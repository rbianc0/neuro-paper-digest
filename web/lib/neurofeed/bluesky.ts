import "server-only";

import { createSupabaseServiceClient } from "@/lib/supabase/service";

const PUBLIC_API = "https://public.api.bsky.app/xrpc";

type BskyProfile = {
  did: string;
  handle: string;
  displayName?: string;
  description?: string;
  avatar?: string;
  labels?: unknown[];
};

export async function bsky<T>(method: string, params: Record<string, string | number>) {
  const url = new URL(`${PUBLIC_API}/${method}`);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, String(value));
  const response = await fetch(url, { headers: { "User-Agent": "Neurofeed/1.0" } });
  if (!response.ok) {
    throw new Error(`Bluesky ${method} failed (${response.status}): ${(await response.text()).slice(0, 300)}`);
  }
  return response.json() as Promise<T>;
}

async function getProfile(actor: string) {
  return bsky<BskyProfile>("app.bsky.actor.getProfile", { actor });
}

async function getFollows(actor: string) {
  const follows: BskyProfile[] = [];
  let cursor: string | undefined;

  do {
    const page = await bsky<{ follows?: BskyProfile[]; cursor?: string }>(
      "app.bsky.graph.getFollows",
      { actor, limit: 100, ...(cursor ? { cursor } : {}) },
    );
    follows.push(...(page.follows || []));
    cursor = page.cursor;
  } while (cursor);

  return follows;
}

function accountRow(profile: BskyProfile) {
  return {
    did: profile.did,
    handle: profile.handle,
    display_name: profile.displayName || null,
    description: profile.description || null,
    profile_metadata: {
      avatar: profile.avatar || null,
      labels: profile.labels || [],
    },
    last_profile_fetched_at: new Date().toISOString(),
  };
}

export async function syncUserBluesky(userId: string) {
  const db = createSupabaseServiceClient();
  const { data: profile, error } = await db
    .from("profiles")
    .select("bluesky_handle")
    .eq("user_id", userId)
    .single();
  if (error) throw error;
  if (!profile.bluesky_handle) throw new Error("Bluesky handle is missing");

  const owner = await getProfile(profile.bluesky_handle);
  const follows = await getFollows(owner.did);

  const accounts = [owner, ...follows].map(accountRow);
  for (let offset = 0; offset < accounts.length; offset += 250) {
    const { error: accountError } = await db
      .from("bluesky_accounts")
      .upsert(accounts.slice(offset, offset + 250), { onConflict: "did" });
    if (accountError) throw accountError;
  }

  const { data: count, error: replaceError } = await db.rpc("replace_user_bluesky_follows", {
    p_user_id: userId,
    p_bluesky_did: owner.did,
    p_bluesky_handle: owner.handle,
    p_followed_dids: follows.map((follow) => follow.did),
  });
  if (replaceError) throw replaceError;

  return { did: owner.did, handle: owner.handle, follows: Number(count ?? follows.length) };
}
