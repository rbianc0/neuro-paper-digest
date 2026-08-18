import Link from "next/link";
import { recordPaperFeedback } from "@/app/(app)/feedback-actions";
import type { DigestItemRow } from "@/lib/digests";

export function PaperCard({ item, digestId, saved, returnTo }: { item: DigestItemRow; digestId: string; saved: boolean; returnTo: string }) {
  const paper = item.papers;
  if (!paper) return null;

  return (
    <article className="card paper-card">
      <div>
        <div className="kicker">#{item.rank} · {item.section}</div>
        <h3>{paper.title || "Untitled paper"}</h3>
        <div className="muted">{paper.journal || "Venue unavailable"}</div>
      </div>
      <p>{item.summary || "Summary unavailable."}</p>
      <p><strong>Why:</strong> {item.why_recommended || "Recommendation explanation unavailable."}</p>
      <div className="actions">
        <Link className="button" href={`/paper/${paper.id}?digest=${digestId}`}>Read paper</Link>
        <form action={recordPaperFeedback}>
          <input type="hidden" name="paper_id" value={paper.id} />
          <input type="hidden" name="digest_id" value={digestId} />
          <input type="hidden" name="event_type" value={saved ? "UNSAVE" : "SAVE"} />
          <input type="hidden" name="return_to" value={returnTo} />
          <button className="secondary" type="submit">{saved ? "Unsave" : "Save"}</button>
        </form>
        <form action={recordPaperFeedback}>
          <input type="hidden" name="paper_id" value={paper.id} />
          <input type="hidden" name="digest_id" value={digestId} />
          <input type="hidden" name="event_type" value="MORE_LIKE_THIS" />
          <input type="hidden" name="return_to" value={returnTo} />
          <button className="secondary" type="submit">More like this</button>
        </form>
        <details>
          <summary>Less like this</summary>
          <form action={recordPaperFeedback} className="stack" style={{ marginTop: "0.6rem" }}>
            <input type="hidden" name="paper_id" value={paper.id} />
            <input type="hidden" name="digest_id" value={digestId} />
            <input type="hidden" name="event_type" value="LESS_LIKE_THIS" />
            <input type="hidden" name="return_to" value={returnTo} />
            <select name="reason" defaultValue="not_interesting" aria-label="Reason for less like this">
              <option value="not_interesting">Not interesting</option>
              <option value="wrong_topic">Wrong topic</option>
              <option value="wrong_methodology">Wrong methodology</option>
              <option value="wrong_species">Wrong species</option>
              <option value="too_clinical">Too clinical</option>
              <option value="too_basic">Too basic</option>
              <option value="already_knew_it">Already knew it</option>
              <option value="other">Other</option>
            </select>
            <button className="danger" type="submit">Submit feedback</button>
          </form>
        </details>
        <Link href={`/recommendation/${digestId}/${paper.id}`}>Why this paper?</Link>
      </div>
    </article>
  );
}
