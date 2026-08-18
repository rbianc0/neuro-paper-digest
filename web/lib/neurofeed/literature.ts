import "server-only";

import { createSupabaseServiceClient } from "@/lib/supabase/service";
import {
  NEUROFEED,
  canonicalDoi,
  canonicalOpenAlexId,
  canonicalOrcid,
  normalizeText,
  normalizedTitle,
  sha256,
  vectorLiteral,
} from "./core";
import { embedTexts } from "./embedding";

const OPENALEX = "https://api.openalex.org";

export type LiteratureWindow = {
  start: string;
  end: string;
};

type OpenAlexInstitution = {
  id?: string;
  display_name?: string;
  country_code?: string;
  type?: string;
};

type OpenAlexAuthorship = {
  author?: { id?: string; display_name?: string; orcid?: string };
  institutions?: OpenAlexInstitution[];
};

type OpenAlexWork = {
  id?: string;
  doi?: string;
  display_name?: string;
  title?: string;
  publication_date?: string;
  type?: string;
  cited_by_count?: number;
  authorships?: OpenAlexAuthorship[];
  primary_location?: {
    landing_page_url?: string;
    source?: { display_name?: string };
  };
  ids?: { doi?: string; pmid?: string };
  abstract_inverted_index?: Record<string, number[]>;
};

function abstractFromIndex(index: OpenAlexWork["abstract_inverted_index"]) {
  if (!index) return null;
  const words: Array<[number, string]> = [];
  for (const [word, positions] of Object.entries(index)) {
    for (const position of positions) words.push([position, word]);
  }
  words.sort((a, b) => a[0] - b[0]);
  return words.length ? words.map(([, word]) => word).join(" ") : null;
}

function pmidFromWork(work: OpenAlexWork) {
  const raw = work.ids?.pmid;
  return raw ? raw.replace(/\/+$/, "").split("/").pop() || null : null;
}

function authorsFromWork(work: OpenAlexWork) {
  return (work.authorships || []).flatMap((authorship, position) => {
    const author = authorship.author;
    if (!author?.display_name) return [];
    return [{
      name: author.display_name,
      openalexId: canonicalOpenAlexId(author.id),
      orcid: canonicalOrcid(author.orcid),
      position,
      affiliations: (authorship.institutions || []).map((institution) => ({
        openalexId: canonicalOpenAlexId(institution.id),
        name: institution.display_name || null,
        countryCode: institution.country_code || null,
        type: institution.type || null,
      })),
    }];
  });
}

function paperFromWork(work: OpenAlexWork) {
  const openalexId = canonicalOpenAlexId(work.id);
  const title = work.display_name || work.title || "";
  if (!openalexId || !title) return null;
  const doi = canonicalDoi(work.doi || work.ids?.doi);
  const publicationDate = work.publication_date?.slice(0, 10) || null;
  return {
    openalexId,
    sourceUrl: work.id || `https://openalex.org/${openalexId}`,
    sourceLandingUrl: work.primary_location?.landing_page_url || null,
    row: {
      openalex_id: openalexId,
      canonical_doi: doi,
      title,
      title_key: normalizedTitle(title) || null,
      abstract: abstractFromIndex(work.abstract_inverted_index),
      journal: work.primary_location?.source?.display_name || null,
      publication_date: publicationDate,
      first_online_date: publicationDate,
      pmid: pmidFromWork(work),
      cited_by_count: work.cited_by_count ?? 0,
      metadata: {
        openalex_type: work.type || null,
        openalex_authors: authorsFromWork(work),
      },
    },
  };
}

async function openAlexPage(window: LiteratureWindow, cursor: string) {
  const apiKey = process.env.OPENALEX_API_KEY;
  if (!apiKey) throw new Error("OPENALEX_API_KEY is required");

  const url = new URL(`${OPENALEX}/works`);
  url.searchParams.set("api_key", apiKey);
  url.searchParams.set(
    "filter",
    `from_publication_date:${window.start},to_publication_date:${window.end},type:article|preprint,topics.field.id:28|32`,
  );
  url.searchParams.set("sort", "publication_date:desc");
  url.searchParams.set("per-page", "100");
  url.searchParams.set("cursor", cursor);
  url.searchParams.set(
    "select",
    "id,doi,display_name,publication_date,type,cited_by_count,authorships,primary_location,ids,abstract_inverted_index",
  );

  const response = await fetch(url, { headers: { "User-Agent": "Neurofeed/1.0" } });
  if (!response.ok) {
    throw new Error(`OpenAlex failed (${response.status}): ${(await response.text()).slice(0, 400)}`);
  }
  return response.json() as Promise<{
    results?: OpenAlexWork[];
    meta?: { next_cursor?: string };
  }>;
}

export async function syncOpenAlexPage(window: LiteratureWindow, cursor = "*") {
  const page = await openAlexPage(window, cursor);
  const works = (page.results || []).map(paperFromWork).filter((work): work is NonNullable<ReturnType<typeof paperFromWork>> => Boolean(work));
  if (!works.length) return { count: 0, nextCursor: null as string | null };

  const db = createSupabaseServiceClient();
  const { data: persisted, error } = await db
    .from("papers")
    .upsert(works.map((work) => work.row), { onConflict: "openalex_id" })
    .select("id,openalex_id,canonical_doi,pmid");
  if (error) throw error;

  const ids = new Map((persisted || []).map((paper) => [paper.openalex_id, paper]));
  const sources = works.flatMap((work) => {
    const paper = ids.get(work.openalexId);
    if (!paper) return [];
    return [{
      paper_id: paper.id,
      source_type: "openalex",
      external_id: work.openalexId,
      source_url: work.sourceLandingUrl || work.sourceUrl,
      metadata: {},
      retrieved_at: new Date().toISOString(),
    }];
  });
  if (sources.length) {
    const { error: sourceError } = await db.from("paper_sources").upsert(sources, { onConflict: "source_type,external_id" });
    if (sourceError) throw sourceError;
  }

  const identifiers = (persisted || []).flatMap((paper) => [
    { paper_id: paper.id, identifier_type: "OPENALEX", identifier_value: paper.openalex_id },
    ...(paper.canonical_doi ? [{ paper_id: paper.id, identifier_type: "DOI", identifier_value: paper.canonical_doi }] : []),
    ...(paper.pmid ? [{ paper_id: paper.id, identifier_type: "PMID", identifier_value: paper.pmid }] : []),
  ]);
  if (identifiers.length) {
    const { error: identifierError } = await db
      .from("paper_identifiers")
      .upsert(identifiers, { onConflict: "identifier_type,identifier_value" });
    if (identifierError) throw identifierError;
  }

  return {
    count: works.length,
    nextCursor: page.meta?.next_cursor || null,
  };
}

export async function embedPendingPaperBatch(limit = 100) {
  const db = createSupabaseServiceClient();
  const { data: papers, error } = await db
    .from("papers")
    .select("id,title,abstract,journal")
    .is("embedding", null)
    .order("first_online_date", { ascending: false, nullsFirst: false })
    .limit(limit);
  if (error) throw error;
  if (!papers?.length) return 0;

  const texts = papers.map((paper) => normalizeText(paper.title, paper.abstract, paper.journal));
  const vectors = await embedTexts(texts);
  const updates = papers.map((paper, index) => ({
    id: paper.id,
    embedding: vectorLiteral(vectors[index]),
    embedding_model: NEUROFEED.embeddingModel,
    embedding_input_hash: sha256(texts[index]),
  }));
  const { error: updateError } = await db.from("papers").upsert(updates, { onConflict: "id" });
  if (updateError) throw updateError;
  return updates.length;
}
