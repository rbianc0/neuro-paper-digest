# Neurofeed

Neurofeed is a personalized neuroscience-paper discovery service. A researcher's existing Bluesky network improves paper discovery; discovered papers can surface scientists worth knowing, while Bluesky remains the sole explicit follow graph.

The primary product is a finite curated email newsletter. The web app handles onboarding, settings, history, saved papers, and feedback.

## Architecture

```text
Vercel / Next.js / TypeScript
├── web UI + Supabase Auth
├── literature ingestion
├── Bluesky ingestion
├── embeddings + ranking
├── feedback learning
├── newsletter generation + SMTP delivery
└── Vercel Workflow orchestration
             │
             ▼
       Supabase/Postgres
       canonical state + pgvector
```

There is one application runtime. GitHub Actions is CI only.

## Product workflows

### New user

```text
finish onboarding
      ↓
embed research profile
      ↓
mirror Bluesky follow graph
      ↓
collect a bounded first slice of scholarly network signals
      ↓
rank shared literature
      ↓
generate first Neurofeed
      ↓
send first email
```

The workflow is durable and resumes at failed steps. A user does not run jobs manually.

### Shared literature

Vercel Cron starts a durable literature workflow every night at 01:37 UTC. It reads an overlapping eight-day OpenAlex neuroscience/psychology window, upserts canonical papers, and embeds new or changed records. The database invalidates embeddings when title/abstract/journal text changes.

### Shared Bluesky network

A second nightly workflow refreshes stale unique followed DIDs once globally, extracts scholarly links from posts/reposts/quotes, and materializes paper social signals. Neurofeed mirrors user follows; it does not create its own follow graph.

### Weekly newsletter

Every Monday at 06:15 UTC a durable workflow refreshes learned feedback, ranks unseen papers, freezes digest snapshots, generates constrained summaries with `gpt-5.6-luna`, and delivers generated issues through SMTP.

## Code

The application lives in `web/`.

- `web/app/` — Next.js UI, auth callbacks, email actions, cron entrypoints
- `web/lib/neurofeed/` — small domain functions for literature, Bluesky, ranking, feedback, and digests
- `web/workflows/` — durable orchestration
- `supabase/migrations/` — database schema, RLS, RPCs, pgvector indexes

The implementation deliberately favors direct functions and platform primitives over internal frameworks, service layers, or speculative abstractions.

## Local setup

```bash
cd web
cp .env.example .env.local
npm install
npm run dev
```

Validation:

```bash
npm audit --omit=dev --audit-level=high
npm run typecheck
npm run build
```

`SUPABASE_SECRET_KEY`, OpenAI/OpenAlex keys, SMTP credentials, and `CRON_SECRET` are server-only and must never be exposed through `NEXT_PUBLIC_*` variables.

## Scheduling

Production schedules live in `web/vercel.json`:

- nightly literature: `37 1 * * *`
- nightly Bluesky: `17 2 * * *`
- weekly newsletter: `15 6 * * 1`

Vercel Cron uses UTC.

## Next product phase

The next product feature is the small **Scientists Worth Knowing** section. It will identify high-confidence authors behind recommended literature and, where possible, resolve their Bluesky identity. Following remains an explicit action on Bluesky.
