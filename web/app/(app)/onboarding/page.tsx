import { requireUser } from "@/lib/auth";
import { saveOnboarding } from "./actions";

export default async function OnboardingPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const { supabase, user } = await requireUser();
  const params = await searchParams;
  const { data: profile } = await supabase.from("profiles").select("bluesky_handle,research_description,discovery_balance,newsletter_enabled").eq("user_id", user.id).maybeSingle();

  return (
    <section className="form-card" style={{ marginTop: 0 }}>
      <div className="kicker">Initial setup</div>
      <h1>Build your research profile</h1>
      <p className="muted">Your Bluesky follows remain the only explicit researcher network. Neurofeed mirrors that public graph; it does not create another follow list.</p>
      {params.error ? <p className="error">{params.error}</p> : null}
      <form action={saveOnboarding} className="form-grid">
        <label>
          Bluesky handle
          <input name="bluesky_handle" placeholder="name.bsky.social" defaultValue={profile?.bluesky_handle || ""} required />
        </label>
        <label>
          Research interests
          <textarea name="research_description" placeholder="Topics, methods, modalities, species, clinical/basic interests…" defaultValue={profile?.research_description || ""} required />
        </label>
        <label>
          Broader-discovery share
          <input name="discovery_balance" type="number" min="0" max="1" step="0.05" defaultValue={String(profile?.discovery_balance ?? 0.25)} />
          <small>0.25 means roughly 75% focused recommendations and 25% deliberate broader discovery.</small>
        </label>
        <label style={{ display: "flex", gridTemplateColumns: "auto 1fr", alignItems: "center" }}>
          <input style={{ width: "auto" }} name="newsletter_enabled" type="checkbox" defaultChecked={profile?.newsletter_enabled ?? true} />
          Receive the weekly Neurofeed newsletter
        </label>
        <button type="submit">Save and continue</button>
      </form>
    </section>
  );
}
