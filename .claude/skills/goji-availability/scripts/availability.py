#!/usr/bin/env python3
"""Goji clinician availability, read from the clinic's public booking API.

Read-only. Talks to https://booking.gojiphysio.com (the website's booking
backend, which reads Plato server-side), so no Plato key is needed or used.

Usage:
  python availability.py --clinician cheryl-long --from 2026-11-23 --to 2026-11-27
  python availability.py --clinician all --next-week
  python availability.py --service clinical-pilates --from 2026-12-01 --days 14
  python availability.py --clinician kristy-ng --next-week --json

Prints, per day and clinician, the free windows (merged 30-min blocks) and the
start times a patient could book for the chosen service.

Stdlib only, so it runs in claude.ai / Cowork code execution as-is.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

BASE = "https://booking.gojiphysio.com"
SGT = timezone(timedelta(hours=8))
UA = "goji-availability-skill/1.0"
PAUSE_S = 1.0  # Plato's budget (20 req/min) is shared with the live website.

CLINICIANS = {
    "cheryl-long": "Cheryl Long",
    "claire-ng": "Claire Ng",
    "kristy-ng": "Kristy Ng",
    "camille-tan": "Camille Tan",
}
# The service used to read each clinician's general free time. Physio has a
# 30-min variant, which gives the finest view of gaps; Camille only does
# Private Pilates (60-min, no variants).
FREE_TIME_SERVICE = {
    "cheryl-long": ("physiotherapy", "30min"),
    "claire-ng": ("physiotherapy", "30min"),
    "kristy-ng": ("physiotherapy", "30min"),
    "camille-tan": ("private-pilates", None),
}
SERVICES = {
    "physiotherapy": 60, "mummy-baby": 85, "clinical-pilates": 60,
    "private-pilates": 60, "strength-conditioning": 60,
}


def get(path: str, params: dict) -> dict:
    """GET a JSON endpoint; waits out the API's 503 'loading' answers.

    Never sends session_id: without it the service records no funnel event,
    so these lookups stay out of the website booking analytics."""
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v})
    url = f"{BASE}{path}?{q}"
    for attempt in range(5):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = {}
            try:
                body = json.load(e)
            except Exception:
                pass
            if e.code == 503 and attempt < 4:  # Plato busy; retry as told
                time.sleep(min(int(body.get("retry_after", 5)), 20))
                continue
            raise RuntimeError(f"{e.code} from {url}: {body or e.reason}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Could not reach {BASE} ({e.reason}). In claude.ai/Cowork, an "
                "admin must allow booking.gojiphysio.com for code execution."
            ) from e
    raise RuntimeError(f"Still busy after retries: {url}")


def windows(starts: list[str], block_min: int) -> list[str]:
    """Merge slot start times into 'HH:MM-HH:MM' free windows."""
    out: list[list[datetime]] = []
    blk = timedelta(minutes=block_min)
    for s in sorted(starts):
        t = datetime.strptime(s, "%H:%M")
        if out and t <= out[-1][1]:
            out[-1][1] = max(out[-1][1], t + blk)
        else:
            out.append([t, t + blk])
    return [f"{a:%H:%M}-{b:%H:%M}" for a, b in out]


def daterange(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def months(a: date, b: date) -> list[str]:
    ms, d = [], a.replace(day=1)
    while d <= b:
        ms.append(d.strftime("%Y-%m"))
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return ms


def open_days(service, clinician, variant, focus, home, a, b) -> set[str]:
    """One summary call per month tells us which days have any slot, so we
    only fetch slots for those days (spares Plato's shared request budget)."""
    days: set[str] = set()
    for m in months(a, b):
        r = get("/api/availability-summary", {
            "service": service, "month": m, "clinician": clinician,
            "variant": variant, "focus": focus, "home": "1" if home else ""})
        days.update(r.get("available", []))
        time.sleep(PAUSE_S)
    return days


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--clinician", default="all",
                   help="cheryl-long | claire-ng | kristy-ng | camille-tan | all")
    p.add_argument("--service", help="bookable start times for this service "
                   f"({', '.join(SERVICES)}); omit for general free time")
    p.add_argument("--variant", help="physio duration variant: 30min | 45min | 55min")
    p.add_argument("--focus", help="physio sub-type: general | womens-health | "
                   "paediatrics | scoliosis | others")
    p.add_argument("--home", action="store_true", help="home visit (Cheryl only)")
    p.add_argument("--from", dest="start", help="YYYY-MM-DD (default today, SGT)")
    p.add_argument("--to", dest="end", help="YYYY-MM-DD inclusive")
    p.add_argument("--days", type=int, help="number of days from --from")
    p.add_argument("--next-week", action="store_true", help="next Mon-Sun")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    a = p.parse_args()

    today = datetime.now(SGT).date()
    if a.next_week:
        start = today + timedelta(days=7 - today.weekday())
        end = start + timedelta(days=6)
    else:
        start = date.fromisoformat(a.start) if a.start else today
        end = (date.fromisoformat(a.end) if a.end
               else start + timedelta(days=(a.days or 7) - 1))
    if end < start:
        p.error("--to is before --from")
    if (end - start).days > 62:
        p.error("range too long: bookings open only 60 days ahead")
    if a.service and a.service not in SERVICES:
        p.error(f"unknown service {a.service}")

    if a.clinician == "all":
        cids = list(CLINICIANS)
    elif a.clinician in CLINICIANS:
        cids = [a.clinician]
    else:
        p.error(f"unknown clinician {a.clinician}; one of {', '.join(CLINICIANS)}")

    result: dict = {"from": start.isoformat(), "to": end.isoformat(),
                    "mode": f"service:{a.service}" if a.service else "free-time",
                    "clinicians": {}}
    for cid in cids:
        if a.service:
            service, variant = a.service, a.variant
        else:
            service, variant = FREE_TIME_SERVICE[cid]
        block = SERVICES[service]
        if variant:
            block = {"30min": 30, "45min": 45, "55min": 55}.get(variant, block)
        days_with_slots = open_days(service, cid, variant, a.focus, a.home, start, end)
        per_day = {}
        for d in daterange(start, end):
            iso = d.isoformat()
            if iso not in days_with_slots:
                per_day[iso] = {"starts": [], "windows": []}
                continue
            r = get("/api/availability", {
                "service": service, "date": iso, "clinician": cid,
                "variant": variant, "focus": a.focus, "home": "1" if a.home else ""})
            starts = r.get("by_clinician", {}).get(cid, [])
            per_day[iso] = {"starts": starts, "windows": windows(starts, block)}
            time.sleep(PAUSE_S)
        result["clinicians"][cid] = {"name": CLINICIANS[cid], "service": service,
                                     "variant": variant, "block_min": block,
                                     "days": per_day}

    if a.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"Availability {start:%a %d %b} - {end:%a %d %b %Y} ({result['mode']}), "
          f"read {datetime.now(SGT):%d %b %H:%M} SGT")
    for cid, c in result["clinicians"].items():
        print(f"\n## {c['name']}  [{c['service']}"
              f"{' ' + c['variant'] if c['variant'] else ''}, {c['block_min']}-min blocks]")
        for iso, v in c["days"].items():
            d = date.fromisoformat(iso)
            if not v["starts"]:
                print(f"  {d:%a %d %b}: no availability")
            elif a.service:
                print(f"  {d:%a %d %b}: starts {', '.join(v['starts'])}")
            else:
                print(f"  {d:%a %d %b}: free {', '.join(v['windows'])}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
