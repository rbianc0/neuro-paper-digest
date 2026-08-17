# Neurofeed

Neurofeed is a personalized scientific-literature discovery service built around the research network a scientist already maintains on Bluesky. The repository began as `neuro-paper-digest`, a deterministic weekly collector, and is being evolved into the lab-testable Neurofeed MVP.

The canonical product behavior is: shared scholarly acquisition + shared Bluesky ingestion → canonical papers → personalized semantic/network ranking → weekly email newsletter → user feedback → improved ranking, with a reverse paper → scientist → Bluesky-follow discovery loop.

## Current implementation status

**Phase 1 — database foundation: implemented on the `agent/neurofeed-phase1` branch.**

- Supabase/PostgreSQL schema for users, preferences, canonical literature, Bluesky cache, social signals, recommendations, feedback, digests, and scientist discovery.
- pgvector enabled for future semantic representations.
- Row Level Security enabled on every public table with client access scoped to the MVP access model.
- Supabase Auth is the user identity source of truth.
- Existing collector mapped onto the target DB-first/shared-ingestion architecture in [`docs/architecture.md`](docs/architecture.md).

The existing Python acquisition code remains intact while Phase 2 converts literature acquisition from JSON-first to DB-first.

## Existing collector capabilities

The prototype currently:

1. queries OpenAlex using focused and broader-discovery queries;
2. collects neuroscience preprints and publication mappings from bioRxiv;
3. reads a public Bluesky follow graph and followed-account feeds;
4. extracts DOI/PubMed/bioRxiv/publisher links from posts/reposts/quotes;
5. enriches identifiers through OpenAlex and bounded metadata resolution;
6. deterministically deduplicates DOI → preprint/publication relation → OpenAlex/PMID → exact title → high title similarity + author overlap;
7. exports weekly JSON/Markdown candidate snapshots.

Those collector components are inputs to the new architecture, not discarded work.

## Target architecture

See [`docs/architecture.md`](docs/architecture.md) for the concrete current-path → target-module map and job boundaries.

The central architectural changes are:

- PostgreSQL/Supabase becomes canonical state rather than generated JSON.
- literature is acquired globally once rather than per user;
- Bluesky account feeds are fetched once per unique DID across all Neurofeed users;
- a user's Bluesky follows remain only a mirror of Bluesky, never an internal competing follow graph;
- recommendation and feedback state are persisted with score provenance;
- the weekly newsletter remains the primary product output.

## Supabase

The reproducible Phase 1 schema is in:

```text
supabase/migrations/20260817210900_phase1_database_foundation.sql
```

For local/CI/backend jobs, keep privileged Supabase credentials server-side only. Never expose a service-role/secret key to a browser client.

Embedding columns are intentionally dimensionless in Phase 1. Once the embedding model is selected in Phase 4, lock the vector dimension and add the appropriate ANN index.

## Prototype local run

The pre-DB collector is still runnable during the migration:

```bash
python -m venv .venv
source .venv/bin/activate
pip install '.[dev]'
export OPENALEX_API_KEY='...'
neuro-digest --lookback-days 7
pytest -q
```

## Current secrets

Do not commit API keys.

- `OPENALEX_API_KEY` — used by the existing OpenAlex collector.
- Supabase server-side credentials will be introduced with the Phase 2 database repository layer.

Bluesky public reads and the bioRxiv API currently do not require user credentials.

## Existing GitHub Actions

`.github/workflows/collect.yml` still runs the legacy weekly all-in-one collector. It will be decomposed as the implementation proceeds into the logical jobs defined by the MVP specification:

- `sync_literature`
- `sync_user_follow_graphs`
- `sync_bluesky_accounts`
- `resolve_social_papers`
- `resolve_researcher_identities`
- `embed_new_papers`
- `generate_weekly_digests`
- `send_weekly_digests`

Generated `data/` and `docs/latest_candidates.json` outputs should be treated as compatibility/debug artifacts once Phase 2 makes literature ingestion DB-first.
