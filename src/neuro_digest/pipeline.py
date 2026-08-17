from __future__ import annotations

import json, logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from neuro_digest.config import load_config
from neuro_digest.dedupe import deduplicate
from neuro_digest.models import Candidate
from neuro_digest.resolve import webpage_metadata
from neuro_digest.sources.biorxiv import collect_preprints, collect_recent_publications
from neuro_digest.sources.bluesky import collect_network
from neuro_digest.sources.openalex import OpenAlexClient
from neuro_digest.util import canonical_doi, scholarly_url, utc_now_iso

LOG=logging.getLogger(__name__)

def _attach(c,signal):
    c.bluesky_signals.append(signal)
    if "bluesky" not in c.source_types: c.source_types.append("bluesky")
    if signal.post_url and signal.post_url not in c.source_urls: c.source_urls.append(signal.post_url)

def _load(path):
    try: return json.loads(path.read_text()) if path.exists() else {}
    except Exception: return {}

def _hkey(c): return c.published_doi or c.doi or c.preprint_doi or c.openalex_id or (c.title or "").casefold()

def _history(candidates,path,today):
    h=_load(path)
    for c in candidates:
        k=_hkey(c)
        if not k: continue
        prev=h.get(k) or {}; c.first_seen=prev.get("first_seen") or today; c.last_seen=today; c.seen_weeks=int(prev.get("seen_weeks") or 0)+1
        h[k]={"title":c.title,"doi":c.doi,"first_seen":c.first_seen,"last_seen":today,"seen_weeks":c.seen_weeks}
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(h,indent=2,ensure_ascii=False))

def run(config_path:str,output_dir:str,docs_dir:str,lookback_days:int=7):
    cfg=load_config(config_path); today=date.today(); start=today-timedelta(days=lookback_days); start_s,end_s=start.isoformat(),today.isoformat(); start_dt=datetime.combine(start,datetime.min.time(),tzinfo=timezone.utc)
    allc=[]; oa=OpenAlexClient(); ocfg=cfg.get("openalex",{})
    if oa.enabled:
        for q in ocfg.get("personal_queries",[]):
            try: allc.extend(oa.search_works(q,start_s,end_s,per_page=ocfg.get("per_query",50)))
            except Exception as e: LOG.warning("OpenAlex query failed %s: %s",q,e)
        try: source_ids=list(oa.resolve_source_ids(ocfg.get("general_journals",[])).values())
        except Exception as e: LOG.warning("Journal resolution failed: %s",e); source_ids=[]
        for q in ocfg.get("general_queries",[]):
            try: allc.extend(oa.search_works(q,start_s,end_s,per_page=ocfg.get("general_per_query",30),source_ids=source_ids))
            except Exception as e: LOG.warning("OpenAlex general failed %s: %s",q,e)
    bcfg=cfg.get("biorxiv",{})
    if bcfg.get("enabled",True):
        try: allc.extend(collect_preprints(start_s,end_s,category=bcfg.get("category","neuroscience")))
        except Exception as e: LOG.warning("bioRxiv failed: %s",e)
        try: allc.extend(collect_recent_publications(start_s,end_s))
        except Exception as e: LOG.warning("bioRxiv pubs failed: %s",e)
    bsky=cfg.get("bluesky",{}); rows=[]
    if bsky.get("enabled",True):
        try: rows=collect_network(bsky.get("handle","rimbianco.bsky.social"),start_dt,max_workers=int(bsky.get("max_workers",8)),max_follows=bsky.get("max_follows"))
        except Exception as e: LOG.warning("Bluesky failed: %s",e)
    candidates=deduplicate(allc); by_doi={}; by_pmid={}
    for c in candidates:
        for d in (c.doi,c.preprint_doi,c.published_doi):
            d=canonical_doi(d)
            if d: by_doi[d]=c
        if c.pmid: by_pmid[c.pmid]=c
    unresolved={}
    for row in rows:
        sig=row["signal"]; attached=False
        for d in row.get("dois",[]):
            d=canonical_doi(d); c=by_doi.get(d)
            if c is None and d and oa.enabled:
                try: c=oa.lookup_doi(d)
                except Exception: c=None
            if c is None and d: c=Candidate(doi=d,url=f"https://doi.org/{d}",metadata_confidence="low",source_types=["bluesky"])
            if c:
                _attach(c,sig); attached=True
                if c not in candidates: candidates.append(c)
                by_doi[d]=c
        for pmid in row.get("pmids",[]):
            c=by_pmid.get(pmid)
            if c is None and oa.enabled:
                try: c=oa.lookup_pmid(pmid)
                except Exception: c=None
            if c:
                _attach(c,sig); attached=True
                if c not in candidates: candidates.append(c)
                by_pmid[pmid]=c
        if not attached:
            for u in row.get("urls",[]):
                if scholarly_url(u): unresolved.setdefault(u,[]).append(sig)
    for u,sigs in list(unresolved.items())[:int(bsky.get("max_web_resolutions",60))]:
        meta=webpage_metadata(u); d=canonical_doi(meta.get("doi")); c=by_doi.get(d) if d else None
        if c is None and d and oa.enabled:
            try: c=oa.lookup_doi(d)
            except Exception: c=None
        if c is None and (d or meta.get("title")): c=Candidate(title=meta.get("title"),doi=d,authors=meta.get("authors") or [],url=meta.get("url") or u,metadata_confidence="medium" if meta.get("title") else "low",source_types=["bluesky"])
        if c:
            for s in sigs: _attach(c,s)
            if c not in candidates: candidates.append(c)
    candidates=deduplicate(candidates); candidates.sort(key=lambda c:(bool(c.bluesky_signals),c.publication_date or c.preprint_date or c.first_available_date or "",c.cited_by_count or 0),reverse=True)
    out=Path(output_dir); docs=Path(docs_dir); out.mkdir(parents=True,exist_ok=True); docs.mkdir(parents=True,exist_ok=True); _history(candidates,out/"history.json",today.isoformat())
    payload={"generated_at":utc_now_iso(),"window":{"start":start_s,"end":end_s,"lookback_days":lookback_days},"candidate_count":len(candidates),"sources":{"openalex_enabled":oa.enabled,"biorxiv_enabled":bcfg.get("enabled",True),"bluesky_enabled":bsky.get("enabled",True),"bluesky_handle":bsky.get("handle","rimbianco.bsky.social")},"candidates":[c.to_dict() for c in candidates]}
    text=json.dumps(payload,indent=2,ensure_ascii=False)
    for p in (out/f"{today.isoformat()}.json",out/"latest_candidates.json",docs/"latest_candidates.json"): p.write_text(text)
    lines=["# Neuro Paper Digest — structured candidate pool","",f"Generated: `{payload['generated_at']}`",f"Window: `{start_s}` → `{end_s}`",f"Unique candidates: **{len(candidates)}**",""]
    for i,c in enumerate(candidates,1):
        lines += [f"## {i}. {c.title or c.doi or c.url or 'Unresolved paper'}",""]
        if c.journal: lines.append(f"- Venue: {c.journal}")
        if c.publication_date: lines.append(f"- Publication date: {c.publication_date}")
        if c.preprint_date: lines.append(f"- Preprint date: {c.preprint_date}")
        if c.doi: lines.append(f"- DOI: https://doi.org/{c.doi}")
        lines.append(f"- Sources: {', '.join(c.source_types)}")
        if c.bluesky_signals:
            actors=sorted({s.followed_actor for s in c.bluesky_signals}); lines.append(f"- Bluesky network: {len(c.bluesky_signals)} signal(s) from {', '.join(actors[:10])}")
        lines.append("")
    md="\n".join(lines); (out/"latest_report.md").write_text(md); (docs/"index.md").write_text(md)
    return candidates
