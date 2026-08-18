import { NextResponse, type NextRequest } from "next/server";
import { hashInteractionToken } from "@/lib/email-actions";
import { createSupabaseServiceClient } from "@/lib/supabase/service";

function safeExternalUrl(value: string | null) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const supabase = createSupabaseServiceClient();
  const { data, error } = await supabase.rpc("consume_interaction_token", {
    p_token_hash: hashInteractionToken(token),
    p_expected_action: "CLICK",
    p_metadata: { surface: "email_redirect" },
  });
  const row = !error && data?.length ? data[0] : null;
  const destination = safeExternalUrl(row?.redirect_url || null);
  if (!destination) return NextResponse.redirect(new URL("/feedback/invalid", request.url));
  return NextResponse.redirect(destination);
}
