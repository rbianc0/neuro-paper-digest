create or replace function public.merge_papers(keep_id uuid, remove_id uuid)
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

  update public.papers kept
  set
    canonical_doi = coalesce(kept.canonical_doi, removed.canonical_doi),
    title = coalesce(kept.title, removed.title),
    title_key = coalesce(kept.title_key, removed.title_key),
    abstract = coalesce(kept.abstract, removed.abstract),
    journal = coalesce(kept.journal, removed.journal),
    publication_date = coalesce(kept.publication_date, removed.publication_date),
    first_online_date = case
      when kept.first_online_date is null then removed.first_online_date
      when removed.first_online_date is null then kept.first_online_date
      else least(kept.first_online_date, removed.first_online_date)
    end,
    openalex_id = coalesce(kept.openalex_id, removed.openalex_id),
    pmid = coalesce(kept.pmid, removed.pmid),
    preprint_doi = coalesce(kept.preprint_doi, removed.preprint_doi),
    published_doi = coalesce(kept.published_doi, removed.published_doi),
    cited_by_count = case
      when kept.cited_by_count is null then removed.cited_by_count
      when removed.cited_by_count is null then kept.cited_by_count
      else greatest(kept.cited_by_count, removed.cited_by_count)
    end,
    metadata = coalesce(removed.metadata, '{}'::jsonb) || coalesce(kept.metadata, '{}'::jsonb)
  from public.papers removed
  where kept.id = keep_id and removed.id = remove_id;

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
