# Neurofeed

Neurofeed is a personalized scientific-literature discovery service built around a researcher's existing Bluesky scientific network. The primary MVP output is a finite weekly email newsletter; the web application is the stateful feedback/control layer.

This repository contains the Python ingestion, feedback-learning, ranking, digest-generation, and email-delivery backend. The implementation source of truth is **Neurofeed MVP Product & Technical Specification v1**.

## Implemented through Phase 6

1. **Database foundation** — Supabase/PostgreSQL, Auth-linked profiles, pgvector, RLS and canonical product state.
2. **Global literature** — shared OpenAlex/bioRxiv acquisition, Crossref/Europe PMC enrichment, deterministic canonicalization and cross-week identifier merging.
3. **Shared Bluesky** — public follow synchronization, stable DIDs, unique-account feed ingestion, durable scholarly links and canonical social signals.
4. **User model + ranking** — 1,536-dimensional semantic retrieval, decomposed semantic+Bluesky scoring and controlled broader discovery.
5. **Feedback learning** — append-only events, current Save state, positive/negative semantic centroids and signed learned method/species features.
6. **Newsletter** — immutable weekly digest snapshots, structured summaries, deterministic recommendation explanations, per-user interaction tokens and idempotent email delivery.

## Phase 6 digest contract

A digest is frozen before delivery:

```text
ranked unique papers
      ↓
one presentation section each
      ↓
canonical paper metadata + authors
      ↓
summary from supplied metadata/abstract only
      ↓
score/provenance snapshot
      ↓
per-user random interaction URLs
      ↓
rendered HTML/text + content hash
      ↓
GENERATED
      ↓
idempotent email send
      ↓
SENT
```

The summarizer never decides whether a paper exists and receives no web-search capability. `why_recommended` is deterministic from the stored ranking components/provenance.

Raw interaction tokens are never stored as dedicated token rows: only SHA-256 hashes are stored in `interaction_tokens`; the raw values appear in the exact newsletter HTML/text delivered to that user. Read-paper tokens create weak CLICK events and redirect. Save/More/Less tokens are single-use and must be explicitly POST-confirmed by the Phase 7 web route; opening the email link alone does not change preference state.

The same `(user, period, version)` digest is not silently regenerated. A new editorial/ranking version must use a new digest version, preserving reproducibility.

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
neurofeed-generate-weekly-digests
neurofeed-send-weekly-digests
```

## Scheduled workflows

- `collect.yml` — Monday global literature ingestion.
- `bluesky.yml` — daily shared Bluesky synchronization/resolution.
- `models.yml` — daily paper embeddings + declared/learned user model refresh.
- `newsletter.yml` — Monday digest freeze followed by email delivery.

## Required server configuration

Secrets: `SUPABASE_SECRET_KEY`, `OPENALEX_API_KEY`, `OPENAI_API_KEY`, `RESEND_API_KEY`.

Repository/environment variables: `CROSSREF_MAILTO` (optional), `NEUROFEED_FROM_EMAIL`, `NEUROFEED_BASE_URL`.

## Next phase

Phase 7 is the lightweight Next.js application: magic-link authentication, onboarding, latest/history/saved/settings, recommendation explanations, `/r/<token>` read redirects, and `/a/<token>` confirmation+POST feedback actions.
