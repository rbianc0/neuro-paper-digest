import "server-only";

import { createHash } from "node:crypto";
import { createSupabaseServiceClient } from "@/lib/supabase/service";

export const emailActionsByKind = {
  save: "SAVE",
  more: "MORE_LIKE_THIS",
  less: "LESS_LIKE_THIS",
} as const;

export type EmailActionKind = keyof typeof emailActionsByKind;
export type EmailActionType = (typeof emailActionsByKind)[EmailActionKind];

export const allowedEmailActions = new Set<EmailActionType>(Object.values(emailActionsByKind));
export const lessReasons = new Set([
  "wrong_topic",
  "wrong_methodology",
  "wrong_species",
  "too_clinical",
  "too_basic",
  "already_knew_it",
  "not_interesting",
  "other",
]);

export function actionForKind(kind: string): EmailActionType | null {
  return emailActionsByKind[kind as EmailActionKind] ?? null;
}

export function hashInteractionToken(rawToken: string) {
  return createHash("sha256").update(rawToken, "utf8").digest("hex");
}

export async function inspectEmailToken(rawToken: string) {
  const supabase = createSupabaseServiceClient();
  const { data, error } = await supabase.rpc("get_interaction_token", {
    p_token_hash: hashInteractionToken(rawToken),
  });
  if (error || !data?.length) return null;
  return data[0] as {
    user_id: string;
    paper_id: string;
    digest_id: string;
    action_type: string;
    redirect_url: string | null;
    expires_at: string;
    single_use: boolean;
    used_at: string | null;
  };
}
