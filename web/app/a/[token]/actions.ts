"use server";

import { redirect } from "next/navigation";
import { allowedEmailActions, hashInteractionToken, inspectEmailToken, lessReasons } from "@/lib/email-actions";
import { createSupabaseServiceClient } from "@/lib/supabase/service";

export async function confirmEmailAction(rawToken: string, formData: FormData) {
  const token = await inspectEmailToken(rawToken);
  if (!token || !allowedEmailActions.has(token.action_type)) redirect("/feedback/invalid");

  const metadata: Record<string, string> = { surface: "email_action" };
  if (token.action_type === "LESS_LIKE_THIS") {
    const reason = String(formData.get("reason") || "not_interesting");
    metadata.reason = lessReasons.has(reason) ? reason : "other";
  }

  const supabase = createSupabaseServiceClient();
  const { error } = await supabase.rpc("consume_interaction_token", {
    p_token_hash: hashInteractionToken(rawToken),
    p_expected_action: token.action_type,
    p_metadata: metadata,
  });
  if (error) redirect("/feedback/invalid");
  redirect(`/feedback/thanks?action=${encodeURIComponent(token.action_type)}`);
}
