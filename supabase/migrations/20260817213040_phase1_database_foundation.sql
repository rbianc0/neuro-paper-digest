create extension if not exists vector with schema extensions;

create schema if not exists private;
revoke all on schema private from public;
revoke all on schema private from anon, authenticated;

create type public.preference_source as enum ('DECLARED', 'INFERRED', 'LEARNED');
create type public.researcher_identity_status as enum ('CONFIRMED', 'HIGH_CONFIDENCE', 'AMBIGUOUS', 'UNKNOWN');
create type public.paper_event_type as enum ('IMPRESSION', 'CLICK', 'SAVE', 'UNSAVE', 'MORE_LIKE_THIS', 'LESS_LIKE_THIS');
create type public.researcher_event_type as enum ('RESEARCHER_RECOMMENDED', 'VIEW_BLUESKY', 'LATER_FOLLOWED');
create type public.bluesky_post_type as enum ('POST', 'REPOST', 'QUOTE');

create function private.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;
revoke all on function private.set_updated_at() from public, anon, authenticated;

create table public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  email text,
  display_name text,
  bluesky_did text,
  bluesky_handle text,
  research_description text,
  discovery_balance numeric(4,3) not null default 0.250 check (discovery_balance between 0 and 1),
  newsletter_enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index profiles_bluesky_did_key on public.profiles (bluesky_did) where bluesky_did is not null;

create table public.user_preference_features (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  feature_type text not null,
  feature_value text not null,
  weight double precision not null default 1.0,
  source public.preference_source not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, feature_type, feature_value, source)
);

create table public.user_embeddings (
  user_id uuid primary key references public.profiles(user_id) on delete cascade,
  declared_embedding extensions.vector,
  learned_positive_embedding extensions.vector,
  learned_negative_embedding extensions.vector,
  embedding_model text,
  feedback_count integer not null default 0 check (feedback_count >= 0),
  updated_at timestamptz not null default now()
);

create table public.papers (
  id uuid primary key default gen_random_uuid(),
  canonical_doi text,
  title text,
  abstract text,
  journal text,
  publication_date date,
  first_online_date date,
  openalex_id text,
  pmid text,
  preprint_doi text,
  published_doi text,
  cited_by_count integer check (cited_by_count is null or cited_by_count >= 0),
  embedding extensions.vector,
  embedding_model text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index papers_canonical_doi_key on public.papers (lower(canonical_doi)) where canonical_doi is not null;
create unique index papers_openalex_id_key on public.papers (openalex_id) where openalex_id is not null;
create unique index papers_pmid_key on public.papers (pmid) where pmid is not null;
create unique index papers_preprint_doi_key on public.papers (lower(preprint_doi)) where preprint_doi is not null;
create unique index papers_published_doi_key on public.papers (lower(published_doi)) where published_doi is not null;
create index papers_publication_date_idx on public.papers (publication_date desc nulls last);
create index papers_first_online_date_idx on public.papers (first_online_date desc nulls last);

create table public.paper_sources (
  id uuid primary key default gen_random_uuid(),
  paper_id uuid not null references public.papers(id) on delete cascade,
  source_type text not null,
  external_id text,
  source_url text,
  metadata jsonb not null default '{}'::jsonb,
  retrieved_at timestamptz not null default now()
);
create index paper_sources_paper_id_idx on public.paper_sources (paper_id);
create unique index paper_sources_external_key on public.paper_sources (source_type, external_id) where external_id is not null;

create table public.authors (
  id uuid primary key default gen_random_uuid(),
  canonical_name text not null,
  openalex_id text,
  orcid text,
  affiliation_metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index authors_openalex_id_key on public.authors (openalex_id) where openalex_id is not null;
create unique index authors_orcid_key on public.authors (lower(orcid)) where orcid is not null;

create table public.paper_authors (
  paper_id uuid not null references public.papers(id) on delete cascade,
  author_id uuid not null references public.authors(id) on delete cascade,
  author_position integer check (author_position is null or author_position >= 0),
  primary key (paper_id, author_id)
);
create index paper_authors_author_id_idx on public.paper_authors (author_id);

create table public.bluesky_accounts (
  did text primary key,
  handle text,
  display_name text,
  description text,
  profile_metadata jsonb not null default '{}'::jsonb,
  last_profile_fetched_at timestamptz,
  last_feed_fetched_at timestamptz,
  fetch_state text not null default 'PENDING',
  error_count integer not null default 0 check (error_count >= 0),
  next_fetch_after timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index bluesky_accounts_handle_idx on public.bluesky_accounts (lower(handle)) where handle is not null;
create index bluesky_accounts_stale_idx on public.bluesky_accounts (next_fetch_after, last_feed_fetched_at);

create table public.user_bluesky_follows (
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  followed_did text not null references public.bluesky_accounts(did) on delete cascade,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  active boolean not null default true,
  primary key (user_id, followed_did)
);
create index user_bluesky_follows_active_idx on public.user_bluesky_follows (user_id, active);
create index user_bluesky_follows_did_active_idx on public.user_bluesky_follows (followed_did, active);

create table public.bluesky_posts (
  uri text primary key,
  cid text,
  author_did text not null references public.bluesky_accounts(did) on delete cascade,
  text text,
  created_at timestamptz,
  indexed_at timestamptz,
  post_type public.bluesky_post_type not null default 'POST',
  referenced_uri text,
  extracted_urls text[] not null default '{}',
  raw_record jsonb not null default '{}'::jsonb,
  ingested_at timestamptz not null default now()
);
create index bluesky_posts_author_created_idx on public.bluesky_posts (author_did, created_at desc nulls last);
create index bluesky_posts_created_at_idx on public.bluesky_posts (created_at desc nulls last);

create table public.paper_social_signals (
  id uuid primary key default gen_random_uuid(),
  paper_id uuid not null references public.papers(id) on delete cascade,
  post_uri text not null references public.bluesky_posts(uri) on delete cascade,
  actor_did text not null references public.bluesky_accounts(did) on delete cascade,
  signal_type public.bluesky_post_type not null,
  signal_timestamp timestamptz not null,
  created_at timestamptz not null default now(),
  unique (paper_id, post_uri, actor_did, signal_type)
);
create index paper_social_signals_paper_time_idx on public.paper_social_signals (paper_id, signal_timestamp desc);
create index paper_social_signals_actor_time_idx on public.paper_social_signals (actor_did, signal_timestamp desc);
create index paper_social_signals_post_uri_idx on public.paper_social_signals (post_uri);

create table public.researcher_identities (
  author_id uuid not null references public.authors(id) on delete cascade,
  bluesky_did text not null references public.bluesky_accounts(did) on delete cascade,
  confidence numeric(4,3) not null default 0 check (confidence between 0 and 1),
  status public.researcher_identity_status not null default 'UNKNOWN',
  evidence jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  primary key (author_id, bluesky_did)
);
create index researcher_identities_did_status_idx on public.researcher_identities (bluesky_did, status);
create index researcher_identities_author_status_idx on public.researcher_identities (author_id, status);

create table public.digests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  period_start date not null,
  period_end date not null,
  generated_at timestamptz not null default now(),
  sent_at timestamptz,
  version text not null default 'v1',
  status text not null default 'GENERATED',
  check (period_end >= period_start),
  unique (user_id, period_start, period_end, version)
);
create index digests_user_generated_idx on public.digests (user_id, generated_at desc);

create table public.digest_items (
  digest_id uuid not null references public.digests(id) on delete cascade,
  paper_id uuid not null references public.papers(id) on delete restrict,
  rank integer not null check (rank > 0),
  section text not null,
  final_score numeric(6,5) not null check (final_score between 0 and 1),
  semantic_score numeric(6,5) check (semantic_score is null or semantic_score between 0 and 1),
  bluesky_score numeric(6,5) check (bluesky_score is null or bluesky_score between 0 and 1),
  fit_score numeric(6,5) check (fit_score is null or fit_score between 0 and 1),
  quality_score numeric(6,5) check (quality_score is null or quality_score between 0 and 1),
  broad_discovery_score numeric(6,5) check (broad_discovery_score is null or broad_discovery_score between 0 and 1),
  novelty_score numeric(6,5) check (novelty_score is null or novelty_score between 0 and 1),
  recency_score numeric(6,5) check (recency_score is null or recency_score between 0 and 1),
  explanation_snapshot jsonb not null default '{}'::jsonb,
  primary key (digest_id, paper_id),
  unique (digest_id, rank)
);
create index digest_items_paper_id_idx on public.digest_items (paper_id);

create table public.user_paper_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  paper_id uuid not null references public.papers(id) on delete cascade,
  digest_id uuid references public.digests(id) on delete set null,
  event_type public.paper_event_type not null,
  created_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb
);
create index user_paper_events_user_time_idx on public.user_paper_events (user_id, created_at desc);
create index user_paper_events_paper_time_idx on public.user_paper_events (paper_id, created_at desc);
create index user_paper_events_digest_id_idx on public.user_paper_events (digest_id);

create table public.researcher_recommendations (
  id uuid primary key default gen_random_uuid(),
  digest_id uuid not null references public.digests(id) on delete cascade,
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  author_id uuid not null references public.authors(id) on delete cascade,
  bluesky_did text not null references public.bluesky_accounts(did) on delete cascade,
  discovery_score numeric(6,5) not null check (discovery_score between 0 and 1),
  identity_confidence numeric(4,3) not null check (identity_confidence between 0 and 1),
  explanation_snapshot jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (digest_id, author_id, bluesky_did)
);
create index researcher_recommendations_user_idx on public.researcher_recommendations (user_id, digest_id);
create index researcher_recommendations_author_id_idx on public.researcher_recommendations (author_id);
create index researcher_recommendations_bluesky_did_idx on public.researcher_recommendations (bluesky_did);

create table public.user_researcher_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  author_id uuid not null references public.authors(id) on delete cascade,
  bluesky_did text not null references public.bluesky_accounts(did) on delete cascade,
  recommendation_id uuid references public.researcher_recommendations(id) on delete set null,
  event_type public.researcher_event_type not null,
  created_at timestamptz not null default now()
);
create index user_researcher_events_user_time_idx on public.user_researcher_events (user_id, created_at desc);
create index user_researcher_events_author_time_idx on public.user_researcher_events (author_id, created_at desc);
create index user_researcher_events_bluesky_did_idx on public.user_researcher_events (bluesky_did);
create index user_researcher_events_recommendation_id_idx on public.user_researcher_events (recommendation_id);

create trigger profiles_set_updated_at before update on public.profiles for each row execute function private.set_updated_at();
create trigger user_preference_features_set_updated_at before update on public.user_preference_features for each row execute function private.set_updated_at();
create trigger user_embeddings_set_updated_at before update on public.user_embeddings for each row execute function private.set_updated_at();
create trigger papers_set_updated_at before update on public.papers for each row execute function private.set_updated_at();
create trigger authors_set_updated_at before update on public.authors for each row execute function private.set_updated_at();
create trigger bluesky_accounts_set_updated_at before update on public.bluesky_accounts for each row execute function private.set_updated_at();
create trigger researcher_identities_set_updated_at before update on public.researcher_identities for each row execute function private.set_updated_at();

alter table public.profiles enable row level security;
alter table public.user_preference_features enable row level security;
alter table public.user_embeddings enable row level security;
alter table public.papers enable row level security;
alter table public.paper_sources enable row level security;
alter table public.authors enable row level security;
alter table public.paper_authors enable row level security;
alter table public.bluesky_accounts enable row level security;
alter table public.user_bluesky_follows enable row level security;
alter table public.bluesky_posts enable row level security;
alter table public.paper_social_signals enable row level security;
alter table public.researcher_identities enable row level security;
alter table public.digests enable row level security;
alter table public.digest_items enable row level security;
alter table public.user_paper_events enable row level security;
alter table public.researcher_recommendations enable row level security;
alter table public.user_researcher_events enable row level security;

revoke all on public.profiles, public.user_preference_features, public.user_embeddings, public.papers, public.paper_sources, public.authors, public.paper_authors, public.bluesky_accounts, public.user_bluesky_follows, public.bluesky_posts, public.paper_social_signals, public.researcher_identities, public.digests, public.digest_items, public.user_paper_events, public.researcher_recommendations, public.user_researcher_events from anon, authenticated;

grant select, insert, update on public.profiles to authenticated;
grant select, insert, update, delete on public.user_preference_features to authenticated;
grant select on public.papers, public.paper_sources, public.authors, public.paper_authors, public.bluesky_accounts to authenticated;
grant select on public.user_bluesky_follows, public.digests, public.digest_items, public.researcher_recommendations to authenticated;
grant select, insert on public.user_paper_events, public.user_researcher_events to authenticated;

grant all privileges on public.profiles, public.user_preference_features, public.user_embeddings, public.papers, public.paper_sources, public.authors, public.paper_authors, public.bluesky_accounts, public.user_bluesky_follows, public.bluesky_posts, public.paper_social_signals, public.researcher_identities, public.digests, public.digest_items, public.user_paper_events, public.researcher_recommendations, public.user_researcher_events to service_role;

create policy profiles_select_own on public.profiles for select to authenticated using ((select auth.uid()) = user_id);
create policy profiles_insert_own on public.profiles for insert to authenticated with check ((select auth.uid()) = user_id);
create policy profiles_update_own on public.profiles for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

create policy preference_features_select_own on public.user_preference_features for select to authenticated using ((select auth.uid()) = user_id);
create policy preference_features_insert_own on public.user_preference_features for insert to authenticated with check ((select auth.uid()) = user_id);
create policy preference_features_update_own on public.user_preference_features for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy preference_features_delete_own on public.user_preference_features for delete to authenticated using ((select auth.uid()) = user_id);

create policy user_embeddings_deny_client_access on public.user_embeddings for all to authenticated using (false) with check (false);
create policy bluesky_posts_deny_client_access on public.bluesky_posts for all to authenticated using (false) with check (false);
create policy paper_social_signals_deny_client_access on public.paper_social_signals for all to authenticated using (false) with check (false);
create policy researcher_identities_deny_client_access on public.researcher_identities for all to authenticated using (false) with check (false);

create policy papers_read_authenticated on public.papers for select to authenticated using (true);
create policy paper_sources_read_authenticated on public.paper_sources for select to authenticated using (true);
create policy authors_read_authenticated on public.authors for select to authenticated using (true);
create policy paper_authors_read_authenticated on public.paper_authors for select to authenticated using (true);
create policy bluesky_accounts_read_authenticated on public.bluesky_accounts for select to authenticated using (true);

create policy follows_select_own on public.user_bluesky_follows for select to authenticated using ((select auth.uid()) = user_id);
create policy digests_select_own on public.digests for select to authenticated using ((select auth.uid()) = user_id);
create policy digest_items_select_own on public.digest_items for select to authenticated using (exists (select 1 from public.digests d where d.id = digest_id and d.user_id = (select auth.uid())));

create policy paper_events_select_own on public.user_paper_events for select to authenticated using ((select auth.uid()) = user_id);
create policy paper_events_insert_own on public.user_paper_events for insert to authenticated with check (
  (select auth.uid()) = user_id
  and (digest_id is null or exists (select 1 from public.digests d where d.id = digest_id and d.user_id = (select auth.uid())))
);

create policy researcher_recommendations_select_own on public.researcher_recommendations for select to authenticated using ((select auth.uid()) = user_id);
create policy researcher_events_select_own on public.user_researcher_events for select to authenticated using ((select auth.uid()) = user_id);
create policy researcher_events_insert_own on public.user_researcher_events for insert to authenticated with check (
  (select auth.uid()) = user_id
  and (recommendation_id is null or exists (select 1 from public.researcher_recommendations r where r.id = recommendation_id and r.user_id = (select auth.uid())))
);

comment on column public.profiles.discovery_balance is 'Fraction of the digest reserved for broader discovery; MVP default 0.25 means approximately 75% focused / 25% broad.';
comment on table public.user_bluesky_follows is 'Mirror of the user public Bluesky follow graph. Bluesky remains the source of truth; clients receive read-only access.';
comment on column public.papers.embedding is 'Unbounded pgvector column in Phase 1. Fix the vector dimension and add ANN indexes only after the embedding model is locked.';
comment on column public.user_embeddings.declared_embedding is 'Unbounded pgvector column in Phase 1 to avoid coupling the schema to an embedding provider/model before Phase 4.';
