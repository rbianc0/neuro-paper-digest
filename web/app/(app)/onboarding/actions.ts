"use server";

import { redirect } from "next/navigation";
import { start } from "workflow/api";

import { requireUser } from "@/lib/auth";
import { bootstrapUser } from "@/workflows/bootstrap-user";

export async function saveOnboarding(formData: FormData) {
  const { supabase, user } = await requireUser();
  const blueskyHandle = String(formData.get("bluesky_handle") || "").trim().replace(/^@/, "");
  const researchDescription = String(formData.get("research_description") || "").trim();
  const discoveryBalance = Number(formData.get("discovery_balance") || 0.25);
  const newsletterEnabled = formData.get("newsletter_enabled") === "on";

  if (!blueskyHandle || !blueskyHandle.includes(".")) {
    redirect("/onboarding?error=Enter%20a%20valid%20Bluesky%20handle.");
  }
  if (researchDescription.length < 20) {
    redirect("/onboarding?error=Describe%20your%20research%20interests%20in%20a%20little%20more%20detail.");
  }
  if (!Number.isFinite(discoveryBalance) || discoveryBalance < 0 || discoveryBalance > 1) {
    redirect("/onboarding?error=Discovery%20balance%20must%20be%20between%200%20and%201.");
  }

  const { error } = await supabase.from("profiles").upsert({
    user_id: user.id,
    email: user.email,
    bluesky_handle: blueskyHandle,
    research_description: researchDescription,
    discovery_balance: discoveryBalance,
    newsletter_enabled: newsletterEnabled,
    bluesky_sync_requested_at: new Date().toISOString(),
  }, { onConflict: "user_id" });

  if (error) {
    redirect(`/onboarding?error=${encodeURIComponent(error.message.slice(0, 220))}`);
  }

  try {
    await start(bootstrapUser, [user.id]);
  } catch (workflowError) {
    redirect(`/onboarding?error=${encodeURIComponent(String(workflowError).slice(0, 220))}`);
  }

  redirect("/latest");
}
