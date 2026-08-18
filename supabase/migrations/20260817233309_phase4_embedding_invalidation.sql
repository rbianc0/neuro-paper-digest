create function private.invalidate_paper_embedding()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if new.title is distinct from old.title
     or new.abstract is distinct from old.abstract
     or new.journal is distinct from old.journal then
    new.embedding = null;
    new.embedding_model = null;
    new.embedding_input_hash = null;
  end if;
  return new;
end;
$$;
revoke all on function private.invalidate_paper_embedding() from public, anon, authenticated;

create trigger papers_invalidate_embedding
before update of title, abstract, journal on public.papers
for each row execute function private.invalidate_paper_embedding();

comment on function private.invalidate_paper_embedding() is 'Invalidates a paper embedding whenever the text used to generate it changes.';
