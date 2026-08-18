import { NextResponse, type NextRequest } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";

function safeExternalUrl(value: string | null) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ paperId: string }> }) {
  const { paperId } = await params;
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.redirect(new URL("/login", request.url));

  const { data: paper } = await supabase.from("papers").select("id,canonical_doi").eq("id", paperId).maybeSingle();
  if (!paper) return NextResponse.redirect(new URL("/latest", request.url));
  let destination = paper.canonical_doi ? `https://doi.org/${paper.canonical_doi}` : null;
  if (!destination) {
    const { data: source } = await supabase.from("paper_sources").select("source_url").eq("paper_id", paperId).not("source_url", "is", null).order("retrieved_at", { ascending: false }).limit(1).maybeSingle();
    destination = safeExternalUrl(source?.source_url || null);
  }
  if (!destination) return NextResponse.redirect(new URL("/latest", request.url));

  const digestId = request.nextUrl.searchParams.get("digest");
  await supabase.rpc("record_paper_event", { p_paper_id: paperId, p_digest_id: digestId || null, p_event_type: "CLICK", p_metadata: { surface: "web" } });
  return NextResponse.redirect(destination);
}
