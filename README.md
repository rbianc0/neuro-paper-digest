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

`neurofeed-rank-user <user_id>` prints the full score decomposition without creating a digest. Digest persistence/presentation remains Phase 6.

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

`SUPABASE_SECRET_KEY` is backend-only and must never be exposed to a browser.

## Configuration

- `config/literature.yaml`: global scholarly acquisition only.
- `config/ranking.yaml`: embedding model, transparent score weights, broad-discovery defaults, priority venues, and interpretable method/species aliases.

User interests are stored in Supabase profiles, not committed into global configuration.

## GitHub Actions

- `.github/workflows/collect.yml`: shared literature ingestion followed by embeddings.
- `.github/workflows/bluesky.yml`: complete user follow sync → unique stale-account ingestion → social-paper resolution.
- `.github/workflows/test.yml`: unit tests on pushes and pull requests.

Required repository secrets for the active backend jobs:

- `OPENALEX_API_KEY`
- `OPENAI_API_KEY`
- `SUPABASE_SECRET_KEY`

Optional repository variable:

- `CROSSREF_MAILTO`

## Next canonical phase

Phase 5 adds feedback endpoints/state transitions and learned preference representation. Phase 6 then snapshots rankings into weekly digests, generates explanations/summaries, signs email actions, and sends the newsletter.
