import { requireOnboardedUser } from "@/lib/profile";
import { requestBlueskyResync, updateSettings } from "./actions";

function formatDate(value: string | null) {
  if (!value) return "Not yet synchronized";
  return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export default async function SettingsPage({ searchParams }: { searchParams: Promise<{ saved?: string; sync?: string; error?: string }> }) {
  const { profile } = await requireOnboardedUser();
  const params = await searchParams;

  return (
    <div className="stack">
      <header>
        <div className="kicker">Control layer</div>
        <h1>Settings</h1>
      </header>
      {params.saved ? <p className="notice">Settings updated.</p> : null}
      {params.sync ? <p className="notice">Bluesky resynchronization requested. The shared backend will process it on the next sync run.</p> : null}
      {params.error ? <p className="error">{params.error}</p> : null}

      <section className="card">
        <form action={updateSettings} className="form-grid">
          <label>
            Bluesky handle
            <input name="bluesky_handle" defaultValue={profile.bluesky_handle || ""} required />
          </label>
          <label>
            Research interests
            <textarea name="research_description" defaultValue={profile.research_description || ""} required />
          </label>
          <label>
            Broader-discovery share
            <input name="discovery_balance" type="number" min="0" max="1" step="0.05" defaultValue={String(profile.discovery_balance ?? 0.25)} />
          </label>
          <label style={{ display: "flex", gridTemplateColumns: "auto 1fr", alignItems: "center" }}>
            <input style={{ width: "auto" }} name="newsletter_enabled" type="checkbox" defaultChecked={profile.newsletter_enabled} />
            Weekly newsletter enabled
          </label>
          <button type="submit">Save settings</button>
        </form>
      </section>

      <section className="card stack">
        <div>
          <h2 style={{ marginTop: 0 }}>Bluesky network status</h2>
          <p className="muted">Last successful sync: {formatDate(profile.last_bluesky_sync_at)}</p>
          {profile.last_bluesky_sync_error ? <p className="error">Last sync error: {profile.last_bluesky_sync_error}</p> : null}
          {profile.bluesky_sync_requested_at ? <p className="notice">A refresh is currently requested.</p> : null}
        </div>
        <form action={requestBlueskyResync}>
          <button className="secondary" type="submit">Request Bluesky resync</button>
        </form>
      </section>
    </div>
  );
}
