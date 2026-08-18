import { enrichRecentPaperBatch, syncBiorxivPage } from "@/lib/neurofeed/literature-sources";
import { embedPendingPaperBatch, syncOpenAlexPage } from "@/lib/neurofeed/literature";

async function windowFor(days: number) {
  "use step";
  const end = new Date();
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - days);
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}

async function syncOpenAlex(window: { start: string; end: string }, cursor: string) {
  "use step";
  return syncOpenAlexPage(window, cursor);
}

async function syncBiorxiv(window: { start: string; end: string }, cursor: number) {
  "use step";
  return syncBiorxivPage(window, cursor);
}

async function enrich() {
  "use step";
  return enrichRecentPaperBatch(40);
}

async function embedBatch() {
  "use step";
  return embedPendingPaperBatch(100);
}

export async function refreshLiterature() {
  "use workflow";

  const window = await windowFor(8);
  let openAlexCursor: string | null = "*";
  let openAlexPapers = 0;
  for (let page = 0; page < 50 && openAlexCursor; page++) {
    const result = await syncOpenAlex(window, openAlexCursor);
    openAlexPapers += result.count;
    openAlexCursor = result.nextCursor;
    if (result.count === 0) break;
  }

  let biorxivCursor: number | null = 0;
  let biorxivPapers = 0;
  for (let page = 0; page < 100 && biorxivCursor !== null; page++) {
    const result = await syncBiorxiv(window, biorxivCursor);
    biorxivPapers += result.count;
    biorxivCursor = result.nextCursor;
    if (result.count === 0) break;
  }

  const enriched = await enrich();

  let embedded = 0;
  for (let batch = 0; batch < 50; batch++) {
    const count = await embedBatch();
    embedded += count;
    if (count < 100) break;
  }

  return { window, openAlexPapers, biorxivPapers, enriched, embedded };
}
