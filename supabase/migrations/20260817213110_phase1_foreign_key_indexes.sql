create index paper_social_signals_post_uri_idx on public.paper_social_signals (post_uri);
create index researcher_recommendations_author_id_idx on public.researcher_recommendations (author_id);
create index researcher_recommendations_bluesky_did_idx on public.researcher_recommendations (bluesky_did);
create index user_paper_events_digest_id_idx on public.user_paper_events (digest_id) where digest_id is not null;
create index user_researcher_events_bluesky_did_idx on public.user_researcher_events (bluesky_did);
create index user_researcher_events_recommendation_id_idx on public.user_researcher_events (recommendation_id) where recommendation_id is not null;
