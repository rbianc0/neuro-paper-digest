from __future__ import annotations

import argparse
import json
import logging
from datetime import date, timedelta
from pathlib import Path

from neuro_digest.config import load_config
from neuro_digest.db import LiteratureRepository, PersistStats
from neuro_digest.dedupe import deduplicate, merge
from neuro_digest.models import Candidate
from neuro_digest.sources.biorxiv import collect_preprints, collect_recent_publications
from neuro_digest.sources.crossref import CrossrefClient
from neuro_digest.sources.europe_pmc import EuropePMCClient
from neuro_digest.sources.openalex import OpenAlexClient
from neuro_digest.util import utc_now_iso

LOG = logging.getLogger(__name__)


def collect_candidates(config: dict, *, lookback_days: int = 7) -> tuple[list[Candidate], dict[str, str]]:
    today = date.today(); start = today - timedelta(days=lookback_days); start_s, end_s = start.isoformat(), today.isoformat(); all_candidates: list[Candidate] = []
    oa = OpenAlexClient(); ocfg = config.get("openalex", {})
    if oa.enabled and ocfg.get("enabled", True):
        try:
            all_candidates.extend(oa.list_recent_field_works(start_s, end_s, field_ids=ocfg.get("field_ids", [28, 32]), max_records=int(ocfg.get("max_records", 5000))))
        except Exception as exc: LOG.warning("OpenAlex global field ingestion failed: %s", exc)
    bcfg = config.get("biorxiv", {})
    if bcfg.get("enabled", True):
        try: all_candidates.extend(collect_preprints(start_s, end_s, category=bcfg.get("category", "neuroscience")))
        except Exception as exc: LOG.warning("bioRxiv details ingestion failed: %s", exc)
        try: all_candidates.extend(collect_recent_publications(start_s, end_s))
        except Exception as exc: LOG.warning("bioRxiv publication mapping ingestion failed: %s", exc)
    return deduplicate(all_candidates), {"start": start_s, "end": end_s}


def _needs_crossref(candidate: Candidate) -> bool:
    return bool(candidate.published_doi or candidate.doi) and (not candidate.title or not candidate.journal or not candidate.publication_date or not candidate.authors or "biorxiv_published_mapping" in candidate.source_types)


def _needs_europe_pmc(candidate: Candidate) -> bool:
    return bool(candidate.pmid or candidate.published_doi or candidate.doi) and (not candidate.abstract or not candidate.pmid)


def enrich_candidates(candidates: list[Candidate], config: dict) -> list[Candidate]:
    crossref_cfg = config.get("crossref", {}); epmc_cfg = config.get("europe_pmc", {})
    crossref = CrossrefClient() if crossref_cfg.get("enabled", True) else None; epmc = EuropePMCClient() if epmc_cfg.get("enabled", True) else None
    crossref_budget = int(crossref_cfg.get("max_enrichments", 500)); epmc_budget = int(epmc_cfg.get("max_enrichments", 1000)); crossref_used = 0; epmc_used = 0; enriched: list[Candidate] = []
    for candidate in candidates:
        current = candidate; doi = current.published_doi or current.doi or current.preprint_doi
        if crossref and crossref_used < crossref_budget and _needs_crossref(current):
            try:
                extra = crossref.lookup_doi(doi) if doi else None; crossref_used += 1
                if extra: current = merge(current, extra)
            except Exception as exc: LOG.warning("Crossref enrichment failed for %s: %s", doi, exc)
        if epmc and epmc_used < epmc_budget and _needs_europe_pmc(current):
            try:
                extra = epmc.lookup(doi=doi, pmid=current.pmid); epmc_used += 1
                if extra: current = merge(current, extra)
            except Exception as exc: LOG.warning("Europe PMC enrichment failed for %s/%s: %s", doi, current.pmid, exc)
        enriched.append(current)
    LOG.info("Enrichment calls: Crossref=%d EuropePMC=%d", crossref_used, epmc_used)
    return deduplicate(enriched)


def sync_literature(config_path: str = "config/literature.yaml", *, lookback_days: int = 7, diagnostic_output: str | None = None, repository: LiteratureRepository | None = None) -> tuple[list[Candidate], PersistStats]:
    config = load_config(config_path); candidates, window = collect_candidates(config, lookback_days=lookback_days); candidates = enrich_candidates(candidates, config); repo = repository or LiteratureRepository(); stats = repo.persist_many(candidates)
    if diagnostic_output:
        path = Path(diagnostic_output); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps({"generated_at": utc_now_iso(), "window": window, "candidate_count": len(candidates), "persisted": stats.__dict__, "candidates": [candidate.to_dict() for candidate in candidates]}, indent=2, ensure_ascii=False))
    return candidates, stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest the global Neurofeed literature pool into Supabase"); parser.add_argument("--config", default="config/literature.yaml"); parser.add_argument("--lookback-days", type=int, default=7); parser.add_argument("--diagnostic-output"); parser.add_argument("--log-level", default="INFO"); args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    candidates, stats = sync_literature(args.config, lookback_days=args.lookback_days, diagnostic_output=args.diagnostic_output)
    print(f"Persisted {stats.papers} canonical candidates ({stats.sources} provenance records, {stats.paper_authors} authorships, {stats.merged_papers} historical paper merges) from {len(candidates)} deduplicated candidates")


if __name__ == "__main__": main()
