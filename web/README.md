# Neurofeed web app

Thin Next.js App Router control surface over the canonical Supabase state.

## Routes

- `/login` — Supabase magic-link sign-in.
- `/onboarding` — Bluesky handle, research description, discovery balance, newsletter preference.
- `/latest` — finite current digest with web feedback.
- `/history` and `/history/[digestId]` — prior frozen digests.
- `/saved` — current Save state derived from append-only events.
- `/settings` — profile editing and Bluesky resync request.
- `/recommendation/[digestId]/[paperId]` — frozen score/provenance explanation.
- `/paper/[paperId]` — authenticated tracked paper redirect.
- `/r/[token]` — email CLICK token consumption and redirect.
- `/a/[token]` — non-mutating email action confirmation page; explicit POST consumes Save/More/Less.

The browser uses only the Supabase publishable key. `SUPABASE_SECRET_KEY` is imported only from server-only modules and is required for public signed email-action routes.

## Local environment

Copy `.env.example` to `.env.local` and fill in the publishable/secret keys. For production, `NEXT_PUBLIC_SITE_URL` should be the deployed web origin and the Phase 6 `NEUROFEED_BASE_URL` should point at the same origin so newsletter links resolve here.
