from __future__ import annotations
import logging
from neuro_digest.http import get_json,session
from neuro_digest.models import Candidate
from neuro_digest.util import canonical_doi,iso_date
LOG=logging.getLogger(__name__); BASE="https://api.biorxiv.org"

def collect_preprints(start,end,*,category="neuroscience",server="biorxiv"):
    s=session(); cursor=0; out=[]
    while True:
        data=get_json(s,f"{BASE}/details/{server}/{start}/{end}/{cursor}",params={"category":category}); rows=data.get("collection") or []
        for row in rows:
            doi=canonical_doi(row.get("doi")); published=canonical_doi(row.get("published")); date=iso_date(row.get("date"))
            out.append(Candidate(title=row.get("title"),doi=published or doi,preprint_doi=doi,published_doi=published,authors=[x.strip() for x in (row.get("authors") or "").split(";") if x.strip()],journal="bioRxiv" if server.lower()=="biorxiv" else "medRxiv",preprint_date=date,first_available_date=date,abstract=row.get("abstract"),url=f"https://doi.org/{doi}" if doi else None,category=row.get("category"),source_types=[server.lower()],source_urls=[f"https://api.biorxiv.org/details/{server}/{doi}"] if doi else []))
        messages=data.get("messages") or []; total=None
        if messages:
            total=messages[0].get("total") or messages[0].get("count")
            try: total=int(total) if total is not None else None
            except (TypeError,ValueError): total=None
        cursor+=len(rows)
        if not rows or len(rows)<30 or (total is not None and cursor>=total): break
    return out

def collect_recent_publications(start,end,*,server="biorxiv"):
    s=session(); cursor=0; out=[]
    while True:
        data=get_json(s,f"{BASE}/pubs/{server}/{start}/{end}/{cursor}"); rows=data.get("collection") or []
        for row in rows:
            pre=canonical_doi(row.get("biorxiv_doi")); pub=canonical_doi(row.get("published_doi")); pubdate=iso_date(row.get("published_date")); predate=iso_date(row.get("preprint_date"))
            out.append(Candidate(title=row.get("preprint_title"),doi=pub or pre,preprint_doi=pre,published_doi=pub,authors=[x.strip() for x in (row.get("preprint_authors") or "").split(";") if x.strip()],journal=row.get("published_journal"),publication_date=pubdate,preprint_date=predate,first_available_date=predate or pubdate,abstract=row.get("preprint_abstract"),url=f"https://doi.org/{pub or pre}" if (pub or pre) else None,category=row.get("preprint_category"),source_types=["biorxiv_published_mapping"]))
        cursor+=len(rows)
        if not rows or len(rows)<100: break
    return out
