-- Follow-up to the initial Phase 1 migration after running Supabase database advisors.
-- IF NOT EXISTS keeps this migration safe when replayed after the repository's
-- consolidated Phase 1 foundation migration.

create index if not exists paper_social_signals_post_uri_idx
  on public.paper_social_signals (post_uri);

create index if not exists researcher_recommendations_author_id_idx
  on public.researcher_recommendations (author_id);

create index if not exists researcher_recommendations_bluesky_did_idx
  on public.researcher_recommendations (bluesky_did);

create index if not exists user_paper_events_digest_id_idx
  on public.user_paper_events (digest_id);

create index if not exists user_researcher_events_bluesky_did_idx
  on public.user_researcher_events (bluesky_did);

create index if not exists user_researcher_events_recommendation_id_idx
  on public.user_researcher_events (recommendation_id);
