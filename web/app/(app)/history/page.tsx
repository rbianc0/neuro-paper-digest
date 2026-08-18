import Link from "next/link";
import { requireOnboardedUser } from "@/lib/profile";

export default async function HistoryPage() {
  const { supabase } = await requireOnboardedUser();
  const { data, error } = await supabase.from("digests").select("id,period_start,period_end,generated_at,sent_at,subject,status").in("status", ["GENERATED", "SENT"]).order("generated_at", { ascending: false });
  if (error) throw new Error(error.message);

  return (
    <div className="stack">
      <header><div className="kicker">Archive</div><h1>Digest history</h1></header>
      {!data?.length ? <div className="empty">No previous digests yet.</div> : data.map((digest) => (
        <article className="card" key={digest.id}>
          <div className="kicker">{digest.period_start} → {digest.period_end}</div>
          <h2 style={{ marginBottom: "0.35rem" }}>{digest.subject || "Neurofeed Weekly"}</h2>
          <p className="muted">Status: {digest.status}{digest.sent_at ? ` · sent ${new Date(digest.sent_at).toLocaleDateString()}` : ""}</p>
          <Link href={`/history/${digest.id}`}>Open digest</Link>
        </article>
      ))}
    </div>
  );
}
