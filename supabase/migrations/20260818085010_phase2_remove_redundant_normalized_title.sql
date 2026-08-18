drop index if exists public.papers_normalized_title_idx;
alter table public.papers drop column if exists normalized_title;
