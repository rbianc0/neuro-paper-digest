# Neurofeed

Neurofeed is a personalized scientific-literature discovery service built around a researcher's existing Bluesky scientific network. The canonical MVP output is a finite weekly email newsletter; the web application is the stateful feedback and control layer.

This repository contains the Python ingestion and ranking backend. The implementation source of truth is **Neurofeed MVP Product & Technical Specification v1**.

## Implemented architecture

### Phase 1 — database foundation

Supabase/PostgreSQL owns canonical literature, user/preferences, shared Bluesky state, digest/feedback entities, researcher identity, pgvector, Auth integration points and RLS boundaries.

### Phase 2 — global literature layer

OpenAlex Neuroscience/Psychology + bioRxiv are acquired globally once, enriched through Crossref/Europe PMC and deterministically canonicalized. DOI/OpenAlex/PMID aliases and later preprint→publication mappings resolve to one paper object.

### Phase 3 — shared Bluesky layer

User handles resolve to stable DIDs. Complete public follow graphs are mirrored atomically, stale actively-followed DIDs are fetched once globally, scholarly links are retained durably, and only resolved links become canonical `paper_social_signals`.

### Phase 4 — user model and ranking v1

Paper and declared-profile embeddings use `text-embedding-3-small` at 1,536 dimensions. Paper embeddings are indexed with pgvector HNSW cosine search and invalidated automatically when title/abstract/venue text changes.

The candidate union is:

```text
semantic nearest neighbours
       ∪
Bluesky network papers
       ∪
broader-discovery papers
       ↓
seen-paper suppression
       ↓
decomposed ranking
       ↓
focused + broad lanes
```

Initial ranking weights remain configuration and match the MVP hypotheses:

```text
semantic relevance       35%
Bluesky network signal   30%
method/species fit       10%
priority/quality prior   10%
broad importance          5%
novelty                   5%
recency                   5%
```

The `quality_score` is deliberately an interpretable v1 priority prior (venue + small citation signal), not a claim of objective scientific quality.

Declared research interests remain the anchor. Learned positive/negative embeddings are already supported by the ranker, but their contribution grows only with feedback maturity and will be populated in Phase 5.

Controlled serendipity uses `profiles.discovery_balance` (default 0.25) to reserve an explicit broad-discovery share rather than filling it with low-ranked leftovers.

## Jobs

```bash
neurofeed-sync-literature
neurofeed-sync-follow-graphs
neurofeed-sync-bluesky-accounts
neurofeed-resolve-social-papers
neurofeed-embed-new-papers
neurofeed-refresh-user-models
neurofeed-rank-user --user-id <uuid>
```

## Scheduled workflows

- `collect.yml` — weekly global literature ingestion.
- `bluesky.yml` — daily shared Bluesky synchronization and social-paper resolution.
- `models.yml` — daily incremental paper embeddings and declared user-model refresh.

## Server environment

Required secrets:

- `SUPABASE_SECRET_KEY`
- `OPENALEX_API_KEY`
- `OPENAI_API_KEY`

Optional repository variable:

- `CROSSREF_MAILTO`

`SUPABASE_SECRET_KEY` and `OPENAI_API_KEY` are backend-only and must never be exposed to a browser/client.

## Next phase

Phase 5 adds feedback endpoints/state transitions and computes learned positive/negative preference representations from click/save/more/less behavior. Phase 6 then freezes ranked results into reproducible digest snapshots and sends the newsletter.
