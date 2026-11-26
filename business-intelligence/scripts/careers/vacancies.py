"""
Which roles are open: read from the website (/careers/vacancies.json, built from
marketing/website/src/lib/vacancies.ts), so a role is opened or closed in one
place. Cached for five minutes; if a refresh fails the last good copy is used.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from . import config

log = logging.getLogger("careers.vacancies")
SGT = timezone(timedelta(hours=8))
TTL_S = 300
_cache: dict = {"at": 0.0, "by_id": None}


def _fetch() -> dict[str, dict]:
    r = requests.get(config.VACANCIES_URL, timeout=8)
    r.raise_for_status()
    return {str(v["id"]): v for v in r.json()["vacancies"]}


def lookup(job_id: str) -> tuple[str, dict | None]:
    """('open' | 'closed' | 'unknown' | 'unavailable', vacancy)."""
    if _cache["by_id"] is None or time.monotonic() - _cache["at"] > TTL_S:
        try:
            _cache.update(by_id=_fetch(), at=time.monotonic())
        except Exception as e:
            log.warning("vacancies refresh failed: %s", type(e).__name__)
    by_id = _cache["by_id"]
    if by_id is None:
        return "unavailable", None
    v = by_id.get(job_id)
    if not v:
        return "unknown", None
    closing = v.get("closing_date")
    if not v.get("open") or (closing and datetime.now(SGT).date().isoformat() > closing):
        return "closed", v
    return "open", v
