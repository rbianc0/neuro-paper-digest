"use server";

import { revalidatePath } from "next/cache";
import { requireUser } from "@/lib/auth";

const allowedEvents = new Set(["SAVE", "UNSAVE", "MORE_LIKE_THIS", "LESS_LIKE_THIS"]);
const lessReasons = new Set(["wrong_topic", "wrong_methodology", "wrong_species", "too_clinical", "too_basic", "already_knew_it", "not_interesting", "other"]);

export async function recordPaperFeedback(formData: FormData) {
  const { supabase } = await requireUser();
  const paperId = String(formData.get("paper_id") || "");
  const digestIdRaw = String(formData.get("digest_id") || "");
  const eventType = String(formData.get("event_type") || "");
  const returnToRaw = String(formData.get("return_to") || "/latest");
  const returnTo = returnToRaw.startsWith("/") && !returnToRaw.startsWith("//") ? returnToRaw : "/latest";

  if (!paperId || !allowedEvents.has(eventType)) return;
  const metadata: Record<string, string> = { surface: "web" };
  if (eventType === "LESS_LIKE_THIS") {
    const reason = String(formData.get("reason") || "not_interesting");
    metadata.reason = lessReasons.has(reason) ? reason : "other";
  }

  const { error } = await supabase.rpc("record_paper_event", {
    p_paper_id: paperId,
    p_digest_id: digestIdRaw || null,
    p_event_type: eventType,
    p_metadata: metadata,
  });
  if (error) throw new Error(error.message);
  revalidatePath(returnTo);
}
