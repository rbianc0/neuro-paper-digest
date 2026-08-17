from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from typing import Any
import requests
from neuro_digest.http import get_json, session
from neuro_digest.models import Candidate
from neuro_digest.util import canonical_doi, iso_date

LOG=logging.getLogger(__name__); BASE="https://api.openalex.org"

def _authors(work):
    return [((a.get("author") or {}).get("display_name")) for a in (work.get("authorships") or []) if ((a.get("author") or {}).get("display_name"))]
def _journal(work):
    return (((work.get("primary_location") or {}).get("source") or {}).get("display_name"))
def _pmid(work):
    pmid=(work.get("ids") or {}).get("pmid"); return str(pmid).rstrip("/").split("/")[-1] if pmid else None

def candidate_from_work(work: dict[str,Any], *, source_type="openalex", query=None) -> Candidate:
    doi=canonical_doi(work.get("doi") or (work.get("ids") or {}).get("doi")); date=iso_date(work.get("publication_date")); landing=((work.get("primary_location") or {}).get("landing_page_url"))
    return Candidate(title=work.get("display_name") or work.get("title"),doi=doi,authors=_authors(work),journal=_journal(work),publication_date=date,first_available_date=date,abstract=work.get("abstract"),url=landing or (f"https://doi.org/{doi}" if doi else work.get("id")),openalex_id=work.get("id"),pmid=_pmid(work),cited_by_count=work.get("cited_by_count"),source_types=[source_type],source_urls=[work.get("id")] if work.get("id") else [],query_hits=[query] if query else [])

class OpenAlexClient:
    def __init__(self,api_key=None): self.api_key=api_key or os.getenv("OPENALEX_API_KEY"); self.s=session()
    @property
    def enabled(self): return bool(self.api_key)
    def _params(self,**kwargs):
        if not self.api_key: raise RuntimeError("OPENALEX_API_KEY is required for OpenAlex API calls")
        return {"api_key":self.api_key,**kwargs}
    def search_works(self,query,start,end,*,per_page=50,source_ids:Iterable[str]|None=None):
        filt=[f"from_publication_date:{start}",f"to_publication_date:{end}","type:article|preprint"]; ids=[x for x in (source_ids or []) if x]
        if ids: filt.append("primary_location.source.id:"+"|".join(ids[:100]))
        params=self._params(search=query,filter=",".join(filt),sort="relevance_score:desc",per_page=min(per_page,100),select="id,doi,display_name,publication_date,type,cited_by_count,authorships,primary_location,ids")
        data=get_json(self.s,f"{BASE}/works",params=params); return [candidate_from_work(w,query=query) for w in data.get("results",[])]
    def lookup_doi(self,doi):
        doi=canonical_doi(doi)
        if not doi: return None
        try: data=get_json(self.s,f"{BASE}/works/doi:{doi}",params=self._params())
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code==404: return None
            raise
        return candidate_from_work(data,source_type="openalex_enrichment")
    def lookup_pmid(self,pmid):
        try: data=get_json(self.s,f"{BASE}/works/pmid:{pmid}",params=self._params())
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code==404: return None
            raise
        return candidate_from_work(data,source_type="openalex_enrichment")
    def resolve_source_ids(self,journal_names):
        out={}
        for name in journal_names:
            data=get_json(self.s,f"{BASE}/sources",params=self._params(search=name,per_page=5,select="id,display_name")); candidates=data.get("results",[]); exact=next((x for x in candidates if (x.get("display_name") or "").casefold()==name.casefold()),None); chosen=exact or (candidates[0] if candidates else None)
            if chosen and chosen.get("id"): out[name]=chosen["id"].rstrip("/").split("/")[-1]
            else: LOG.warning("Could not resolve OpenAlex source for journal %s",name)
        return out
