import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";

export async function requireOnboardedUser() {
  const { supabase, user } = await requireUser();
  const { data: profile, error } = await supabase
    .from("profiles")
    .select("user_id,research_description,bluesky_handle,discovery_balance,newsletter_enabled,last_bluesky_sync_at,last_bluesky_sync_error,bluesky_sync_requested_at")
    .eq("user_id", user.id)
    .maybeSingle();

  if (error) throw new Error(error.message);
  if (!profile?.research_description || !profile?.bluesky_handle) {
    redirect("/onboarding");
  }

  return { supabase, user, profile };
}
