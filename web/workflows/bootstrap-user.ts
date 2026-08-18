import { RetryableError } from "workflow";

import { syncUserBluesky } from "@/lib/neurofeed/bluesky";
import { createInitialDigest, sendDigest } from "@/lib/neurofeed/digest";
import { embedUserProfile } from "@/lib/neurofeed/embedding";
import { resolveScholarlyLinks, syncScholarlyFeeds, userFollowedDids } from "@/lib/neurofeed/social";

async function embed(userId: string) {
  "use step";
  return embedUserProfile(userId);
}

async function syncBluesky(userId: string) {
  "use step";
  return syncUserBluesky(userId);
}

async function follows(userId: string) {
  "use step";
  return userFollowedDids(userId);
}

async function syncSignals(dids: string[]) {
  "use step";
  return syncScholarlyFeeds(dids, 8);
}

async function resolveSignals() {
  "use step";
  return resolveScholarlyLinks(2000);
}

async function prepareFirstDigest(userId: string) {
  "use step";
  const digestId = await createInitialDigest(userId);
  if (!digestId) {
    throw new RetryableError("The shared literature pool is not ready yet", { retryAfter: "30m" });
  }
  return digestId;
}

async function deliver(digestId: string) {
  "use step";
  return sendDigest(digestId);
}

export async function bootstrapUser(userId: string) {
  "use workflow";

  await embed(userId);
  await syncBluesky(userId);

  const dids = (await follows(userId)).slice(0, 200);
  for (let offset = 0; offset < dids.length; offset += 25) {
    await syncSignals(dids.slice(offset, offset + 25));
  }
  await resolveSignals();

  const digestId = await prepareFirstDigest(userId);
  await deliver(digestId);

  return { userId, digestId };
}
