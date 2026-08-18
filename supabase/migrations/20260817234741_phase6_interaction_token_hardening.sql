create function public.get_interaction_token(p_token_hash text)
returns table (
  user_id uuid,
  paper_id uuid,
  digest_id uuid,
  action_type public.paper_event_type,
  redirect_url text,
  expires_at timestamptz,
  single_use boolean,
  used_at timestamptz
)
language sql
stable
security invoker
set search_path = ''
as $$
  select t.user_id, t.paper_id, t.digest_id, t.action_type,
         t.redirect_url, t.expires_at, t.single_use, t.used_at
  from public.interaction_tokens t
  where t.token_hash = p_token_hash
    and t.expires_at > now()
    and (t.single_use = false or t.used_at is null);
$$;
revoke all on function public.get_interaction_token(text) from public, anon, authenticated;
grant execute on function public.get_interaction_token(text) to service_role;

drop function public.consume_interaction_token(text, jsonb);

create function public.consume_interaction_token(
  p_token_hash text,
  p_expected_action public.paper_event_type,
  p_metadata jsonb default '{}'::jsonb
)
returns table (
  event_id uuid,
  redirect_url text,
  action_type public.paper_event_type
)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_token public.interaction_tokens%rowtype;
  v_event_id uuid;
begin
  select * into v_token
  from public.interaction_tokens
  where token_hash = p_token_hash
    and action_type = p_expected_action
    and expires_at > now()
    and (single_use = false or used_at is null)
  for update;

  if not found then
    raise exception 'invalid_expired_or_mismatched_interaction_token';
  end if;

  insert into public.user_paper_events (
    user_id, paper_id, digest_id, event_type, metadata
  ) values (
    v_token.user_id,
    v_token.paper_id,
    v_token.digest_id,
    v_token.action_type,
    coalesce(v_token.metadata, '{}'::jsonb) || coalesce(p_metadata, '{}'::jsonb)
  ) returning id into v_event_id;

  if v_token.single_use then
    update public.interaction_tokens
    set used_at = now()
    where token_hash = p_token_hash;
  end if;

  return query select v_event_id, v_token.redirect_url, v_token.action_type;
end;
$$;
revoke all on function public.consume_interaction_token(text, public.paper_event_type, jsonb) from public, anon, authenticated;
grant execute on function public.consume_interaction_token(text, public.paper_event_type, jsonb) to service_role;

comment on function public.get_interaction_token(text) is 'Service-only non-consuming lookup used to render email-action confirmation pages safely.';
comment on function public.consume_interaction_token(text, public.paper_event_type, jsonb) is 'Atomic service-only redemption requiring an expected action to prevent cross-route token misuse.';
