# Neurofeed

Neurofeed is a personalized scientific-literature discovery service built around a researcher's existing Bluesky scientific network. The canonical MVP output is a finite weekly email newsletter; the web application is the stateful feedback and control layer.

This repository contains the Python ingestion backend. The implementation source of truth is **Neurofeed MVP Product & Technical Specification v1**.

## Current implementation

### Phase 1 — database foundation

The connected Supabase/PostgreSQL project contains the canonical MVP schema, pgvector, Supabase Auth integration points, RLS, feedback/digest state, shared Bluesky entities, and researcher-discovery entities. Migrations live under `supabase/migrations/`.

### Phase 2 — global literature layer

The literature pipeline is now DB-first:

```text
OpenAlex (shared Neuroscience + Psychology corpus)
                  +
bioRxiv Neuroscience + publication mappings
                  ↓
       deterministic in-memory dedup
                  ↓
Crossref / Europe PMC bounded enrichment
                  ↓
       canonical identifier resolution
                  ↓
             Supabase
 papers / paper_identifiers / paper_sources
 authors / paper_authors
```

Acquisition is global, not per user. User research descriptions and learned preferences will be applied later during candidate generation/ranking over this shared pool.

A DOI, OpenAlex ID, PMID, preprint DOI, published DOI, or later preprint→journal mapping can resolve to the same canonical paper. If historical rows are later proven equivalent, the service-only `merge_papers` database function consolidates them atomically while preserving provenance and downstream references.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install '.[dev]'

export OPENALEX_API_KEY='...'
export SUPABASE_URL='https://yajsdhpaobqtduazpkkd.supabase.co'
export SUPABASE_SECRET_KEY='...'
export CROSSREF_MAILTO='you@example.org'   # optional

neurofeed-sync-literature --lookback-days 8
pytest -q
```

`SUPABASE_SECRET_KEY` is a backend secret and must never be committed or exposed to a browser.

## Configuration

`config/literature.yaml` contains only global acquisition settings. It intentionally does **not** contain a user's research interests or Bluesky handle.

The MVP currently acquires:

- recent OpenAlex works whose topics include the Neuroscience or Psychology fields;
- bioRxiv Neuroscience preprints;
- bioRxiv publication mappings;
- bounded Crossref enrichment for incomplete DOI/publication records;
- bounded Europe PMC enrichment when biomedical abstract/PMID metadata is useful.

## GitHub Actions

`.github/workflows/collect.yml` runs the global literature job weekly and supports manual runs. It writes canonical state directly to Supabase. The generated JSON file is only a short-lived diagnostic artifact; Git is no longer the database.

Required repository secrets:

- `OPENALEX_API_KEY`
- `SUPABASE_SECRET_KEY`

Optional repository variable:

- `CROSSREF_MAILTO`

## Architectural boundary

Phase 2 does not perform user ranking and does not crawl a user's Bluesky graph. Those are separate responsibilities:

- Phase 3: shared unique-DID Bluesky ingestion;
- Phase 4: user representation and decomposed semantic + Bluesky ranking;
- Phase 5+: feedback, newsletter, web UI, researcher discovery.

Bluesky remains the sole explicit researcher-follow graph throughout the product.
