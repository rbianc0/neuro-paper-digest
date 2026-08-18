from __future__ import annotations

import argparse
import logging

from neuro_digest.bluesky_db import BlueskyRepository
from neuro_digest.db import LiteratureRepository
from neuro_digest.resolve import webpage_metadata
from neuro_digest.sources.openalex import OpenAlexClient
from neuro_digest.util import canonical_doi, extract_pmid

LOG = logging.getLogger(__name__)


def _find_existing(repo: BlueskyRepository, *, doi: str | None, pmid: str | None) -> str | None:
    if doi:
        paper_id = repo.find_paper_by_identifier("DOI", canonical_doi(doi) or doi)
        if paper_id:
            return paper_id
    if pmid:
        paper_id = repo.find_paper_by_identifier("PMID", str(pmid))
        if paper_id:
            return paper_id
    return None


def _materialize_from_openalex(doi: str | None, pmid: str | None, literature_repo: LiteratureRepository, openalex: OpenAlexClient) -> str | None:
    candidate = None
    if doi and openalex.enabled:
        candidate = openalex.lookup_doi(doi)
    if candidate is None and pmid and openalex.enabled:
        candidate = openalex.lookup_pmid(pmid)
    if candidate is None:
        return None
    paper_id, _, _, _ = literature_repo.persist(candidate)
    return paper_id


def resolve_social_papers(*, limit: int = 1000, max_web_resolutions: int = 100, repository: BlueskyRepository | None = None, literature_repository: LiteratureRepository | None = None) -> tuple[int, int, int]:
    repo = repository or BlueskyRepository(); literature_repo = literature_repository or LiteratureRepository(repo.api); openalex = OpenAlexClient()
    resolved = unresolved = signals = web_used = 0
    for link in repo.pending_links(limit=limit):
        doi = canonical_doi(link.get("doi")); pmid = str(link["pmid"]) if link.get("pmid") else None
        try:
            paper_id = _find_existing(repo, doi=doi, pmid=pmid)
            if not paper_id:
                paper_id = _materialize_from_openalex(doi, pmid, literature_repo, openalex)
            if not paper_id and link.get("url") and web_used < max_web_resolutions:
                web_used += 1
                metadata = webpage_metadata(link["url"])
                doi = canonical_doi(metadata.get("doi")) or doi
                pmid = str(extract_pmid(metadata.get("url") or "") or pmid or "") or None
                paper_id = _find_existing(repo, doi=doi, pmid=pmid)
                if not paper_id:
                    paper_id = _materialize_from_openalex(doi, pmid, literature_repo, openalex)
            if paper_id:
                repo.resolve_link(link["id"], paper_id)
                signals += repo.materialize_social_signals(post_uri=link["post_uri"], paper_id=paper_id)
                resolved += 1
            else:
                repo.mark_link_unresolved(link["id"])
                unresolved += 1
        except Exception as exc:
            repo.mark_link_unresolved(link["id"], error=str(exc))
            unresolved += 1
            LOG.exception("Failed to resolve Bluesky scholarly link %s", link.get("link_key"))
    return resolved, unresolved, signals


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve Bluesky scholarly links into canonical Neurofeed papers")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--max-web-resolutions", type=int, default=100)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    resolved, unresolved, signals = resolve_social_papers(limit=args.limit, max_web_resolutions=args.max_web_resolutions)
    print(f"Social resolution: {resolved} links resolved, {unresolved} unresolved/error, {signals} network signals materialized")


if __name__ == "__main__":
    main()
