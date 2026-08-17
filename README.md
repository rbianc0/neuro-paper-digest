# Neurofeed

Neurofeed is a personalized scientific-literature discovery service built around a researcher's existing Bluesky scientific network. The primary MVP output is a finite weekly email newsletter; the web application is the stateful feedback and control layer.

This repository contains the Python ingestion, feedback-learning, and ranking backend. The implementation source of truth is **Neurofeed MVP Product & Technical Specification v1**.

## Implemented through Phase 5

### Phase 1 — database foundation
Supabase/PostgreSQL owns canonical literature, user state, shared Bluesky state, digest/feedback entities, pgvector, Auth integration points and RLS boundaries.

### Phase 2 — global literature
OpenAlex Neuroscience/Psychology + bioRxiv are acquired globally once, enriched through Crossref/Europe PMC, and canonicalized across DOI/OpenAlex/PMID/preprint-publication aliases.

### Phase 3 — shared Bluesky
Handles resolve to stable DIDs. Complete public follow graphs are mirrored atomically, stale actively-followed DIDs are fetched once globally, scholarly links remain durable until resolved, and only resolved links become paper social signals.

### Phase 4 — user model + ranking
`text-embedding-3-small` 1,536-dimensional paper/profile embeddings feed pgvector HNSW cosine retrieval. Candidate ranking remains decomposed and configurable: semantic 35%, Bluesky 30%, method/species fit 10%, priority prior 10%, broad importance 5%, novelty 5%, recency 5%. Controlled serendipity uses the user's `discovery_balance` rather than low-score leftovers.

### Phase 5 — feedback learning
Feedback is append-only and interpretable:

```text
IMPRESSION / CLICK / SAVE / UNSAVE / MORE / LESS
                       ↓
           effective paper feedback
                       ↓
      positive + negative embedding centroids
                       +
          learned signed feature weights
                       ↓
              future Phase 4 ranking
```

Current Save state is derived from the event stream through a security-invoker view. The authenticated event RPC derives user identity from `auth.uid()`; callers do not supply a trusted user ID.

Initial feedback weights are configuration, not product truth:

- click: weak positive (`0.25`)
- current saved state: strong positive (`1.0`)
- More like this: strongest positive (`1.5`)
- Less like this: strong negative (`-1.5`)

Repeated clicks do not stack, SAVE/UNSAVE is reduced to current state, and the latest explicit More/Less action wins. `already_knew_it` is neutral for preference learning: it still records the user action but does not teach the system that the paper's topic/method/species is unwanted.

Learned positive/negative semantic centroids are rebuilt from canonical paper embeddings and normalized. Learned method/species features are signed and saturating, while the declared profile remains the anchor; Phase 4 only increases the learned semantic contribution gradually as `feedback_count` grows.

## Jobs

```bash
neurofeed-sync-literature
neurofeed-sync-follow-graphs
neurofeed-sync-bluesky-accounts
neurofeed-resolve-social-papers
neurofeed-embed-new-papers
neurofeed-refresh-user-models
neurofeed-refresh-feedback-models
neurofeed-rank-user --user-id <uuid>
```

## Scheduled workflows

- `collect.yml` — weekly global literature ingestion.
- `bluesky.yml` — daily shared Bluesky synchronization and social-paper resolution.
- `models.yml` — daily paper embeddings, declared user model refresh, then learned-feedback model rebuild.

## Server secrets

Required: `SUPABASE_SECRET_KEY`, `OPENALEX_API_KEY`, `OPENAI_API_KEY`. Optional repository variable: `CROSSREF_MAILTO`.

## Next phase

Phase 6 freezes ranked papers and score provenance into reproducible weekly digest snapshots, generates concise scientific summaries/explanations, creates safe interaction links, and sends the newsletter.
