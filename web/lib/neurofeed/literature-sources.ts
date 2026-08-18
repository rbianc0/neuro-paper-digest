import "server-only";

import { createSupabaseServiceClient } from "@/lib/supabase/service";
import { canonicalDoi, normalizedTitle } from "./core";
import type { LiteratureWindow } from "./literature";

const BIORXIV = "https://api.biorxiv.org";
const CROSSREF = "https://api.crossref.org";
const EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest";

type BiorxivPaper = {
  doi?: string;
  title?: string;
  abstract?: string;
  date?: string;
  category?: string;
  published?: string;
  version?: string;
};

type CrossrefWork = {
  abstract?: string;
  "container-title"?: string[];
};

async function paperIdFor(identifierType: "DOI" | "PMID", value: string) {
  const db = createSupabaseServiceClient();
  const { data, error } = await db
    .from("paper_identifiers")
    .select("paper_id")
    .eq("identifier_type", identifierType)
    .eq("identifier_value", value)
    .maybeSingle();
  if (error) throw error;
  return data?.paper_id as string | undefined;
}

async function addIdentifier(paperId: string, type: "DOI" | "PMID", value: string) {
  const db = createSupabaseServiceClient();
  const { error } = await db.from("paper_identifiers").upsert(
    { paper_id: paperId, identifier_type: type, identifier_value: value },
    { onConflict: "identifier_type,identifier_value" },
  );
  if (error) throw error;
}

async function canonicalPaperForDois(preprintDoi: string, publishedDoi: string | null) {
  const db = createSupabaseServiceClient();
  const preprintId = await paperIdFor("DOI", preprintDoi);
  const publishedId = publishedDoi ? await paperIdFor("DOI", publishedDoi) : undefined;

  if (preprintId && publishedId && preprintId !== publishedId) {
    const { data, error } = await db.rpc("merge_papers", { keep_id: publishedId, remove_id: preprintId });
    if (error) throw error;
    return data as string;
  }
  return publishedId || preprintId || null;
}

export async function syncBiorxivPage(window: LiteratureWindow, cursor = 0) {
  const url = `${BIORXIV}/details/biorxiv/${window.start}/${window.end}/${cursor}`;
  const response = await fetch(url, { headers: { "User-Agent": "Neurofeed/1.0" } });
  if (!response.ok) throw new Error(`bioRxiv failed (${response.status})`);

  const payload = await response.json() as {
    collection?: BiorxivPaper[];
    messages?: Array<{ total?: number }>;
  };
  const papers = payload.collection || [];
  const db = createSupabaseServiceClient();
  let stored = 0;

  for (const item of papers) {
    const preprintDoi = canonicalDoi(item.doi);
    const publishedDoi = canonicalDoi(item.published);
    if (!preprintDoi || !item.title?.trim()) continue;

    let paperId = await canonicalPaperForDois(preprintDoi, publishedDoi);
    const row = {
      title: item.title.trim(),
      title_key: normalizedTitle(item.title) || null,
      abstract: item.abstract?.trim() || null,
      publication_date: publishedDoi ? null : item.date?.slice(0, 10) || null,
      first_online_date: item.date?.slice(0, 10) || null,
      canonical_doi: publishedDoi || preprintDoi,
      preprint_doi: preprintDoi,
      published_doi: publishedDoi,
      metadata: {
        biorxiv_category: item.category || null,
        biorxiv_version: item.version || null,
      },
    };

    if (paperId) {
      const { error } = await db.from("papers").update(row).eq("id", paperId);
      if (error) throw error;
    } else {
      const { data, error } = await db.from("papers").insert(row).select("id").single();
      if (error) throw error;
      paperId = data.id;
    }
    if (!paperId) throw new Error(`Failed to persist bioRxiv paper ${preprintDoi}`);

    await addIdentifier(paperId, "DOI", preprintDoi);
    if (publishedDoi) await addIdentifier(paperId, "DOI", publishedDoi);

    const { error: sourceError } = await db.from("paper_sources").upsert({
      paper_id: paperId,
      source_type: "biorxiv",
      external_id: preprintDoi,
      source_url: `https://doi.org/${preprintDoi}`,
      metadata: { category: item.category || null, version: item.version || null },
      retrieved_at: new Date().toISOString(),
    }, { onConflict: "source_type,external_id" });
    if (sourceError) throw sourceError;
    stored++;
  }

  const total = Number(payload.messages?.[0]?.total || 0);
  const nextCursor = cursor + papers.length;
  return { count: stored, nextCursor: papers.length && nextCursor < total ? nextCursor : null };
}

async function crossref(doi: string) {
  const url = new URL(`${CROSSREF}/works/${encodeURIComponent(doi)}`);
  if (process.env.CROSSREF_MAILTO) url.searchParams.set("mailto", process.env.CROSSREF_MAILTO);
  const response = await fetch(url, { headers: { "User-Agent": "Neurofeed/1.0" } });
  if (!response.ok) return null;
  const payload = await response.json() as { message?: CrossrefWork };
  return payload.message || null;
}

async function europePmc(doi: string) {
  const url = new URL(`${EUROPE_PMC}/search`);
  url.searchParams.set("query", `DOI:${doi}`);
  url.searchParams.set("format", "json");
  url.searchParams.set("resultType", "core");
  url.searchParams.set("pageSize", "1");
  const response = await fetch(url, { headers: { "User-Agent": "Neurofeed/1.0" } });
  if (!response.ok) return null;
  const payload = await response.json() as {
    resultList?: { result?: Array<{ pmid?: string; abstractText?: string; journalTitle?: string }> };
  };
  return payload.resultList?.result?.[0] || null;
}

export async function enrichRecentPaperBatch(limit = 40) {
  const db = createSupabaseServiceClient();
  const { data: papers, error } = await db
    .from("papers")
    .select("id,canonical_doi,abstract,journal,pmid")
    .not("canonical_doi", "is", null)
    .or("abstract.is.null,journal.is.null,pmid.is.null")
    .order("first_online_date", { ascending: false, nullsFirst: false })
    .limit(limit);
  if (error) throw error;

  let changed = 0;
  for (const paper of papers || []) {
    const doi = canonicalDoi(paper.canonical_doi);
    if (!doi) continue;
    const [cr, epmc] = await Promise.all([crossref(doi), europePmc(doi)]);
    const pmid = paper.pmid || epmc?.pmid || null;
    const patch = {
      abstract: paper.abstract || epmc?.abstractText || cr?.abstract || null,
      journal: paper.journal || epmc?.journalTitle || cr?.["container-title"]?.[0] || null,
      pmid,
    };
    const { error: updateError } = await db.from("papers").update(patch).eq("id", paper.id);
    if (updateError) throw updateError;
    if (pmid) await addIdentifier(paper.id, "PMID", pmid);

    if (cr) {
      const { error: sourceError } = await db.from("paper_sources").upsert({
        paper_id: paper.id,
        source_type: "crossref",
        external_id: doi,
        source_url: `https://doi.org/${doi}`,
        metadata: {},
        retrieved_at: new Date().toISOString(),
      }, { onConflict: "source_type,external_id" });
      if (sourceError) throw sourceError;
    }
    if (epmc) {
      const { error: sourceError } = await db.from("paper_sources").upsert({
        paper_id: paper.id,
        source_type: "europe_pmc",
        external_id: epmc.pmid || doi,
        source_url: epmc.pmid ? `https://europepmc.org/article/MED/${epmc.pmid}` : null,
        metadata: {},
        retrieved_at: new Date().toISOString(),
      }, { onConflict: "source_type,external_id" });
      if (sourceError) throw sourceError;
    }
    changed++;
  }
  return changed;
}
