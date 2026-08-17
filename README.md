# Neuro Paper Digest collector

Deterministic acquisition layer for a weekly neuroscience newsletter. It collects recent candidates from OpenAlex and bioRxiv, scans the public Bluesky follow graph of `rimbianco.bsky.social`, normalizes scholarly identifiers, merges preprint/publication versions, and writes a structured candidate pool for a separate ChatGPT Scheduled Task to rank and summarize.

## Pipeline

1. OpenAlex: overlapping topic queries over the last 7 days.
2. OpenAlex broad-discovery lane: neuro/psych queries restricted to a configurable high-selectivity journal list.
3. bioRxiv: Neuroscience-category preprints plus bioRxiv→journal publication mappings.
4. Bluesky: `app.bsky.graph.getFollows` followed by `app.bsky.feed.getAuthorFeed` for each public followed account; extract DOI/PubMed/bioRxiv/publisher links from post text, facets, embeds and reposts.
5. Enrichment: DOI/PMID records are normalized through OpenAlex; unresolved scholarly URLs get a bounded metadata-page fallback.
6. Deduplication: canonical DOI → preprint/published DOI relationship → OpenAlex/PMID → exact normalized title → high title similarity + author overlap.
7. Outputs: weekly snapshot, `data/latest_candidates.json`, and a human-readable `docs/index.md`.

## Secrets

Do **not** commit API keys. Add the following GitHub Actions repository secret:

- `OPENALEX_API_KEY` — required for OpenAlex API access. OpenAlex provides a free daily allowance.

Bluesky public follow/feed reads and the bioRxiv API do not require keys.

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install '.[dev]'
export OPENALEX_API_KEY='...'
neuro-digest --lookback-days 7
pytest -q
```

## GitHub Actions

`.github/workflows/collect.yml` runs every Monday at 03:37 UTC and can also be triggered manually. It commits generated `data/` and `docs/` files back to the repository using the built-in `GITHUB_TOKEN`.

The scheduled ChatGPT task should run later (currently Monday morning Europe/Berlin), read `docs/latest_candidates.json` or `docs/index.md`, supplement it with its own web search, then perform semantic ranking and summaries.

## Configuration

Edit `config/interests.yaml` to change:

- personalized OpenAlex discovery queries;
- broad neuroscience/psychology discovery queries;
- high-selectivity journal whitelist;
- Bluesky handle and crawl limits;
- bioRxiv category.

The query list is intentionally redundant. Deduplication happens after acquisition.

## Privacy / security

The repository is designed to contain only public scholarly metadata and public Bluesky activity. API keys remain in GitHub Actions secrets and are never written to generated output.
