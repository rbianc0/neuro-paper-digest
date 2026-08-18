import Link from "next/link";
import { recordPaperFeedback } from "@/app/(app)/feedback-actions";
import { requireOnboardedUser } from "@/lib/profile";

export default async function SavedPage() {
  const { supabase } = await requireOnboardedUser();
  const { data: savedRows, error } = await supabase.from("user_saved_papers").select("paper_id,saved_at").order("saved_at", { ascending: false });
  if (error) throw new Error(error.message);
  const ids = (savedRows || []).map((row) => row.paper_id as string);
  const { data: papers, error: paperError } = ids.length ? await supabase.from("papers").select("id,title,journal,publication_date,first_online_date").in("id", ids) : { data: [], error: null };
  if (paperError) throw new Error(paperError.message);
  const paperMap = new Map((papers || []).map((paper) => [paper.id, paper]));

  return (
    <div className="stack">
      <header><div className="kicker">Reading memory</div><h1>Saved papers</h1></header>
      {!ids.length ? <div className="empty">You have not saved any papers yet.</div> : savedRows?.map((saved) => {
        const paper = paperMap.get(saved.paper_id);
        if (!paper) return null;
        return (
          <article className="card paper-card" key={paper.id}>
            <div><h3>{paper.title || "Untitled paper"}</h3><div className="muted">{paper.journal || "Venue unavailable"} · saved {new Date(saved.saved_at).toLocaleDateString()}</div></div>
            <div className="actions">
              <Link className="button" href={`/paper/${paper.id}`}>Read paper</Link>
              <form action={recordPaperFeedback}>
                <input type="hidden" name="paper_id" value={paper.id} />
                <input type="hidden" name="event_type" value="UNSAVE" />
                <input type="hidden" name="return_to" value="/saved" />
                <button className="secondary" type="submit">Unsave</button>
              </form>
            </div>
          </article>
        );
      })}
    </div>
  );
}
