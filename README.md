# Neurofeed

Neurofeed is a personalized scientific-literature discovery service built around a researcher's existing Bluesky scientific network. The canonical MVP output is a finite weekly email newsletter; the web application is the stateful feedback and control layer.

This repository contains the Python ingestion backend. The implementation source of truth is **Neurofeed MVP Product & Technical Specification v1**.

## Implemented architecture

### Phase 1 — database foundation

Supabase/PostgreSQL contains the canonical MVP schema, pgvector, Supabase Auth integration points, RLS, shared literature state, shared Bluesky state, digest/feedback entities, and researcher-discovery entities.

### Phase 2 — global literature layer

```text
OpenAlex Neuroscience/Psychology + bioRxiv
                  ↓
 deterministic canonicalization
                  ↓
 Crossref / Europe PMC enrichment
                  ↓
               Supabase
```

Literature is acquired globally once. `paper_identifiers` and the service-only `merge_papers` operation preserve one scientific object across DOI/OpenAlex/PMID aliases and later preprint→publication mappings.

### Phase 3 — shared Bluesky layer

```text
Neurofeed profiles
      ↓
resolve handle → stable DID
      ↓
public Bluesky follow graph
      ↓
user_bluesky_follows
      │
      └──────────────┐
                     ▼
        unique active followed DIDs
                     ↓
        fetch each stale account once
                     ↓
      posts + actor attention events
                     ↓
        normalized scholarly links
                     ↓
       canonical paper resolution
                     ↓
          paper_social_signals
```

The same followed researcher is fetched once regardless of how many Neurofeed users follow them. Follow-graph replacement is atomic: the database is changed only after a complete successful public follow fetch. Failed account fetches use bounded exponential backoff.

Raw network attention is stored separately from resolved paper signals:

- `bluesky_posts`: underlying post objects;
- `bluesky_post_events`: which followed DID posted/reposted/quoted a post and when;
- `bluesky_scholarly_links`: DOI/PMID/scholarly URLs plus durable resolution state;
- `paper_social_signals`: only links that have resolved to canonical papers.

This means an unresolved publisher URL is not discarded and can be retried later.

## Jobs

### Literature

```bash
neurofeed-sync-literature --lookback-days 8
```

### Bluesky follow graphs

```bash
neurofeed-sync-follow-graphs
```

### Shared stale-account cache

```bash
neurofeed-sync-bluesky-accounts \
  --stale-hours 22 \
  --lookback-days 8 \
  --batch-size 1000 \
  --max-workers 8
```

### Social paper resolution

```bash
neurofeed-resolve-social-papers --limit 2000
```

The Bluesky jobs use public reads only. Neurofeed does not request Bluesky passwords and does not create follows; Bluesky remains the source of truth for the researcher graph.

## Environment

```bash
export OPENALEX_API_KEY='...'
export SUPABASE_URL='https://yajsdhpaobqtduazpkkd.supabase.co'
export SUPABASE_SECRET_KEY='...'
export CROSSREF_MAILTO='you@example.org'   # optional
```

`SUPABASE_SECRET_KEY` is server-only and must never be exposed to a browser/client.

## GitHub Actions

- `.github/workflows/collect.yml` — weekly global literature ingestion.
- `.github/workflows/bluesky.yml` — daily follow synchronization, unique-account feed refresh, and social-paper resolution.

Both workflows use the same canonical Supabase state. Generated JSON is diagnostic only; Git is not the database.

Required repository secrets:

- `OPENALEX_API_KEY`
- `SUPABASE_SECRET_KEY`

Optional repository variable:

- `CROSSREF_MAILTO`

## Next phase

Phase 4 adds the user representation and transparent ranking model: declared research profile, embeddings, semantic candidates, Bluesky subscore, broader-discovery lane, and decomposed recommendation scores. No recommendation or newsletter logic belongs in the ingestion services above.
