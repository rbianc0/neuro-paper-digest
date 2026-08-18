# Neurofeed MVP architecture map

The original `neuro-paper-digest` repository was a useful single-user acquisition prototype. Neurofeed keeps the deterministic scholarly parsing/deduplication ideas but replaces JSON-first state and per-user crawling with shared canonical services.

## Target service boundaries

```text
                         ┌────────────────────┐
                         │ Supabase / Postgres│
                         │ canonical state    │
                         └─────────┬──────────┘
                                   │
          ┌────────────────────────┼─────────────────────────┐
          │                        │                         │
   global literature       shared Bluesky            user/digest state
      ingestion               ingestion                + feedback
          │                        │                         │
 OpenAlex/bioRxiv        unique DID scheduler       ranking/newsletter
 Crossref/Europe PMC     posts + social links      web control layer
```

## Phase 2 mapping

| Prototype | Neurofeed target | Status |
|---|---|---|
| `sources/openalex.py` keyword searches | shared recent Neuroscience/Psychology corpus + identifier lookup | implemented |
| `sources/biorxiv.py` | global Neuroscience preprints + publication mappings | implemented |
| no Crossref collector | DOI/publisher enrichment + provenance | implemented |
| no Europe PMC collector | biomedical abstract/PMID/OA enrichment | implemented |
| `Candidate.authors: list[str]` | structured `AuthorRef` with OpenAlex/ORCID/affiliations/position | implemented |
| parallel `source_types/source_urls` lists | structured `SourceRecord` provenance | implemented |
| `dedupe.py` weekly in-memory only | in-memory dedup + persistent identifier registry + historical merge | implemented |
| `data/*.json` canonical state | PostgreSQL canonical state | implemented |
| JSON history file | canonical DB identifiers/timestamps | implemented |
| monolithic `pipeline.py` | explicit scheduled jobs | old pipeline removed |
| `config/interests.yaml` | global acquisition config + later per-user DB profiles | prototype config removed |

## Canonical literature identity

`papers` is the scientific object. `paper_identifiers` registers stable aliases independently of presentation columns:

1. all DOI variants attached to the study, including preprint and journal DOI;
2. OpenAlex work ID;
3. PMID;
4. exact normalized title fallback only when no stable identifier is known;
5. strong title similarity + author overlap remains an in-memory deterministic fallback.

`paper_sources` stores where metadata/provenance came from. A source record is not a paper.

A later preprint→journal mapping can reveal that two already-persisted rows are the same study. `merge_papers(keep_id, remove_id)` moves identifiers, provenance, authorships, social signals, digest references, and paper events in one database transaction before deleting the duplicate.

## Author identity in Phase 2

Author ingestion is intentionally conservative:

- ORCID is preferred when available;
- otherwise OpenAlex author ID;
- name-only authors receive a paper-scoped provisional identity rather than a global name match.

The repository also searches existing ORCID/OpenAlex columns before creating a new author, so later enrichment can attach stronger identifiers without requiring prototype compatibility. Full Bluesky researcher identity resolution remains Phase 8.

## Scheduled jobs

The canonical specification defines these logical jobs:

1. `sync_literature` — implemented in Phase 2.
2. `sync_user_follow_graphs` — Phase 3.
3. `sync_bluesky_accounts` — Phase 3.
4. `resolve_social_papers` — Phase 3.
5. `resolve_researcher_identities` — later/minimal support as needed.
6. `embed_new_papers` — Phase 4.
7. `generate_weekly_digests` — Phase 6.
8. `send_weekly_digests` — Phase 6.

GitHub Actions remains sufficient for scheduled MVP execution; no additional worker platform is introduced before pilot evidence demands it.
