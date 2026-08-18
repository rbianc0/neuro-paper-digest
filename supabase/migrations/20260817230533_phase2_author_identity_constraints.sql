drop index if exists public.authors_openalex_id_key;
drop index if exists public.authors_orcid_key;
drop index if exists public.authors_identity_key_key;

alter table public.authors alter column identity_key set not null;
alter table public.authors add constraint authors_identity_key_unique unique (identity_key);

create index authors_openalex_id_idx on public.authors (openalex_id) where openalex_id is not null;
create index authors_orcid_idx on public.authors (orcid) where orcid is not null;

comment on constraint authors_identity_key_unique on public.authors is 'Canonical ingestion identity. ORCID is preferred when available, then OpenAlex ID; name-only authors remain paper-scoped until later identity resolution.';
