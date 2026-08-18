import { notFound } from "next/navigation";
import { confirmEmailAction, expectedActionForKind } from "./actions";
import { inspectEmailToken } from "@/lib/email-actions";
import { createSupabaseServiceClient } from "@/lib/supabase/service";

const labels: Record<string, string> = {
  SAVE: "Save this paper",
  MORE_LIKE_THIS: "Show me more like this",
  LESS_LIKE_THIS: "Show me less like this",
};

export default async function EmailActionPage({
  params,
}: {
  params: Promise<{ kind: string; token: string }>;
}) {
  const { kind, token: rawToken } = await params;
  const expectedAction = expectedActionForKind(kind);
  if (!expectedAction) notFound();

  const token = await inspectEmailToken(rawToken);
  if (!token || token.action_type !== expectedAction) notFound();

  const supabase = createSupabaseServiceClient();
  const { data: paper } = await supabase
    .from("papers")
    .select("title,journal")
    .eq("id", token.paper_id)
    .maybeSingle();

  const action = confirmEmailAction.bind(null, rawToken, expectedAction);

  return (
    <main className="shell">
      <section className="form-card">
        <div className="kicker">Email feedback confirmation</div>
        <h1>{labels[expectedAction]}</h1>
        <p>
          <strong>{paper?.title || "This paper"}</strong>
          {paper?.journal ? ` — ${paper.journal}` : ""}
        </p>
        <p className="muted">
          Opening this page has not changed your preferences. Confirm below to record the action.
        </p>
        <form action={action} className="form-grid">
          {expectedAction === "LESS_LIKE_THIS" ? (
            <label>
              Optional reason
              <select name="reason" defaultValue="not_interesting">
                <option value="not_interesting">Not interesting</option>
                <option value="wrong_topic">Wrong topic</option>
                <option value="wrong_methodology">Wrong methodology</option>
                <option value="wrong_species">Wrong species</option>
                <option value="too_clinical">Too clinical</option>
                <option value="too_basic">Too basic</option>
                <option value="already_knew_it">Already knew it</option>
                <option value="other">Other</option>
              </select>
            </label>
          ) : null}
          <button type="submit">Confirm</button>
        </form>
      </section>
    </main>
  );
}
