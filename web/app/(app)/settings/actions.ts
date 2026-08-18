"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { start } from "workflow/api";

import { requireUser } from "@/lib/auth";
import { bootstrapUser } from "@/workflows/bootstrap-user";

async function restartPersonalization(userId: string) {
  await start(bootstrapUser, [userId]);
}

export async function updateSettings(formData: FormData) {
  const { supabase, user } = await requireUser();
  const blueskyHandle = String(formData.get("bluesky_handle") || "").trim().replace(/^@/, "");
  const researchDescription = String(formData.get("research_description") || "").trim();
  const discoveryBalance = Number(formData.get("discovery_balance") || 0.25);
  const newsletterEnabled = formData.get("newsletter_enabled") === "on";

  if (!blueskyHandle || !blueskyHandle.includes(".") || researchDescription.length < 20 || discoveryBalance < 0 || discoveryBalance > 1) {
    redirect("/settings?error=Check%20the%20profile%20fields%20and%20try%20again.");
  }

  const { error } = await supabase.from("profiles").update({
    bluesky_handle: blueskyHandle,
    research_description: researchDescription,
    discovery_balance: discoveryBalance,
    newsletter_enabled: newsletterEnabled,
    bluesky_sync_requested_at: new Date().toISOString(),
  }).eq("user_id", user.id);

  if (error) redirect(`/settings?error=${encodeURIComponent(error.message.slice(0, 220))}`);
  await restartPersonalization(user.id);
  revalidatePath("/settings");
  redirect("/settings?saved=1");
}

export async function requestBlueskyResync() {
  const { supabase, user } = await requireUser();
  const { error } = await supabase.from("profiles").update({ bluesky_sync_requested_at: new Date().toISOString() }).eq("user_id", user.id);
  if (error) redirect(`/settings?error=${encodeURIComponent(error.message.slice(0, 220))}`);
  await restartPersonalization(user.id);
  revalidatePath("/settings");
  redirect("/settings?sync=1");
}
