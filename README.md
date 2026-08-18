# Neurofeed

Neurofeed is a personalized scientific-literature discovery service built around a researcher's existing Bluesky scientific network. The canonical MVP output is a finite weekly email newsletter; the web application is the stateful feedback and control layer.

The implementation source of truth is **Neurofeed MVP Product & Technical Specification v1**. Before the lab pilot, the repository optimizes for the target architecture rather than compatibility with the original prototype.

## Implemented foundation

### Phase 1 — database foundation

Supabase/PostgreSQL provides the canonical state, Auth integration points, pgvector, RLS, user feedback/digest state, shared Bluesky entities, and researcher-discovery entities. Migrations live under `supabase/migrations/`.

### Phase 2 — global literature ingestion

Literature acquisition is DB-first and shared across users:

```text
OpenAlex + bioRxiv
       ↓
deterministic deduplication
       ↓
Crossref / Europe PMC enrichment
       ↓
canonical identifiers + provenance
       ↓
Supabase papers / authors / sources
```

DOI, OpenAlex ID, PMID, preprint DOI, published DOI, and explicit preprint→publication mappings resolve into canonical papers. Historical duplicates can be merged atomically with provenance and downstream references preserved.

### Phase 3 — shared Bluesky ingestion

Bluesky is split into independent jobs:

```text
user Bluesky handle
       ↓
complete public follow-graph sync
       ↓
user_bluesky_follows
       ↓
unique actively-followed DIDs
       ↓
fetch each stale account once globally
       ↓
post/repost/quote scholarly events
       ↓
resolve DOI / PMID / scholarly URLs
       ↓
paper_social_signals
```

A repost is modeled as an attention event by the followed actor while the underlying post retains its original author. Partial/failed graph fetches never replace the last known complete graph. Bluesky remains the sole explicit researcher-follow graph.

### Phase 4 — user model and transparent ranking v1

Canonical papers and declared research profiles are embedded with a configurable embedding model. Current database vectors are 1536-dimensional and `config/ranking.yaml` defaults to `text-embedding-3-small`.

Ranking keeps the MVP score decomposition explicit:

- semantic relevance: 35%
- Bluesky network signal: 30%
- methods/species/profile fit: 10%
- scientific quality: 10%
- broad-discovery importance: 5%
- novelty: 5%
- recency: 5%

Bluesky authorship and discussion are separate signals. Social counts use saturation rather than linear popularity. Previously shown papers are suppressed, and broad discovery is selected as an explicit per-user lane rather than low-score leftovers.

`neurofeed-rank-user <user_id>` prints the full score decomposition without creating a digest.

### Phase 5 — feedback learning

Paper interactions are append-only events. SAVE/UNSAVE state is derived from event history, and effective positive/negative feedback feeds a conservative learned semantic preference vector. Declared interests remain the stable base representation while learned feedback ramps in as evidence accumulates.

### Phase 6 — weekly newsletter generation and pilot delivery

Weekly rankings are frozen into immutable digest snapshots before delivery. Each selected paper stores its score decomposition, generated summary, recommendation explanation, and action URLs. Newsletter summaries use `gpt-5.6-luna` with `xhigh` reasoning by default and are constrained to canonical metadata supplied by Neurofeed.

The pilot delivery layer is provider-neutral SMTP with Gmail defaults (`smtp.gmail.com:587` + STARTTLS). A dedicated Gmail account can therefore send the lab pilot without a custom domain. The sender records an IMPRESSION only after SMTP delivery succeeds.

`neurofeed-generate-digests` prepares the frozen weekly newsletter snapshots. `neurofeed-send-digests` sends already-generated snapshots without reranking them.

## Local backend setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install '.[dev]'

export OPENALEX_API_KEY='...'
export OPENAI_API_KEY='...'
export SUPABASE_URL='https://yajsdhpaobqtduazpkkd.supabase.co'
export SUPABASE_SECRET_KEY='...'
export CROSSREF_MAILTO='you@example.org'   # optional

neurofeed-sync-literature --lookback-days 8
neurofeed-embed
pytest -q
```

`SUPABASE_SECRET_KEY` and SMTP credentials are backend-only and must never be exposed to a browser.

## Configuration

- `config/literature.yaml`: global scholarly acquisition only.
- `config/ranking.yaml`: embedding model, transparent score weights, broad-discovery defaults, priority venues, and interpretable method/species aliases.
- `config/feedback.yaml`: event weights and learned-preference ramp.
- `config/newsletter.yaml`: digest structure, summary model, and presentation settings.

User interests are stored in Supabase profiles, not committed into global configuration.

## GitHub Actions

- `.github/workflows/collect.yml`: shared literature ingestion followed by embeddings.
- `.github/workflows/bluesky.yml`: complete user follow sync → unique stale-account ingestion → social-paper resolution.
- `.github/workflows/feedback.yml`: learned preference refresh.
- `.github/workflows/newsletter.yml`: generate frozen weekly digests and deliver them through the configured SMTP account.
- `.github/workflows/test.yml`: unit tests on pushes and pull requests.

Required repository secrets for the active backend jobs:

- `OPENALEX_API_KEY`
- `OPENAI_API_KEY`
- `SUPABASE_SECRET_KEY`
- `NEUROFEED_SMTP_PASSWORD` once newsletter delivery is enabled

Repository variables used by newsletter delivery:

- `NEUROFEED_SMTP_USERNAME`
- `NEUROFEED_EMAIL_FROM`
- `NEUROFEED_PUBLIC_URL` after the web app receives its Vercel URL
- `CROSSREF_MAILTO` (optional)

## Next canonical phase

Phase 7 builds the lightweight web application for onboarding, preferences, saved papers, history, and safe confirmation of state-changing email actions. Phase 8 then adds the small “Scientists Worth Knowing” section without creating a competing researcher-follow graph.
