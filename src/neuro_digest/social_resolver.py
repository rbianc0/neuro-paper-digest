from __future__ import annotations

import logging
from typing import Any

from neuro_digest.db import LiteratureRepository
from neuro_digest.dedupe import merge
from neuro_digest.resolve import webpage_metadata
from neuro_digest.social_db import SocialRepository
from neuro_digest.sources.crossref import CrossrefClient
from neuro_digest.sources.europe_pmc import EuropePMCClient
from neuro_digest.sources.openalex import OpenAlexClient
from neuro_digest.util import canonical_doi, normalized_title

LOG = logging.getLogger(__name__)


class SocialPaperResolver:
    def __init__(self, social: SocialRepository | None = None, literature: LiteratureRepository | None = None):
        self.social = social or SocialRepository(); self.literature = literature or LiteratureRepository(self.social.api)
        self.openalex = OpenAlexClient(); self.crossref = CrossrefClient(); self.europe_pmc = EuropePMCClient()

    def resolve_pending(self, *, limit: int = 1000) -> tuple[int, int, int]:
        resolved = unresolved = errors = 0
        for link in self.social.pending_links(limit=limit):
            try:
                if self.resolve_link(link): resolved += 1
                else: unresolved += 1
            except Exception as exc:
                errors += 1; LOG.warning("Social link resolution failed for %s: %s", link.get("link_key"), exc); self.social.mark_link_unresolved(link["id"], error=str(exc))
        return resolved, unresolved, errors

    def resolve_link(self, link: dict[str, Any]) -> str | None:
        doi = canonical_doi(link.get("doi")); pmid = str(link.get("pmid") or "").strip() or None; title = None
        paper_id = self._existing_paper(doi=doi, pmid=pmid)
        if paper_id is None and link.get("url"):
            meta = webpage_metadata(link["url"]); doi = doi or canonical_doi(meta.get("doi")); pmid = pmid or (str(meta.get("pmid")).strip() if meta.get("pmid") else None); title = meta.get("title")
            paper_id = self._existing_paper(doi=doi, pmid=pmid)
            if paper_id is None and title: paper_id = self.social.paper_for_title_key(normalized_title(title))
        if paper_id is None:
            candidate = self._retrieve_candidate(doi=doi, pmid=pmid)
            if candidate is not None:
                if doi and "crossref" not in candidate.source_types:
                    try:
                        extra = self.crossref.lookup_doi(doi)
                        if extra: candidate = merge(candidate, extra)
                    except Exception: LOG.debug("Crossref social enrichment failed for %s", doi, exc_info=True)
                if (pmid or doi) and "europe_pmc" not in candidate.source_types:
                    try:
                        extra = self.europe_pmc.lookup(doi=doi, pmid=pmid)
                        if extra: candidate = merge(candidate, extra)
                    except Exception: LOG.debug("Europe PMC social enrichment failed for %s/%s", doi, pmid, exc_info=True)
                paper_id, *_ = self.literature.persist(candidate)
        if paper_id is None:
            self.social.mark_link_unresolved(link["id"]); return None
        self.social.mark_link_resolved(link["id"], paper_id, doi=doi, pmid=pmid)
        for event in self.social.events_for_post(link["post_uri"]): self.social.create_paper_signal(paper_id, event)
        return paper_id

    def _existing_paper(self, *, doi: str | None, pmid: str | None) -> str | None:
        if doi:
            paper_id = self.social.paper_for_identifier("DOI", doi)
            if paper_id: return paper_id
        if pmid:
            paper_id = self.social.paper_for_identifier("PMID", pmid)
            if paper_id: return paper_id
        return None

    def _retrieve_candidate(self, *, doi: str | None, pmid: str | None):
        if doi and self.openalex.enabled:
            candidate = self.openalex.lookup_doi(doi)
            if candidate: return candidate
        if pmid and self.openalex.enabled:
            candidate = self.openalex.lookup_pmid(pmid)
            if candidate: return candidate
        if doi:
            candidate = self.crossref.lookup_doi(doi)
            if candidate: return candidate
        if pmid:
            candidate = self.europe_pmc.lookup(pmid=pmid)
            if candidate: return candidate
        if doi: return self.europe_pmc.lookup(doi=doi)
        return None
