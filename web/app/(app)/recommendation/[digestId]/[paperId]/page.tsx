import Link from "next/link";
import { notFound } from "next/navigation";
import { requireOnboardedUser } from "@/lib/profile";

function percent(value: number | null) {
  return value == null ? "—" : `${Math.round(Number(value) * 100)}%`;
}

export default async function RecommendationPage({ params }: { params: Promise<{ digestId: string; paperId: string }> }) {
  const { digestId, paperId } = await params;
  const { supabase } = await requireOnboardedUser();
  const { data, error } = await supabase.from("digest_items").select("digest_id,paper_id,rank,section,final_score,semantic_score,bluesky_score,fit_score,quality_score,broad_discovery_score,novelty_score,recency_score,summary,why_recommended,explanation_snapshot,papers(id,title,journal,publication_date)").eq("digest_id", digestId).eq("paper_id", paperId).maybeSingle();
  if (error) throw new Error(error.message);
  if (!data) notFound();
  const paper = data.papers as unknown as { id: string; title: string | null; journal: string | null; publication_date: string | null } | null;
  if (!paper) notFound();
  const explanation = (data.explanation_snapshot || {}) as Record<string, unknown>;
  const provenance = (explanation.provenance || {}) as Record<string, unknown>;

  return (
    <div className="stack">
      <header><div className="kicker">Recommendation explanation</div><h1>{paper.title || "Untitled paper"}</h1><p className="muted">{paper.journal || "Venue unavailable"} · {data.section}</p></header>
      <section className="card"><h2>Why you saw this</h2><p>{data.why_recommended || "No explanation snapshot is available."}</p><p className="muted">The values below are the exact score components frozen when this digest was generated.</p></section>
      <section className="score-grid">
        {[['Final', data.final_score], ['Semantic', data.semantic_score], ['Bluesky', data.bluesky_score], ['Method/species fit', data.fit_score], ['Priority prior', data.quality_score], ['Broad importance', data.broad_discovery_score], ['Novelty', data.novelty_score], ['Recency', data.recency_score]].map(([label, value]) => <div className="score" key={String(label)}><span>{String(label)}</span><strong>{percent(value as number | null)}</strong></div>)}
      </section>
      <section className="card"><h2>Network provenance</h2><p>Independent followed actors: {String(provenance.independent_followed_actors ?? 0)}</p><p>Authored by a followed scientist: {provenance.authored_by_followed ? "Yes" : "No"}</p><p>Direct posts: {String(provenance.direct_count ?? 0)} · Reposts: {String(provenance.repost_count ?? 0)} · Quotes: {String(provenance.quote_count ?? 0)}</p></section>
      <div className="actions"><Link className="button" href={`/paper/${paper.id}?digest=${digestId}`}>Read paper</Link><Link href={`/history/${digestId}`}>Back to digest</Link></div>
    </div>
  );
}
