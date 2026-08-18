alter table public.profiles
  add column if not exists last_bluesky_sync_at timestamptz,
  add column if not exists last_bluesky_sync_error text;

create table public.bluesky_post_events (
  event_key text primary key,
  post_uri text not null references public.bluesky_posts(uri) on delete cascade,
  actor_did text not null references public.bluesky_accounts(did) on delete cascade,
  signal_type public.bluesky_post_type not null,
  signal_timestamp timestamptz not null,
  event_uri text,
  raw_event jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index bluesky_post_events_actor_time_idx on public.bluesky_post_events (actor_did, signal_timestamp desc);
create index bluesky_post_events_post_uri_idx on public.bluesky_post_events (post_uri);

create table public.bluesky_scholarly_links (
  id uuid primary key default gen_random_uuid(),
  post_uri text not null references public.bluesky_posts(uri) on delete cascade,
  link_key text not null,
  url text,
  doi text,
  pmid text,
  resolved_paper_id uuid references public.papers(id) on delete set null,
  resolution_status text not null default 'PENDING' check (resolution_status in ('PENDING', 'RESOLVED', 'UNRESOLVED', 'ERROR')),
  last_attempted_at timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (post_uri, link_key)
);
create index bluesky_scholarly_links_status_idx on public.bluesky_scholarly_links (resolution_status, last_attempted_at);
create index bluesky_scholarly_links_paper_idx on public.bluesky_scholarly_links (resolved_paper_id) where resolved_paper_id is not null;

create trigger bluesky_scholarly_links_set_updated_at before update on public.bluesky_scholarly_links for each row execute function private.set_updated_at();

alter table public.bluesky_post_events enable row level security;
alter table public.bluesky_scholarly_links enable row level security;
revoke all on public.bluesky_post_events, public.bluesky_scholarly_links from anon, authenticated;
grant all privileges on public.bluesky_post_events, public.bluesky_scholarly_links to service_role;

create function public.replace_user_bluesky_follows(p_user_id uuid, p_bluesky_did text, p_bluesky_handle text, p_followed_dids text[])
returns integer
language plpgsql
security invoker
set search_path = ''
as $$
declare v_count integer;
begin
  if not exists (select 1 from public.profiles where user_id = p_user_id) then
    raise exception 'profile % does not exist', p_user_id;
  end if;
  update public.user_bluesky_follows set active = false where user_id = p_user_id and active = true;
  insert into public.user_bluesky_follows (user_id, followed_did, first_seen_at, last_seen_at, active)
  select p_user_id, did, now(), now(), true from unnest(coalesce(p_followed_dids, '{}'::text[])) as did
  on conflict (user_id, followed_did) do update set last_seen_at = excluded.last_seen_at, active = true;
  update public.profiles set bluesky_did = p_bluesky_did, bluesky_handle = p_bluesky_handle, last_bluesky_sync_at = now(), last_bluesky_sync_error = null where user_id = p_user_id;
  select count(*)::integer into v_count from public.user_bluesky_follows where user_id = p_user_id and active = true;
  return v_count;
end;
$$;
revoke all on function public.replace_user_bluesky_follows(uuid, text, text, text[]) from public, anon, authenticated;
grant execute on function public.replace_user_bluesky_follows(uuid, text, text, text[]) to service_role;

create function public.get_stale_bluesky_accounts(p_stale_before timestamptz, p_limit integer default 1000)
returns table (did text, handle text, display_name text, last_feed_fetched_at timestamptz, error_count integer, next_fetch_after timestamptz)
language sql
security invoker
set search_path = ''
as $$
  select a.did, a.handle, a.display_name, a.last_feed_fetched_at, a.error_count, a.next_fetch_after
  from public.bluesky_accounts a
  where exists (select 1 from public.user_bluesky_follows f where f.followed_did = a.did and f.active = true)
    and (a.last_feed_fetched_at is null or a.last_feed_fetched_at < p_stale_before)
    and (a.next_fetch_after is null or a.next_fetch_after <= now())
  order by a.last_feed_fetched_at asc nulls first, a.did
  limit greatest(1, least(coalesce(p_limit, 1000), 5000));
$$;
revoke all on function public.get_stale_bluesky_accounts(timestamptz, integer) from public, anon, authenticated;
grant execute on function public.get_stale_bluesky_accounts(timestamptz, integer) to service_role;

comment on table public.bluesky_post_events is 'Durable raw network attention events. Events exist before a scholarly link can necessarily be resolved to a canonical paper.';
comment on table public.bluesky_scholarly_links is 'Normalized scholarly identifiers/URLs extracted from Bluesky posts with durable resolution state.';
comment on function public.replace_user_bluesky_follows(uuid, text, text, text[]) is 'Atomically mirrors one user public Bluesky follow graph after a complete successful API fetch. Bluesky remains the source of truth.';
comment on function public.get_stale_bluesky_accounts(timestamptz, integer) is 'Returns unique actively-followed DIDs whose shared feed cache is stale and not under backoff.';
