alter table public.profiles
  add column if not exists bluesky_sync_requested_at timestamptz;

create or replace function public.replace_user_bluesky_follows(
  p_user_id uuid,
  p_bluesky_did text,
  p_bluesky_handle text,
  p_followed_dids text[]
)
returns integer
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_count integer;
begin
  if not exists (select 1 from public.profiles where user_id = p_user_id) then
    raise exception 'profile % does not exist', p_user_id;
  end if;

  update public.user_bluesky_follows
  set active = false
  where user_id = p_user_id and active = true;

  insert into public.user_bluesky_follows (
    user_id, followed_did, first_seen_at, last_seen_at, active
  )
  select p_user_id, did, now(), now(), true
  from unnest(coalesce(p_followed_dids, '{}'::text[])) as did
  on conflict (user_id, followed_did) do update
    set last_seen_at = excluded.last_seen_at,
        active = true;

  update public.profiles
  set bluesky_did = p_bluesky_did,
      bluesky_handle = p_bluesky_handle,
      last_bluesky_sync_at = now(),
      last_bluesky_sync_error = null,
      bluesky_sync_requested_at = null
  where user_id = p_user_id;

  select count(*)::integer into v_count
  from public.user_bluesky_follows
  where user_id = p_user_id and active = true;

  return v_count;
end;
$$;
revoke all on function public.replace_user_bluesky_follows(uuid, text, text, text[]) from public, anon, authenticated;
grant execute on function public.replace_user_bluesky_follows(uuid, text, text, text[]) to service_role;

comment on column public.profiles.bluesky_sync_requested_at is 'User-requested follow-graph refresh timestamp. The shared sync job prioritizes these profiles and clears the request only after a successful complete graph replacement.';
