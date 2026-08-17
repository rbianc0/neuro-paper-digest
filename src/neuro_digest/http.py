from __future__ import annotations

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

LOG = logging.getLogger(__name__)


def session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        respect_retry_after_header=True,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20))
    s.headers.update({
        "User-Agent": "neuro-paper-digest/0.1 (+https://github.com/rbianc0/neuro-paper-digest)",
        "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    })
    return s


def get_json(s: requests.Session, url: str, *, params: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    r = s.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()
