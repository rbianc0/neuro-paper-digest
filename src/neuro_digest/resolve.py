from __future__ import annotations

import logging
from typing import Any
from bs4 import BeautifulSoup
from neuro_digest.http import session
from neuro_digest.util import canonical_doi, extract_dois, extract_pmid

LOG = logging.getLogger(__name__)


def webpage_metadata(url: str) -> dict[str, Any]:
    s=session()
    try:
        r=s.get(url,timeout=20,allow_redirects=True,headers={"Accept":"text/html,*/*;q=0.8"}); r.raise_for_status()
    except Exception as e:
        LOG.debug("Could not fetch %s: %s",url,e); return {"url":url}
    if "html" not in r.headers.get("content-type",""): return {"url":r.url}
    soup=BeautifulSoup(r.text[:2_000_000],"html.parser")
    doi=None
    for key,value in (("name","citation_doi"),("name","dc.identifier"),("property","dc.identifier")):
        tag=soup.find("meta",attrs={key:value})
        if tag and tag.get("content"):
            doi=canonical_doi(tag["content"])
            if doi: break
    if not doi:
        found=extract_dois(r.url)|extract_dois(r.text[:200_000]); doi=sorted(found)[0] if found else None
    title=None
    for key,value in (("name","citation_title"),("property","og:title"),("name","dc.title")):
        tag=soup.find("meta",attrs={key:value})
        if tag and tag.get("content"): title=tag["content"].strip(); break
    authors=[x.get("content","").strip() for x in soup.find_all("meta",attrs={"name":"citation_author"}) if x.get("content")]
    return {"url":r.url,"doi":doi,"title":title,"authors":authors,"pmid":extract_pmid(r.url)}
