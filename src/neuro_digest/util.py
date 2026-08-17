from __future__ import annotations

import html
import re
import unicodedata
from datetime import date, datetime, timezone
from urllib.parse import unquote, urlparse

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
PMID_RE = re.compile(r"(?:pubmed\.ncbi\.nlm\.nih\.gov/|/pubmed/)(\d+)", re.I)
URL_RE = re.compile(r"https?://[^\s<>\]\[\)\(\"']+", re.I)


def canonical_doi(value: str | None) -> str | None:
    if not value:
        return None
    value = html.unescape(unquote(value)).strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.I)
    value = re.sub(r"^doi:\s*", "", value, flags=re.I)
    match = DOI_RE.search(value)
    if not match:
        return None
    doi = match.group(0).rstrip(".,;:)]}\"").lower()
    return doi


def extract_dois(text: str | None) -> set[str]:
    if not text:
        return set()
    return {d for m in DOI_RE.finditer(unquote(text)) if (d := canonical_doi(m.group(0)))}


def extract_urls(text: str | None) -> set[str]:
    if not text:
        return set()
    return {m.group(0).rstrip(".,;:)") for m in URL_RE.finditer(text)}


def extract_pmid(value: str | None) -> str | None:
    if not value:
        return None
    m = PMID_RE.search(value)
    return m.group(1) if m else None


def normalized_title(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def author_key(name: str) -> str:
    name = normalized_title(name)
    if not name:
        return ""
    return name.split()[-1]


def iso_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def host(url: str | None) -> str:
    if not url:
        return ""
    try:
        return urlparse(url).netloc.casefold().removeprefix("www.")
    except ValueError:
        return ""


def scholarly_url(url: str) -> bool:
    h = host(url)
    if not h:
        return False
    allow = (
        "doi.org", "biorxiv.org", "medrxiv.org", "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov",
        "nature.com", "science.org", "cell.com", "sciencedirect.com", "springer.com", "link.springer.com",
        "wiley.com", "onlinelibrary.wiley.com", "academic.oup.com", "jneurosci.org", "elifesciences.org",
        "plos.org", "frontiersin.org", "tandfonline.com", "cambridge.org", "arxiv.org", "openalex.org",
    )
    return any(h == x or h.endswith("." + x) for x in allow)


def biorxiv_doi_from_url(url: str) -> str | None:
    if "biorxiv.org" not in host(url) and "medrxiv.org" not in host(url):
        return None
    return canonical_doi(url)
