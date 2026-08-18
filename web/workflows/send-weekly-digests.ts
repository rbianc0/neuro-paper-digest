import { createSupabaseServiceClient } from "@/lib/supabase/service";
import { createWeeklyDigest, sendDigest } from "@/lib/neurofeed/digest";

async function subscribers() {
  "use step";
  const db = createSupabaseServiceClient();
  const { data, error } = await db.rpc("get_newsletter_users");
  if (error) throw error;
  return (data || []).map((row: { user_id: string }) => row.user_id);
}

async function prepare(userId: string) {
  "use step";
  return createWeeklyDigest(userId);
}

async function deliver(digestId: string) {
  "use step";
  return sendDigest(digestId);
}

export async function sendWeeklyDigests() {
  "use workflow";

  const users = await subscribers();
  let generated = 0;
  let sent = 0;
  for (const userId of users) {
    const digestId = await prepare(userId);
    if (!digestId) continue;
    generated++;
    const result = await deliver(digestId);
    if (result.sent) sent++;
  }
  return { users: users.length, generated, sent };
}
