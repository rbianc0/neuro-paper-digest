from __future__ import annotations

from typing import Any

from neuro_digest.http import get_json, session
from neuro_digest.models import AuthorRef, Candidate, SourceRecord
from neuro_digest.util import canonical_doi, canonical_orcid, iso_date

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"


def _authors(result: dict[str, Any]) -> list[AuthorRef]:
    out: list[AuthorRef] = []
    for position, raw in enumerate(((result.get("authorList") or {}).get("author") or [])):
        name = raw.get("fullName") or " ".join(x for x in (raw.get("firstName"), raw.get("lastName")) if x).strip()
        if not name: continue
        author_id = raw.get("authorId"); orcid = canonical_orcid(str(author_id)) if ((raw.get("authorIdType") or "").upper() == "ORCID" or (author_id and "-" in str(author_id))) else None
        affiliations = [{"name": raw.get("affiliation")}] if raw.get("affiliation") else []
        out.append(AuthorRef(name=name, orcid=orcid, affiliations=affiliations, position=position))
    return out


def candidate_from_result(result: dict[str, Any]) -> Candidate:
    doi = canonical_doi(result.get("doi")); source = result.get("source") or result.get("src") or "unknown"; explicit_pmid = result.get("pmid"); pmid = str(explicit_pmid or (result.get("id") if str(source).upper() == "MED" else "") or "").strip() or None; ext_id = str(result.get("id") or pmid or doi or "unknown")
    publication_date = iso_date(result.get("firstPublicationDate") or result.get("electronicPublicationDate") or result.get("journalInfo", {}).get("printPublicationDate"))
    full_text_urls = [x.get("url") for x in ((result.get("fullTextUrlList") or {}).get("fullTextUrl") or []) if x.get("url")]
    url = full_text_urls[0] if full_text_urls else (f"https://doi.org/{doi}" if doi else None)
    metadata = {"pmcid": result.get("pmcid"), "source": source, "is_open_access": result.get("isOpenAccess"), "in_epmc": result.get("inEPMC"), "pub_types": ((result.get("pubTypeList") or {}).get("pubType") or []), "full_text_urls": full_text_urls}
    return Candidate(title=result.get("title"), doi=doi, authors=_authors(result), journal=result.get("journalTitle") or ((result.get("journalInfo") or {}).get("journal") or {}).get("title"), publication_date=publication_date, first_available_date=publication_date, abstract=result.get("abstractText"), url=url, pmid=pmid, cited_by_count=int(result["citedByCount"]) if str(result.get("citedByCount") or "").isdigit() else None, sources=[SourceRecord("europe_pmc", f"{source}:{ext_id}", f"https://europepmc.org/article/{source}/{ext_id}", metadata)], metadata={"pmcid": result.get("pmcid")})


class EuropePMCClient:
    def __init__(self): self.s = session()

    def lookup(self, *, doi: str | None = None, pmid: str | None = None) -> Candidate | None:
        if doi: query = f'DOI:"{canonical_doi(doi) or doi}"'
        elif pmid: query = f"EXT_ID:{pmid} AND SRC:MED"
        else: return None
        data = get_json(self.s, f"{BASE}/search", params={"query": query, "format": "json", "resultType": "core", "pageSize": 1})
        results = ((data.get("resultList") or {}).get("result") or [])
        return candidate_from_result(results[0]) if results else None
