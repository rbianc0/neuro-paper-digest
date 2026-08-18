import { notFound } from "next/navigation";
import { PaperCard } from "@/components/paper-card";
import { loadDigest, loadSavedPaperIds } from "@/lib/digests";
import { requireOnboardedUser } from "@/lib/profile";

const sectionOrder = ["Must Read", "Highly Relevant", "From Your Bluesky Network", "Broader Discovery"];

export default async function HistoryDigestPage({ params }: { params: Promise<{ digestId: string }> }) {
  const { digestId } = await params;
  const { supabase } = await requireOnboardedUser();
  const { digest, items } = await loadDigest(supabase, digestId);
  if (!digest) notFound();
  const saved = await loadSavedPaperIds(supabase, items.map((item) => item.paper_id));
  const returnTo = `/history/${digestId}`;

  return (
    <div>
      <header><div className="kicker">Archived digest · {digest.period_start} → {digest.period_end}</div><h1>{digest.subject || "Neurofeed Weekly"}</h1></header>
      {sectionOrder.map((section) => {
        const rows = items.filter((item) => item.section === section);
        if (!rows.length) return null;
        return <section className="section" key={section}><h2>{section}</h2><div className="stack">{rows.map((item) => <PaperCard key={item.paper_id} item={item} digestId={digestId} saved={saved.has(item.paper_id)} returnTo={returnTo} />)}</div></section>;
      })}
    </div>
  );
}
