import type { SupabaseClient } from "@supabase/supabase-js";

export type DigestRow = {
  id: string;
  period_start: string;
  period_end: string;
  generated_at: string;
  sent_at: string | null;
  subject: string | null;
  status: string;
};

export type DigestItemRow = {
  digest_id: string;
  paper_id: string;
  rank: number;
  section: string;
  final_score: number;
  semantic_score: number | null;
  bluesky_score: number | null;
  fit_score: number | null;
  quality_score: number | null;
  broad_discovery_score: number | null;
  novelty_score: number | null;
  recency_score: number | null;
  summary: string | null;
  why_recommended: string | null;
  explanation_snapshot: unknown;
  papers: {
    id: string;
    title: string | null;
    journal: string | null;
    publication_date: string | null;
    first_online_date: string | null;
  } | null;
};

export async function loadLatestDigest(supabase: SupabaseClient) {
  const { data, error } = await supabase
    .from("digests")
    .select("id,period_start,period_end,generated_at,sent_at,subject,status")
    .in("status", ["GENERATED", "SENT"])
    .order("generated_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) throw new Error(error.message);
  return data as DigestRow | null;
}

export async function loadDigest(supabase: SupabaseClient, digestId: string) {
  const [{ data: digest, error: digestError }, { data: items, error: itemError }] = await Promise.all([
    supabase.from("digests").select("id,period_start,period_end,generated_at,sent_at,subject,status").eq("id", digestId).maybeSingle(),
    supabase.from("digest_items").select("digest_id,paper_id,rank,section,final_score,semantic_score,bluesky_score,fit_score,quality_score,broad_discovery_score,novelty_score,recency_score,summary,why_recommended,explanation_snapshot,papers(id,title,journal,publication_date,first_online_date)").eq("digest_id", digestId).order("rank", { ascending: true }),
  ]);
  if (digestError) throw new Error(digestError.message);
  if (itemError) throw new Error(itemError.message);
  return { digest: digest as DigestRow | null, items: (items || []) as unknown as DigestItemRow[] };
}

export async function loadSavedPaperIds(supabase: SupabaseClient, paperIds: string[]) {
  if (!paperIds.length) return new Set<string>();
  const { data, error } = await supabase.from("user_saved_papers").select("paper_id").in("paper_id", paperIds);
  if (error) throw new Error(error.message);
  return new Set((data || []).map((row) => row.paper_id as string));
}
