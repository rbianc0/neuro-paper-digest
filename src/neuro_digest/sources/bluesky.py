from __future__ import annotations
import logging
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from typing import Any
from dateutil.parser import isoparse
from neuro_digest.http import get_json,session
from neuro_digest.models import BlueskySignal
from neuro_digest.util import extract_dois,extract_pmid,extract_urls,scholarly_url
LOG=logging.getLogger(__name__); BASE="https://public.api.bsky.app/xrpc"

def _walk_strings(obj:Any):
    if isinstance(obj,str): yield obj
    elif isinstance(obj,dict):
        for v in obj.values(): yield from _walk_strings(v)
    elif isinstance(obj,list):
        for v in obj: yield from _walk_strings(v)

def _post_url(handle,at_uri):
    if not handle or not at_uri: return None
    return f"https://bsky.app/profile/{handle}/post/{at_uri.rstrip('/').split('/')[-1]}"

def get_follows(handle,*,max_follows=None):
    s=session(); cursor=None; out=[]
    while True:
        params={"actor":handle,"limit":100}
        if cursor: params["cursor"]=cursor
        data=get_json(s,f"{BASE}/app.bsky.graph.getFollows",params=params); out.extend(data.get("follows") or [])
        if max_follows and len(out)>=max_follows: return out[:max_follows]
        cursor=data.get("cursor")
        if not cursor: return out

def _created_at(item):
    reason=item.get("reason") or {}; post=item.get("post") or {}; record=post.get("record") or {}
    return reason.get("indexedAt") or record.get("createdAt") or post.get("indexedAt")

def _extract_signal_rows(followed,item):
    post=item.get("post") or {}; record=post.get("record") or {}; reason=item.get("reason") or {}; followed_handle=followed.get("handle") or followed.get("did"); original_author=((post.get("author") or {}).get("handle"))
    if "reasonRepost" in (reason.get("$type") or ""): action="repost"
    else:
        embed_type=((record.get("embed") or {}).get("$type") or "") if isinstance(record.get("embed"),dict) else ""; action="quote" if ("embed.record" in embed_type or "recordWithMedia" in embed_type) else "post"
    text=record.get("text") or ""; urls={u for u in extract_urls(text) if scholarly_url(u)}; dois=set(extract_dois(text)); pmids=set()
    for raw in _walk_strings({"facets":record.get("facets"),"embed":record.get("embed"),"view_embed":post.get("embed")}):
        if raw.startswith("http://") or raw.startswith("https://"):
            if scholarly_url(raw): urls.add(raw)
            dois.update(extract_dois(raw)); p=extract_pmid(raw)
            if p: pmids.add(p)
    for u in list(urls):
        dois.update(extract_dois(u)); p=extract_pmid(u)
        if p: pmids.add(p)
    if not urls and not dois and not pmids: return []
    signal=BlueskySignal(followed_actor=followed_handle,followed_actor_did=followed.get("did"),action=action,post_url=_post_url(original_author,post.get("uri")),created_at=_created_at(item),original_author=original_author,text=text[:1000] if text else None)
    return [{"dois":sorted(dois),"pmids":sorted(pmids),"urls":sorted(urls),"signal":signal}]

def _fetch_actor_week(followed,start_dt:datetime,*,max_pages=5):
    s=session(); actor=followed.get("did") or followed.get("handle"); cursor=None; out=[]
    for _ in range(max_pages):
        params={"actor":actor,"limit":100,"filter":"posts_with_replies"}
        if cursor: params["cursor"]=cursor
        try: data=get_json(s,f"{BASE}/app.bsky.feed.getAuthorFeed",params=params)
        except Exception as e: LOG.warning("Bluesky feed failed for %s: %s",actor,e); return out
        feed=data.get("feed") or []
        if not feed: return out
        oldest=None
        for item in feed:
            created=_created_at(item)
            if created:
                try:
                    dt=isoparse(created); dt=dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc); oldest=dt if oldest is None or dt<oldest else oldest
                    if dt<start_dt: continue
                except ValueError: pass
            out.extend(_extract_signal_rows(followed,item))
        if oldest and oldest<start_dt: return out
        cursor=data.get("cursor")
        if not cursor: return out
    return out

def collect_network(handle,start_dt,*,max_workers=8,max_follows=None):
    follows=get_follows(handle,max_follows=max_follows); LOG.info("Bluesky: scanning %d followed accounts",len(follows)); out=[]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures=[pool.submit(_fetch_actor_week,f,start_dt) for f in follows]
        for fut in as_completed(futures):
            try: out.extend(fut.result())
            except Exception as e: LOG.warning("Bluesky worker failed: %s",e)
    return out
