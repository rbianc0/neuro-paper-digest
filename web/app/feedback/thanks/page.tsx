import Link from "next/link";

const messages: Record<string, string> = {
  SAVE: "Paper saved.",
  MORE_LIKE_THIS: "Preference recorded. Future ranking can learn from this paper.",
  LESS_LIKE_THIS: "Preference recorded. Future ranking can use this signal.",
};

export default async function FeedbackThanksPage({ searchParams }: { searchParams: Promise<{ action?: string }> }) {
  const { action } = await searchParams;
  return <main className="shell"><section className="form-card"><div className="kicker">Neurofeed</div><h1>Feedback recorded</h1><p>{messages[action || ""] || "Your action was recorded."}</p><Link href="/latest">Open Neurofeed</Link></section></main>;
}
