# Neurofeed target architecture and repository map

This repository started as the deterministic `neuro-paper-digest` collector. The Neurofeed MVP specification keeps the working acquisition/deduplication logic, but changes the system from a single-user JSON-first pipeline to a shared DB-first product architecture.

## Target architecture

```text
                           ┌───────────────────────────┐
                           │       Supabase Auth       │
                           └─────────────┬─────────────┘
                                         │
                                         ▼
┌────────────────────────────────────────────────────────────────────┐
│                    PostgreSQL / Supabase                           │
│                                                                    │
│ canonical literature     shared Bluesky       user state           │
│ papers                   accounts/posts       profiles             │
│ paper_sources            paper_social_signals follows              │
│ authors/paper_authors                         feedback/events       │
│                                                digests              │
└───────────┬──────────────────────┬───────────────────────┬──────────┘
            │                      │                       │
            │                      │                       │
            ▼                      ▼                       ▼
 global literature jobs     shared Bluesky jobs      ranking/digest jobs
 OpenAlex                   follow sync              semantic candidates
 bioRxiv                    unique-account sync      network scoring
 Crossref                   link resolution          feedback adjustment
 Europe PMC                 identity resolution      newsletter snapshot
            │                      │                       │
            └──────────────────────┴───────────┬───────────┘
                                               ▼
                                   Next.js web + email delivery
```

The database is the canonical state. Generated JSON/Markdown files are compatibility/debug artifacts only and should no longer be treated as the product data store once Phase 2 lands.

## Current repository -> target architecture

| Current path | What it does now | Target ownership | Phase |
|---|---|---|---|
| `src/neuro_digest/sources/openalex.py` | OpenAlex discovery/enrichment | `literature/openalex` global collector | Phase 2 |
| `src/neuro_digest/sources/biorxiv.py` | bioRxiv preprint/publication acquisition | `literature/biorxiv` global collector | Phase 2 |
| `src/neuro_digest/dedupe.py` | deterministic DOI/ID/title+author dedupe | canonical literature service | Phase 2 |
| `src/neuro_digest/resolve.py` | bounded scholarly webpage metadata resolution | literature/social resolution helper | Phase 2/3 |
| `src/neuro_digest/sources/bluesky.py` | fetch one user's follows and all followed feeds | split into `sync_user_follow_graphs` + `sync_bluesky_accounts` | Phase 3 |
| `src/neuro_digest/models.py` | transient `Candidate` and `BlueskySignal` dataclasses | ingestion DTOs; persisted entities live in Postgres | Phase 2/3 |
| `src/neuro_digest/pipeline.py` | orchestrates acquisition, dedupe, social resolution, history, output | decomposed into idempotent scheduled jobs | Phase 2-6 |
| `config/interests.yaml` | one hard-coded user's interests and crawl settings | onboarding/profile defaults + job config; no hard-coded user | Phase 4 |
| `.github/workflows/collect.yml` | one weekly all-in-one collector | multiple logical scheduled jobs, initially still GitHub Actions | Phase 2/3 |
| `data/*.json`, `docs/latest_candidates.json` | canonical-ish weekly state | compatibility/debug output only | deprecated after Phase 2 |

## Required job boundaries

The MVP specification defines these logical jobs. The first implementation can keep them in one Python package and GitHub Actions, but the boundaries should remain explicit and independently runnable/idempotent:

1. `sync_literature` — global OpenAlex/bioRxiv/Crossref/Europe PMC acquisition and canonicalization.
2. `sync_user_follow_graphs` — resolve each user's Bluesky handle/DID and mirror active follows.
3. `sync_bluesky_accounts` — fetch stale unique DIDs once globally, irrespective of how many Neurofeed users follow them.
4. `resolve_social_papers` — resolve scholarly links/posts into canonical `papers` + `paper_social_signals`.
5. `resolve_researcher_identities` — confidence-scored author ↔ Bluesky identity mapping.
6. `embed_new_papers` — embedding generation after a model is selected.
7. `generate_weekly_digests` — candidate union, decomposed scoring, section assignment and immutable score/explanation snapshots.
8. `send_weekly_digests` — transactional email delivery and delivery state.

## Phase 1 database decisions

The Phase 1 schema lives under `supabase/migrations/` and is also applied to the connected Supabase project.

- `auth.users` is the authentication source of truth; `public.profiles.user_id` references it 1:1.
- `profiles`, preferences, follows, digests, and feedback events are user-specific and RLS protected.
- literature and cached public Bluesky metadata are shared globally.
- worker-owned tables (`bluesky_posts`, `paper_social_signals`, `researcher_identities`, `user_embeddings`) are not writable/readable from ordinary clients; scheduled backend jobs use a server-side secret/service role only.
- `user_bluesky_follows` is a mirror, not a competing follow graph. The client has read-only access to its own rows.
- pgvector is enabled. Embedding columns intentionally use unbounded `vector` in Phase 1 so the schema does not lock an embedding model/dimension prematurely. Phase 4 should fix the dimension and add an ANN index once the model is selected.
- score components are persisted in `digest_items` so the lab pilot can compare semantic-only and Bluesky-assisted recommendations reproducibly.
- `researcher_recommendations` and `user_researcher_events` preserve the paper → scientist → later Bluesky follow loop.

## Immediate Phase 2 refactor sequence

1. Introduce a database repository layer and configuration for server-side Supabase/Postgres access.
2. Keep existing source clients and deterministic dedupe tests intact.
3. Change literature ingestion from returning/writing one weekly candidate list to idempotent upserts into `papers`, `paper_sources`, `authors`, and `paper_authors`.
4. Add Crossref and Europe PMC enrichment behind the same canonicalization layer.
5. Retain JSON/Markdown output temporarily as a diagnostic export generated from the database.
6. Only after the literature path is DB-first, split the current Bluesky crawler into per-user follow synchronization and shared unique-account ingestion.

## Non-negotiable product boundaries

- Bluesky remains the sole explicit researcher-follow graph.
- literature and Bluesky acquisition are shared across users.
- LLMs do not determine bibliographic existence or canonical identity.
- recommendation score provenance must remain auditable.
- the newsletter is the primary delivery surface; the web app is the state/feedback/control surface.
