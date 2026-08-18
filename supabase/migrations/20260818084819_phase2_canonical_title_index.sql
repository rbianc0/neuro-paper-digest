alter table public.papers add column if not exists normalized_title text;
create index if not exists papers_normalized_title_idx on public.papers (normalized_title) where normalized_title is not null;
comment on column public.papers.normalized_title is 'Deterministic normalized title used for exact-title canonicalization after DOI and stable scholarly identifiers.';
