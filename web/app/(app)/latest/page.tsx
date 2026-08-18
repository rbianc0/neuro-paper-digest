import { ImpressionTracker } from "@/components/impression-tracker";
import { PaperCard } from "@/components/paper-card";
import { loadDigest, loadLatestDigest, loadSavedPaperIds } from "@/lib/digests";
import { requireOnboardedUser } from "@/lib/profile";

const sectionOrder = ["Must Read", "Highly Relevant", "From Your Bluesky Network", "Broader Discovery"];

export default async function LatestPage() {
  const { supabase } = await requireOnboardedUser();
  const latest = await loadLatestDigest(supabase);

  if (!latest) {
    return (
      <div className="stack">
        <header><div className="kicker">Weekly digest</div><h1>Latest</h1></header>
        <div className="empty">No digest has been generated yet. Once the shared literature, Bluesky, and model jobs have run, your first finite weekly digest will appear here.</div>
      </div>
    );
  }

  const { items } = await loadDigest(supabase, latest.id);
  const saved = await loadSavedPaperIds(supabase, items.map((item) => item.paper_id));

  return (
    <div>
      <header>
        <div className="kicker">Weekly digest · {latest.period_start} → {latest.period_end}</div>
        <h1>{latest.subject || "Neurofeed Weekly"}</h1>
        <p className="muted">{items.length} unique papers. Finite by design.</p>
      </header>
      <ImpressionTracker digestId={latest.id} paperIds={items.map((item) => item.paper_id)} />
      {sectionOrder.map((section) => {
        const rows = items.filter((item) => item.section === section);
        if (!rows.length) return null;
        return (
          <section className="section" key={section}>
            <h2>{section}</h2>
            <div className="stack">
              {rows.map((item) => <PaperCard key={item.paper_id} item={item} digestId={latest.id} saved={saved.has(item.paper_id)} returnTo="/latest" />)}
            </div>
          </section>
        );
      })}
    </div>
  );
}
