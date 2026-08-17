create table public.paper_identifiers (
  paper_id uuid not null references public.papers(id) on delete cascade,
  identifier_type text not null check (identifier_type in ('DOI', 'OPENALEX', 'PMID')),
  identifier_value text not null,
  created_at timestamptz not null default now(),
  primary key (identifier_type, identifier_value)
);
create index paper_identifiers_paper_id_idx on public.paper_identifiers (paper_id);

alter table public.paper_identifiers enable row level security;
revoke all on public.paper_identifiers from anon, authenticated;
grant select on public.paper_identifiers to authenticated;
grant all privileges on public.paper_identifiers to service_role;
create policy paper_identifiers_read_authenticated on public.paper_identifiers
  for select to authenticated using (true);

create function public.merge_papers(keep_id uuid, remove_id uuid)
returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if keep_id = remove_id then
    return keep_id;
  end if;
  if not exists (select 1 from public.papers where id = keep_id) then
    raise exception 'keep paper % does not exist', keep_id;
  end if;
  if not exists (select 1 from public.papers where id = remove_id) then
    return keep_id;
  end if;

  update public.paper_sources set paper_id = keep_id where paper_id = remove_id;

  insert into public.paper_authors (paper_id, author_id, author_position)
  select keep_id, author_id, author_position
  from public.paper_authors
  where paper_id = remove_id
  on conflict (paper_id, author_id) do update
    set author_position = case
      when public.paper_authors.author_position is null then excluded.author_position
      when excluded.author_position is null then public.paper_authors.author_position
      else least(public.paper_authors.author_position, excluded.author_position)
    end;
  delete from public.paper_authors where paper_id = remove_id;

  delete from public.paper_social_signals old
  using public.paper_social_signals kept
  where old.paper_id = remove_id
    and kept.paper_id = keep_id
    and old.post_uri = kept.post_uri
    and old.actor_did = kept.actor_did
    and old.signal_type = kept.signal_type;
  update public.paper_social_signals set paper_id = keep_id where paper_id = remove_id;

  delete from public.digest_items old
  using public.digest_items kept
  where old.paper_id = remove_id
    and kept.paper_id = keep_id
    and old.digest_id = kept.digest_id;
  update public.digest_items set paper_id = keep_id where paper_id = remove_id;

  update public.user_paper_events set paper_id = keep_id where paper_id = remove_id;
  update public.paper_identifiers set paper_id = keep_id where paper_id = remove_id;

  delete from public.papers where id = remove_id;
  return keep_id;
end;
$$;
revoke all on function public.merge_papers(uuid, uuid) from public, anon, authenticated;
grant execute on function public.merge_papers(uuid, uuid) to service_role;

comment on table public.paper_identifiers is 'Stable identifier registry used to enforce one canonical paper object across DOI, OpenAlex and PMID aliases, including preprint and journal DOI mappings.';
comment on function public.merge_papers(uuid, uuid) is 'Atomic service-role-only canonical merge used when new provenance reveals that two historical paper rows are the same scientific work.';
