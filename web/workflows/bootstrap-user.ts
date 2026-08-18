import { RetryableError } from "workflow";

import { syncUserBluesky } from "@/lib/neurofeed/bluesky";
import { createInitialDigest, sendDigest } from "@/lib/neurofeed/digest";
import { embedUserProfile } from "@/lib/neurofeed/embedding";

async function embed(userId: string) {
  "use step";
  return embedUserProfile(userId);
}

async function syncBluesky(userId: string) {
  "use step";
  return syncUserBluesky(userId);
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
  const digestId = await prepareFirstDigest(userId);
  await deliver(digestId);

  return { userId, digestId };
}
