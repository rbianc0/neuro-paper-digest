alter table public.papers
  alter column embedding type extensions.vector(1536)
  using embedding::extensions.vector(1536);
alter table public.papers
  add column if not exists embedding_input_hash text;

alter table public.user_embeddings
  alter column declared_embedding type extensions.vector(1536)
  using declared_embedding::extensions.vector(1536),
  alter column learned_positive_embedding type extensions.vector(1536)
  using learned_positive_embedding::extensions.vector(1536),
  alter column learned_negative_embedding type extensions.vector(1536)
  using learned_negative_embedding::extensions.vector(1536);
alter table public.user_embeddings
  add column if not exists declared_input_hash text;

create index papers_embedding_hnsw_idx
  on public.papers using hnsw (embedding extensions.vector_cosine_ops)
  where embedding is not null;

create function public.match_papers(
  p_query_embedding extensions.vector(1536),
  p_published_after date,
  p_match_count integer default 300
)
returns table (paper_id uuid, similarity double precision)
language sql
stable
security invoker
set search_path = ''
as $$
  select p.id,
         greatest(0::double precision,
                  least(1::double precision,
                        1 - (p.embedding OPERATOR(extensions.<=>) p_query_embedding))) as similarity
  from public.papers p
  where p.embedding is not null
    and coalesce(p.first_online_date, p.publication_date) >= p_published_after
  order by p.embedding OPERATOR(extensions.<=>) p_query_embedding
  limit greatest(1, least(coalesce(p_match_count, 300), 2000));
$$;
revoke all on function public.match_papers(extensions.vector, date, integer) from public, anon, authenticated;
grant execute on function public.match_papers(extensions.vector, date, integer) to service_role;

create function public.score_papers(
  p_paper_ids uuid[],
  p_query_embedding extensions.vector(1536)
)
returns table (paper_id uuid, similarity double precision)
language sql
stable
security invoker
set search_path = ''
as $$
  select p.id,
         greatest(0::double precision,
                  least(1::double precision,
                        1 - (p.embedding OPERATOR(extensions.<=>) p_query_embedding))) as similarity
  from public.papers p
  where p.id = any(coalesce(p_paper_ids, '{}'::uuid[]))
    and p.embedding is not null;
$$;
revoke all on function public.score_papers(uuid[], extensions.vector) from public, anon, authenticated;
grant execute on function public.score_papers(uuid[], extensions.vector) to service_role;

create function public.get_user_network_candidates(
  p_user_id uuid,
  p_published_after date
)
returns table (
  paper_id uuid,
  independent_actors bigint,
  direct_count bigint,
  repost_count bigint,
  quote_count bigint,
  latest_signal_at timestamptz,
  authored_by_followed boolean
)
language sql
stable
security invoker
set search_path = ''
as $$
  with followed as (
    select followed_did as did
    from public.user_bluesky_follows
    where user_id = p_user_id and active = true
  ),
  social as (
    select s.paper_id,
           count(distinct s.actor_did) as independent_actors,
           count(*) filter (where s.signal_type = 'POST') as direct_count,
           count(*) filter (where s.signal_type = 'REPOST') as repost_count,
           count(*) filter (where s.signal_type = 'QUOTE') as quote_count,
           max(s.signal_timestamp) as latest_signal_at
    from public.paper_social_signals s
    join followed f on f.did = s.actor_did
    group by s.paper_id
  ),
  authored as (
    select distinct pa.paper_id
    from public.paper_authors pa
    join public.researcher_identities ri on ri.author_id = pa.author_id
    join followed f on f.did = ri.bluesky_did
    where ri.status in ('CONFIRMED', 'HIGH_CONFIDENCE')
  ),
  candidate_ids as (
    select paper_id from social
    union
    select paper_id from authored
  )
  select c.paper_id,
         coalesce(s.independent_actors, 0),
         coalesce(s.direct_count, 0),
         coalesce(s.repost_count, 0),
         coalesce(s.quote_count, 0),
         s.latest_signal_at,
         (a.paper_id is not null) as authored_by_followed
  from candidate_ids c
  join public.papers p on p.id = c.paper_id
  left join social s on s.paper_id = c.paper_id
  left join authored a on a.paper_id = c.paper_id
  where coalesce(p.first_online_date, p.publication_date) >= p_published_after;
$$;
revoke all on function public.get_user_network_candidates(uuid, date) from public, anon, authenticated;
grant execute on function public.get_user_network_candidates(uuid, date) to service_role;

create function public.get_broad_candidates(
  p_published_after date,
  p_priority_venues text[],
  p_limit integer default 200
)
returns table (paper_id uuid, venue_priority boolean, cited_by_count integer)
language sql
stable
security invoker
set search_path = ''
as $$
  select p.id,
         (lower(coalesce(p.journal, '')) = any(coalesce(p_priority_venues, '{}'::text[]))) as venue_priority,
         coalesce(p.cited_by_count, 0)
  from public.papers p
  where p.embedding is not null
    and coalesce(p.first_online_date, p.publication_date) >= p_published_after
    and (
      lower(coalesce(p.journal, '')) = any(coalesce(p_priority_venues, '{}'::text[]))
      or coalesce(p.cited_by_count, 0) >= 3
    )
  order by
    (lower(coalesce(p.journal, '')) = any(coalesce(p_priority_venues, '{}'::text[]))) desc,
    coalesce(p.cited_by_count, 0) desc,
    coalesce(p.first_online_date, p.publication_date) desc
  limit greatest(1, least(coalesce(p_limit, 200), 1000));
$$;
revoke all on function public.get_broad_candidates(date, text[], integer) from public, anon, authenticated;
grant execute on function public.get_broad_candidates(date, text[], integer) to service_role;

create function public.get_user_seen_papers(p_user_id uuid)
returns table (paper_id uuid)
language sql
stable
security invoker
set search_path = ''
as $$
  select distinct di.paper_id
  from public.digest_items di
  join public.digests d on d.id = di.digest_id
  where d.user_id = p_user_id
  union
  select distinct e.paper_id
  from public.user_paper_events e
  where e.user_id = p_user_id and e.event_type = 'IMPRESSION';
$$;
revoke all on function public.get_user_seen_papers(uuid) from public, anon, authenticated;
grant execute on function public.get_user_seen_papers(uuid) to service_role;

comment on column public.papers.embedding_input_hash is 'SHA-256 of the normalized text used to generate the current paper embedding.';
comment on column public.user_embeddings.declared_input_hash is 'SHA-256 of the declared research description used to generate declared_embedding.';
comment on function public.match_papers(extensions.vector, date, integer) is 'Service-only cosine nearest-neighbor candidate retrieval over recent canonical papers.';
comment on function public.get_user_network_candidates(uuid, date) is 'Service-only decomposed Bluesky candidate features from the user active follow graph plus high-confidence followed-author mappings.';
