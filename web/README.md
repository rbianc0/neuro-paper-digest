# Neurofeed application

The complete Neurofeed runtime lives here: Next.js UI, scientific discovery logic, newsletter generation, and Vercel Workflows.

## Routes

- `/login` — Supabase magic-link sign-in
- `/onboarding` — interests, discovery balance, newsletter preference, Bluesky handle; starts the first-digest workflow
- `/latest` — current finite digest and feedback
- `/history`, `/history/[digestId]` — frozen prior issues
- `/saved` — saved papers derived from append-only events
- `/settings` — profile settings and Bluesky refresh request
- `/recommendation/[digestId]/[paperId]` — ranking provenance
- `/paper/[paperId]` — authenticated tracked paper redirect
- `/r/[token]` — email click redirect
- `/action/save/[token]`, `/action/more/[token]`, `/action/less/[token]` — confirmation-first email actions
- `/api/cron/*` — authenticated Vercel Cron entrypoints that start durable workflows

## Runtime structure

- `lib/neurofeed/` — direct domain functions
- `workflows/` — durable user/bootstrap, literature, Bluesky, and newsletter orchestration
- `lib/supabase/` — browser/server/service Supabase clients

The browser receives only the Supabase publishable key. `SUPABASE_SECRET_KEY`, OpenAI/OpenAlex keys, SMTP credentials, and `CRON_SECRET` are server-only.

## Local setup

```bash
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
