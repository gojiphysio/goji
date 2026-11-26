"""
Which roles are open — read from the website, not duplicated here.

The site builds /careers/vacancies.json from src/lib/vacancies.ts, so closing a
role on the site closes it here too (within VACANCIES_TTL_S, or on the next
deploy of the site). A failed refresh keeps serving the last good copy; if we
have never managed to load it, job applications are refused with a retryable
error (general expressions of interest still work).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

from . import config

log = logging.getLogger("careers.vacancies")
SGT = timezone(timedelta(hours=8))

_lock = threading.Lock()
_cache: dict = {"at": 0.0, "by_id": None}


def _fetch() -> dict[str, dict]:
    r = requests.get(config.VACANCIES_URL, timeout=8)
    r.raise_for_status()
    rows = r.json().get("vacancies")
    if not isinstance(rows, list):
        raise ValueError("vacancies.json has no list")
    return {str(v["id"]): v for v in rows if isinstance(v, dict) and v.get("id")}


def _all() -> dict[str, dict] | None:
    now = time.monotonic()
    with _lock:
        fresh = _cache["by_id"] is not None and now - _cache["at"] < config.VACANCIES_TTL_S
        if fresh:
            return _cache["by_id"]
    try:
        by_id = _fetch()
    except Exception as e:
        log.warning("vacancies refresh failed, using last good copy: %s", e)
        with _lock:
            return _cache["by_id"]
    with _lock:
        _cache.update(at=now, by_id=by_id)
    return by_id


def lookup(job_id: str) -> tuple[str, dict | None]:
    """('open'|'closed'|'unknown'|'unavailable', vacancy)."""
    by_id = _all()
    if by_id is None:
        return "unavailable", None
    v = by_id.get(job_id)
    if not v:
        return "unknown", None
    closing = v.get("closing_date")
    today = datetime.now(SGT).date().isoformat()
    if not v.get("open") or (closing and today > closing):
        return "closed", v
    return "open", v


def reset_cache() -> None:  # tests
    with _lock:
        _cache.update(at=0.0, by_id=None)
