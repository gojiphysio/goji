"""
Which roles are open — read from the website, so a vacancy is opened, closed
or edited in exactly one place (`marketing/website/src/content/careers/*.md`).

The site builds `/careers/vacancies.json` from that collection. We fetch it,
cache it for VACANCIES_TTL_S, and keep the last good copy if a refresh fails, so
a website blip never closes the form. A role that is missing or `active: false`
can't be applied for (HTTP 410 "closed"). The general expression of interest is
built in and always open.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import requests

from . import config

log = logging.getLogger("careers.vacancies")


@dataclass(frozen=True)
class Vacancy:
    id: str
    title: str
    active: bool
    form: str            # "physio" adds the physiotherapy questions; "general" doesn't
    location: str
    drive_folder: str    # role folder name under Applications/<year>/
    min_days: int | None = None

    @property
    def is_general(self) -> bool:
        return self.id == config.GENERAL_JOB_ID


GENERAL = Vacancy(id=config.GENERAL_JOB_ID, title="General expression of interest",
                  active=True, form="general", location="Lentor Modern, Singapore",
                  drive_folder=config.GENERAL_DRIVE_FOLDER)

_cache: tuple[float, dict[str, Vacancy]] | None = None
_lock = threading.Lock()


def _parse(payload) -> dict[str, Vacancy]:
    roles = payload.get("vacancies") if isinstance(payload, dict) else None
    if not isinstance(roles, list):
        raise ValueError("vacancies.json has no 'vacancies' list")
    out: dict[str, Vacancy] = {}
    for r in roles:
        if not isinstance(r, dict) or not r.get("id") or not r.get("title"):
            continue
        rid = str(r["id"])
        if rid == config.GENERAL_JOB_ID:
            continue
        min_days = r.get("minDaysPerWeek")
        out[rid] = Vacancy(
            id=rid, title=str(r["title"]), active=bool(r.get("active")),
            form="physio" if r.get("form") == "physio" else "general",
            location=str(r.get("location") or "Lentor Modern, Singapore"),
            drive_folder=str(r.get("driveFolder") or r["title"])[:100],
            min_days=int(min_days) if isinstance(min_days, (int, float)) else None,
        )
    return out


def _fetch() -> dict[str, Vacancy]:
    r = requests.get(config.VACANCIES_URL, timeout=8,
                     headers={"User-Agent": "goji-careers/1.0"})
    r.raise_for_status()
    return _parse(r.json())


def all_vacancies() -> dict[str, Vacancy] | None:
    """The current role list, or None if it has never loaded."""
    global _cache
    now = time.monotonic()
    with _lock:
        if _cache and now - _cache[0] < config.VACANCIES_TTL_S:
            return _cache[1]
    try:
        roles = _fetch()
    except Exception as e:  # keep serving the last good copy
        log.warning("vacancies refresh failed: %s", e)
        with _lock:
            return _cache[1] if _cache else None
    with _lock:
        _cache = (now, roles)
    return roles


def lookup(job_id: str) -> tuple[Vacancy | None, str | None]:
    """(vacancy, None) when it can be applied for, else (None, reason) where
    reason is 'unknown', 'closed' or 'unavailable' (role list never loaded)."""
    if job_id == config.GENERAL_JOB_ID:
        return GENERAL, None
    roles = all_vacancies()
    if roles is None:
        return None, "unavailable"
    v = roles.get(job_id)
    if v is None:
        return None, "unknown"
    if not v.active:
        return None, "closed"
    return v, None


def reset_cache() -> None:
    global _cache
    with _lock:
        _cache = None
