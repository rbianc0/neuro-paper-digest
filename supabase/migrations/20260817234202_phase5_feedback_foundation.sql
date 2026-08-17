create view public.user_saved_papers
with (security_invoker = true)
as
select latest.user_id, latest.paper_id, latest.created_at as saved_at
from (
  select distinct on (e.user_id, e.paper_id)
         e.user_id, e.paper_id, e.event_type, e.created_at
  from public.user_paper_events e
  where e.event_type in ('SAVE', 'UNSAVE')
  order by e.user_id, e.paper_id, e.created_at desc, e.id::text desc
) latest
where latest.event_type = 'SAVE';

grant select on public.user_saved_papers to authenticated;

create function public.record_paper_event(
  p_paper_id uuid,
  p_digest_id uuid,
  p_event_type public.paper_event_type,
  p_metadata jsonb default '{}'::jsonb
)
returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_user_id uuid;
  v_event_id uuid;
begin
  v_user_id := auth.uid();
  if v_user_id is null then
    raise exception 'authentication required';
  end if;
  insert into public.user_paper_events (user_id, paper_id, digest_id, event_type, metadata)
  values (v_user_id, p_paper_id, p_digest_id, p_event_type, coalesce(p_metadata, '{}'::jsonb))
  returning id into v_event_id;
  return v_event_id;
end;
$$;
revoke all on function public.record_paper_event(uuid, uuid, public.paper_event_type, jsonb) from public, anon;
grant execute on function public.record_paper_event(uuid, uuid, public.paper_event_type, jsonb) to authenticated, service_role;

create function public.get_effective_paper_feedback(
  p_user_id uuid,
  p_click_weight double precision default 0.25,
  p_save_weight double precision default 1.0,
  p_more_weight double precision default 1.5,
  p_less_weight double precision default 1.5,
  p_neutral_less_reasons text[] default array['already_knew_it']::text[]
)
returns table (
  paper_id uuid,
  effective_weight double precision,
  embedding extensions.vector(1536),
  last_event_at timestamptz,
  explicit_event public.paper_event_type,
  explicit_metadata jsonb
)
language sql
stable
security invoker
set search_path = ''
as $$
  with per_paper as (
    select e.paper_id,
      bool_or(e.event_type = 'CLICK') as clicked,
      ((array_agg(e.event_type order by e.created_at desc, e.id::text desc) filter (where e.event_type in ('SAVE', 'UNSAVE'))))[1] as save_state,
      ((array_agg(e.event_type order by e.created_at desc, e.id::text desc) filter (where e.event_type in ('MORE_LIKE_THIS', 'LESS_LIKE_THIS'))))[1] as explicit_state,
      ((array_agg(e.metadata order by e.created_at desc, e.id::text desc) filter (where e.event_type in ('MORE_LIKE_THIS', 'LESS_LIKE_THIS'))))[1] as explicit_metadata,
      max(e.created_at) as last_event_at
    from public.user_paper_events e
    where e.user_id = p_user_id
    group by e.paper_id
  ), weighted as (
    select pp.*,
      (case when pp.clicked then p_click_weight else 0 end)
      + (case when pp.save_state = 'SAVE' then p_save_weight else 0 end)
      + (case
           when pp.explicit_state = 'MORE_LIKE_THIS' then p_more_weight
           when pp.explicit_state = 'LESS_LIKE_THIS' then
             case when coalesce(pp.explicit_metadata->>'reason', '') = any(coalesce(p_neutral_less_reasons, '{}'::text[])) then 0 else -p_less_weight end
           else 0
         end) as effective_weight
    from per_paper pp
  )
  select w.paper_id, w.effective_weight, p.embedding, w.last_event_at, w.explicit_state, w.explicit_metadata
  from weighted w
  join public.papers p on p.id = w.paper_id
  where p.embedding is not null and abs(w.effective_weight) > 1e-9;
$$;
revoke all on function public.get_effective_paper_feedback(uuid, double precision, double precision, double precision, double precision, text[]) from public, anon, authenticated;
grant execute on function public.get_effective_paper_feedback(uuid, double precision, double precision, double precision, double precision, text[]) to service_role;

comment on view public.user_saved_papers is 'Current saved-paper state derived from the append-only SAVE/UNSAVE event stream.';
comment on function public.record_paper_event(uuid, uuid, public.paper_event_type, jsonb) is 'Authenticated event write API. User identity comes from auth.uid(); RLS still enforces paper/digest ownership constraints.';
comment on function public.get_effective_paper_feedback(uuid, double precision, double precision, double precision, double precision, text[]) is 'Service-only reproducible reduction of append-only paper events into one effective learning weight per embedded paper. Neutral Less-like reasons such as already_knew_it do not teach a negative preference.';
