alter table public.digests
  add column if not exists subject text,
  add column if not exists rendered_html text,
  add column if not exists rendered_text text,
  add column if not exists content_hash text,
  add column if not exists delivery_provider text,
  add column if not exists delivery_id text,
  add column if not exists delivery_error text;

alter table public.digest_items
  add column if not exists summary text,
  add column if not exists why_recommended text,
  add column if not exists paper_url text,
  add column if not exists summary_model text,
  add column if not exists summary_input_hash text;

create table public.interaction_tokens (
  token_hash text primary key,
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  paper_id uuid not null references public.papers(id) on delete cascade,
  digest_id uuid not null references public.digests(id) on delete cascade,
  action_type public.paper_event_type not null,
  redirect_url text,
  expires_at timestamptz not null,
  single_use boolean not null default true,
  used_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  check (action_type in ('CLICK', 'SAVE', 'MORE_LIKE_THIS', 'LESS_LIKE_THIS'))
);
create index interaction_tokens_digest_idx on public.interaction_tokens (digest_id);
create index interaction_tokens_expires_idx on public.interaction_tokens (expires_at);

alter table public.interaction_tokens enable row level security;
revoke all on public.interaction_tokens from anon, authenticated;
grant all privileges on public.interaction_tokens to service_role;

create function public.get_newsletter_users()
returns table (
  user_id uuid,
  email text,
  display_name text,
  discovery_balance numeric,
  research_description text
)
language sql
stable
security invoker
set search_path = ''
as $$
  select p.user_id,
         coalesce(nullif(p.email, ''), u.email)::text as email,
         p.display_name,
         p.discovery_balance,
         p.research_description
  from public.profiles p
  join auth.users u on u.id = p.user_id
  where p.newsletter_enabled = true
    and p.research_description is not null
    and coalesce(nullif(p.email, ''), u.email) is not null;
$$;
revoke all on function public.get_newsletter_users() from public, anon, authenticated;
grant execute on function public.get_newsletter_users() to service_role;

create function public.get_digest_paper_data(p_paper_ids uuid[])
returns table (
  paper_id uuid,
  title text,
  abstract text,
  journal text,
  publication_date date,
  first_online_date date,
  canonical_doi text,
  canonical_url text,
  authors jsonb
)
language sql
stable
security invoker
set search_path = ''
as $$
  select p.id,
         p.title,
         p.abstract,
         p.journal,
         p.publication_date,
         p.first_online_date,
         p.canonical_doi,
         case
           when p.canonical_doi is not null then 'https://doi.org/' || p.canonical_doi
           else (
             select ps.source_url
             from public.paper_sources ps
             where ps.paper_id = p.id and ps.source_url is not null
             order by case ps.source_type
               when 'crossref' then 1
               when 'openalex' then 2
               when 'biorxiv' then 3
               when 'europe_pmc' then 4
               else 10 end,
               ps.retrieved_at desc
             limit 1
           )
         end as canonical_url,
         coalesce((
           select jsonb_agg(
             jsonb_build_object(
               'name', a.canonical_name,
               'position', pa.author_position,
               'orcid', a.orcid,
               'openalex_id', a.openalex_id
             )
             order by pa.author_position nulls last, a.canonical_name
           )
           from public.paper_authors pa
           join public.authors a on a.id = pa.author_id
           where pa.paper_id = p.id
         ), '[]'::jsonb) as authors
  from public.papers p
  where p.id = any(coalesce(p_paper_ids, '{}'::uuid[]));
$$;
revoke all on function public.get_digest_paper_data(uuid[]) from public, anon, authenticated;
grant execute on function public.get_digest_paper_data(uuid[]) to service_role;

create function public.consume_interaction_token(
  p_token_hash text,
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
    and expires_at > now()
    and (single_use = false or used_at is null)
  for update;

  if not found then
    raise exception 'invalid_or_expired_interaction_token';
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
revoke all on function public.consume_interaction_token(text, jsonb) from public, anon, authenticated;
grant execute on function public.consume_interaction_token(text, jsonb) to service_role;

comment on table public.interaction_tokens is 'Server-only hashes of random newsletter interaction tokens. Raw tokens are emitted only into the user newsletter/action URL.';
comment on function public.consume_interaction_token(text, jsonb) is 'Atomic service-only token redemption. State-changing email action URLs should call this only after explicit POST confirmation; read-paper redirect tokens may be non-single-use CLICK tokens.';
comment on column public.digests.rendered_html is 'Exact HTML snapshot prepared for delivery, including the per-user interaction URLs that were shown.';
comment on column public.digest_items.summary is 'LLM-generated concise summary based only on canonical metadata supplied by Neurofeed; bibliographic existence remains structured-system truth.';
