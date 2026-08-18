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

async function syncPage(window: { start: string; end: string }, cursor: string) {
  "use step";
  return syncOpenAlexPage(window, cursor);
}

async function embedBatch() {
  "use step";
  return embedPendingPaperBatch(100);
}

export async function refreshLiterature() {
  "use workflow";

  const window = await windowFor(8);
  let cursor: string | null = "*";
  let papers = 0;

  for (let page = 0; page < 50 && cursor; page++) {
    const result = await syncPage(window, cursor);
    papers += result.count;
    cursor = result.nextCursor;
    if (result.count === 0) break;
  }

  let embedded = 0;
  for (let batch = 0; batch < 50; batch++) {
    const count = await embedBatch();
    embedded += count;
    if (count < 100) break;
  }

  return { window, papers, embedded };
}
