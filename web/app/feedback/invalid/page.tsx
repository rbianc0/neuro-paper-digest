import Link from "next/link";

export default function InvalidFeedbackPage() {
  return <main className="shell"><section className="form-card"><div className="kicker">Neurofeed</div><h1>Link unavailable</h1><p>This interaction link is invalid, expired, already used, or does not match the requested action.</p><Link href="/latest">Open Neurofeed</Link></section></main>;
}
