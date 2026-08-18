# Neurofeed

Neurofeed is a personalized scientific-literature discovery service built around a researcher's existing Bluesky scientific network. The primary MVP output is a finite weekly email newsletter; the web application is the stateful feedback/control layer.

This repository now contains the Python backend plus the lightweight Next.js web control surface. The implementation source of truth is **Neurofeed MVP Product & Technical Specification v1**.

## Implemented through Phase 7

1. **Database foundation** — Supabase/PostgreSQL, Auth-linked profiles, pgvector, RLS and canonical product state.
2. **Global literature** — shared OpenAlex/bioRxiv acquisition, Crossref/Europe PMC enrichment, deterministic canonicalization and cross-week identifier merging.
3. **Shared Bluesky** — public follow synchronization, stable DIDs, unique-account feed ingestion, durable scholarly links and canonical social signals.
4. **User model + ranking** — 1,536-dimensional semantic retrieval, decomposed semantic+Bluesky scoring and controlled broader discovery.
5. **Feedback learning** — append-only events, current Save state, positive/negative semantic centroids and signed learned method/species features.
6. **Newsletter** — immutable weekly digest snapshots, structured summaries, deterministic explanations, hashed interaction tokens and idempotent email delivery.
7. **Web control surface** — magic-link auth, onboarding, latest/history/saved/settings, recommendation explanations, tracked reads and safe email-action confirmation routes.

## Product boundary

The web app is intentionally not an infinite feed. `/latest` renders the current finite digest; history and saved papers are explicit memory surfaces. Bluesky remains the sole researcher-follow graph. A web Settings resync request is queued into the same shared follow-sync pipeline rather than crawling Bluesky in the browser.

## Web feedback

Authenticated web interactions call the same append-only event RPC used by the learning layer. A lightweight client impression tracker records digest exposure once per browser session. Read-paper redirects record CLICK before leaving Neurofeed. Save/More/Less use server actions and optional Less reasons.

Email state-changing links remain safe against automatic GET prefetch: `/a/<token>` only inspects the server-only hashed token and asks for confirmation; the explicit form POST consumes it. `/r/<token>` can consume CLICK on GET because CLICK is intentionally weak/noisy and non-single-use.

## Scheduled backend jobs

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

## Web development

```bash
cd web
npm ci
npm run typecheck
npm run build
```

The Phase 7 branch workflow generates and commits `web/package-lock.json` from exact pinned package versions before validating the production build.

## Next phase

Phase 8 adds conservative researcher identity resolution and the sparse **Scientists Worth Knowing** section. Phase 9 then prepares the lab pilot, instrumentation review, onboarding cohort and ranking/newsletter tuning.
