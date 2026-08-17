alter table public.papers add column if not exists title_key text;
create index if not exists papers_title_key_idx on public.papers (title_key) where title_key is not null;

alter table public.authors add column if not exists identity_key text;
create unique index if not exists authors_identity_key_key on public.authors (identity_key) where identity_key is not null;

update public.paper_sources
set external_id = source_url
where external_id is null and source_url is not null;

delete from public.paper_sources
where external_id is null;

alter table public.paper_sources alter column external_id set not null;
drop index if exists public.paper_sources_external_key;
alter table public.paper_sources
  add constraint paper_sources_source_external_key unique (source_type, external_id);

comment on column public.papers.title_key is 'Application-generated normalized title fingerprint used as the deterministic exact-title fallback in canonical paper identity.';
comment on column public.authors.identity_key is 'Stable application identity key: prefer OpenAlex/ORCID; otherwise use a paper-scoped provisional name key to avoid unsafe global name merges.';
