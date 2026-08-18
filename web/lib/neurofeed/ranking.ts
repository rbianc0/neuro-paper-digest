import "server-only";

import { createSupabaseServiceClient } from "@/lib/supabase/service";
import { NEUROFEED, RankedPaper, ageDays, clamp, isoDateDaysAgo, saturatingCount } from "./core";

type Paper = {
  id: string;
  title: string;
  abstract: string | null;
  journal: string | null;
  publication_date: string | null;
  first_online_date: string | null;
  cited_by_count: number | null;
};

type Network = {
  paper_id: string;
  independent_actors: number;
  direct_count: number;
  repost_count: number;
  quote_count: number;
  latest_signal_at: string | null;
  authored_by_followed: boolean;
};

type BroadCandidate = {
  paper_id: string;
  venue_priority: boolean;
  cited_by_count: number | null;
};

const STOP = new Set([
  "the", "and", "for", "with", "from", "into", "using", "study", "studies", "paper",
  "research", "brain", "neural", "neuroscience", "analysis", "data", "this", "that",
]);

function tokens(text: string) {
  return new Set((text.toLowerCase().match(/[a-z][a-z0-9+:/-]{2,}/g) || []).filter((x) => !STOP.has(x)));
}

function fitScore(profile: string, paper: Paper) {
  const a = tokens(profile);
  const b = tokens(`${paper.title} ${paper.abstract || ""}`);
  if (!a.size) return 0;
  let overlap = 0;
  for (const word of a) if (b.has(word)) overlap++;
  return clamp(overlap / Math.min(12, a.size));
}

function qualityScore(paper: Paper) {
  const venue = (paper.journal || "").trim().toLowerCase();
  const venueScore = NEUROFEED.priorityVenues.has(venue) ? 1 : 0;
  const citations = Math.max(0, paper.cited_by_count || 0);
  const citationScore = Math.min(1, Math.log1p(citations) / Math.log(21));
  return clamp(0.55 * venueScore + 0.45 * citationScore);
}

function recencyScore(paper: Paper) {
  return clamp(Math.exp(-ageDays(paper.first_online_date || paper.publication_date) / 14));
}

function blueskyScore(row?: Network) {
  if (!row) return 0;
  const signalAge = ageDays(row.latest_signal_at);
  let score =
    0.45 * saturatingCount(row.independent_actors, 2) +
    0.20 * saturatingCount(row.direct_count, 1.5) +
    0.15 * saturatingCount(row.quote_count, 1.5) +
    0.05 * saturatingCount(row.repost_count, 2.5) +
    0.15 * Math.exp(-signalAge / 7);
  if (row.authored_by_followed) score = Math.max(0.72, score);
  return clamp(score);
}

function learnedWeight(count: number) {
  if (count < 2) return 0;
  return Math.min(0.35, 0.35 * Math.min(1, (count - 1) / 9));
}

function learnedSimilarity(positive?: number, negative?: number) {
  if (positive !== undefined && negative !== undefined) return clamp(0.5 + 0.5 * (positive - negative));
  if (positive !== undefined) return clamp(positive);
  if (negative !== undefined) return clamp(1 - negative);
  return undefined;
}

export async function rankUser(userId: string): Promise<RankedPaper[]> {
  const db = createSupabaseServiceClient();
  const [{ data: profile, error: profileError }, { data: state, error: stateError }] = await Promise.all([
    db.from("profiles").select("research_description,discovery_balance").eq("user_id", userId).single(),
    db.from("user_embeddings").select("declared_embedding,learned_positive_embedding,learned_negative_embedding,feedback_count").eq("user_id", userId).single(),
  ]);
  if (profileError) throw profileError;
  if (stateError) throw stateError;
  if (!state.declared_embedding) throw new Error("User embedding is missing");

  const publishedAfter = isoDateDaysAgo(NEUROFEED.lookbackDays);
  const [semanticResult, networkResult, broadResult, seenResult] = await Promise.all([
    db.rpc("match_papers", {
      p_query_embedding: state.declared_embedding,
      p_published_after: publishedAfter,
      p_match_count: NEUROFEED.semanticCandidates,
    }),
    db.rpc("get_user_network_candidates", { p_user_id: userId, p_published_after: publishedAfter }),
    db.rpc("get_broad_candidates", {
      p_published_after: publishedAfter,
      p_priority_venues: [...NEUROFEED.priorityVenues],
      p_limit: NEUROFEED.broadCandidates,
    }),
    db.rpc("get_user_seen_papers", { p_user_id: userId }),
  ]);
  for (const result of [semanticResult, networkResult, broadResult, seenResult]) if (result.error) throw result.error;

  const declared = new Map<string, number>(
    (semanticResult.data || []).map((row: { paper_id: string; similarity: number }) => [row.paper_id, Number(row.similarity)]),
  );
  const network = new Map<string, Network>(
    (networkResult.data || []).map((row: Network) => [row.paper_id, row]),
  );
  const broad = new Map<string, BroadCandidate>(
    (broadResult.data || []).map((row: BroadCandidate) => [row.paper_id, row]),
  );
  const seen = new Set<string>((seenResult.data || []).map((row: { paper_id: string }) => row.paper_id));
  const ids: string[] = [...new Set<string>([...declared.keys(), ...network.keys(), ...broad.keys()])].filter((id) => !seen.has(id));
  if (!ids.length) return [];

  const { data: papers, error: paperError } = await db
    .from("papers")
    .select("id,title,abstract,journal,publication_date,first_online_date,cited_by_count")
    .in("id", ids);
  if (paperError) throw paperError;

  const alpha = learnedWeight(Number(state.feedback_count || 0));
  const positive = new Map<string, number>();
  const negative = new Map<string, number>();
  if (alpha > 0) {
    for (const [vector, target] of [
      [state.learned_positive_embedding, positive],
      [state.learned_negative_embedding, negative],
    ] as const) {
      if (!vector) continue;
      const { data, error } = await db.rpc("score_papers", { p_paper_ids: ids, p_query_embedding: vector });
      if (error) throw error;
      for (const row of (data || []) as Array<{ paper_id: string; similarity: number }>) {
        target.set(row.paper_id, Number(row.similarity));
      }
    }
  }

  const ranked = (papers as Paper[]).map((paper) => {
    const declaredScore = clamp(declared.get(paper.id) || 0);
    const learned = learnedSimilarity(positive.get(paper.id), negative.get(paper.id));
    const semantic = learned === undefined ? declaredScore : clamp((1 - alpha) * declaredScore + alpha * learned);
    const social = blueskyScore(network.get(paper.id));
    const fit = fitScore(profile.research_description || "", paper);
    const quality = qualityScore(paper);
    const broadRow = broad.get(paper.id);
    const broadScore = broadRow
      ? (broadRow.venue_priority ? 1 : clamp(0.35 + 0.15 * Math.log1p(Number(broadRow.cited_by_count || 0))))
      : 0;
    const recency = recencyScore(paper);
    const score = clamp(
      NEUROFEED.weights.semantic * semantic +
      NEUROFEED.weights.bluesky * social +
      NEUROFEED.weights.fit * fit +
      NEUROFEED.weights.quality * quality +
      NEUROFEED.weights.broad * broadScore +
      NEUROFEED.weights.novelty +
      NEUROFEED.weights.recency * recency,
    );
    return {
      paperId: paper.id,
      finalScore: score,
      semanticScore: semantic,
      blueskyScore: social,
      fitScore: fit,
      qualityScore: quality,
      broadScore,
      noveltyScore: 1,
      recencyScore: recency,
      lane: broadRow && semantic < 0.58 && social < 0.35 ? "broad" : "focused",
      provenance: { declaredSimilarity: declaredScore, learnedSimilarity: learned, learnedWeight: alpha, network: network.get(paper.id) || null },
    } satisfies RankedPaper;
  }).sort((a, b) => b.finalScore - a.finalScore);

  const broadTarget = Math.round(NEUROFEED.targetPapers * Number(profile.discovery_balance ?? 0.25));
  const focusedTarget = NEUROFEED.targetPapers - broadTarget;
  const selected = [
    ...ranked.filter((x) => x.lane === "focused").slice(0, focusedTarget),
    ...ranked.filter((x) => x.lane === "broad").slice(0, broadTarget),
  ];
  const used = new Set(selected.map((x) => x.paperId));
  if (selected.length < NEUROFEED.targetPapers) {
    selected.push(...ranked.filter((x) => !used.has(x.paperId)).slice(0, NEUROFEED.targetPapers - selected.length));
  }
  return selected.sort((a, b) => b.finalScore - a.finalScore);
}
