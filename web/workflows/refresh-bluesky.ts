import { createSupabaseServiceClient } from "@/lib/supabase/service";
import { resolveScholarlyLinks, syncScholarlyFeeds } from "@/lib/neurofeed/social";

async function staleAccounts() {
  "use step";
  const db = createSupabaseServiceClient();
  const staleBefore = new Date(Date.now() - 18 * 60 * 60 * 1000).toISOString();
  const { data, error } = await db.rpc("get_stale_bluesky_accounts", {
    p_stale_before: staleBefore,
    p_limit: 1000,
  });
  if (error) throw error;
  return (data || []).map((row: { did: string }) => row.did);
}

async function syncBatch(dids: string[]) {
  "use step";
  return syncScholarlyFeeds(dids, 8);
}

async function resolve() {
  "use step";
  return resolveScholarlyLinks(5000);
}

export async function refreshBluesky() {
  "use workflow";

  const dids = await staleAccounts();
  let events = 0;
  let failed = 0;
  for (let offset = 0; offset < dids.length; offset += 25) {
    const result = await syncBatch(dids.slice(offset, offset + 25));
    events += result.events;
    failed += result.failed;
  }
  const resolved = await resolve();
  return { accounts: dids.length, events, failed, resolved };
}
