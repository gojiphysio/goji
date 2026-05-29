#!/usr/bin/env python3
"""
Plato BI: bookings vs recognised revenue vs deferred revenue, last 7 days.

Based on the live data shape we observed, here are the three classifications:

  BOOKING (cash in)
    - any invoice item whose others.redeem_from is NOT set
    - line value = item.selling_price * item.qty - discount (use sub_total when present)

  REDEMPTION (revenue recognised, $0 cash)
    - item.others.redeem_from is set (this line CONSUMES sessions from another invoice)
    - recognised value = sum of item.others.redeem_alloc[].value

  DEFERRED REVENUE (snapshot today)
    - sum of reports/outstanding_packages[].pro_rata_left
    - Plato computes this for us; no diffing needed

A single-visit sale (consult, product) collapses into BOOKING only - we treat
booking == recognised when the item is not a package and is consumed same day.

Usage:
    export PLATO_DB=gojihealth
    export PLATO_API_KEY=...
    python3 plato_week_metrics.py
    python3 plato_week_metrics.py --days 30
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

BASE = "https://clinic.platomedical.com/api"
PER_PAGE_SLEEP_S = 3
TIMEOUT_S = 30


def env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        sys.exit(f"set {name}")
    return v


def paged_get(session: requests.Session, url: str, params: dict | None = None):
    """Yield rows from a paginated Plato endpoint using current_page."""
    page = 1
    params = dict(params or {})
    while True:
        params["current_page"] = page
        r = session.get(url, params=params, timeout=TIMEOUT_S)
        if r.status_code == 429:
            time.sleep(60)
            continue
        r.raise_for_status()
        batch = r.json()
        if not isinstance(batch, list) or not batch:
            return
        for row in batch:
            yield row
        rem = r.headers.get("x-ratelimit-remaining")
        time.sleep(60 if (rem and rem.isdigit() and int(rem) < 2) else PER_PAGE_SLEEP_S)
        page += 1


def money(v) -> float:
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def classify_item(item: dict) -> tuple[str, float]:
    """Return (kind, value).
    kind: 'redemption' | 'package_sale' | 'sale'
    value: dollar amount for that kind (recognised revenue for redemption,
           cash in for sale/package_sale)
    """
    others = item.get("others") or {}
    if isinstance(others, dict) and others.get("redeem_from"):
        # Sum the redeem_alloc values - this is recognised revenue
        allocs = others.get("redeem_alloc") or []
        value = sum(money(a.get("value")) for a in allocs)
        return ("redemption", value)
    if item.get("inventory") == "package":
        # Original package sale (cash in, deferred liability created)
        # Prefer sub_total if Plato sets it; otherwise selling_price * qty
        sub = money(item.get("sub_total"))
        if sub > 0:
            return ("package_sale", sub)
        return ("package_sale", money(item.get("selling_price")) * money(item.get("qty") or 1))
    # Non-package, normal sale
    sub = money(item.get("sub_total"))
    if sub > 0:
        return ("sale", sub)
    return ("sale", money(item.get("selling_price")) * money(item.get("qty") or 1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    db = env("PLATO_DB")
    key = env("PLATO_API_KEY")

    session = requests.Session()
    session.headers.update({
        "accept": "application/json",
        "Authorization": f"Bearer {key}",
    })

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    modified_since = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    cutoff_date = cutoff.date().isoformat()
    today = datetime.now(timezone.utc).date().isoformat()

    # 1) Pull provider names so we can show clinician names in output
    print("Loading clinician roster from systemsetup...")
    r = session.get(f"{BASE}/{db}/systemsetup", timeout=TIMEOUT_S)
    r.raise_for_status()
    providers = {p["given_id"]: p["name"] for p in r.json().get("providers", [])}
    print(f"  {len(providers)} providers: " + ", ".join(f"{k}={v}" for k, v in providers.items()))

    # 2) Iterate invoices in window
    print(f"\nFetching invoices modified since {modified_since}...")
    bookings_by_day = defaultdict(float)   # cash in
    recognised_by_day = defaultdict(float) # revenue earned
    by_clinician = defaultdict(lambda: {"bookings": 0.0, "recognised": 0.0})
    booking_count = 0
    redemption_count = 0
    skipped_outside_window = 0

    for inv in paged_get(session, f"{BASE}/{db}/invoice", {"modified_since": modified_since}):
        date_str = (inv.get("date") or "")[:10]
        if not date_str or date_str < cutoff_date:
            skipped_outside_window += 1
            continue
        if inv.get("void"):
            continue
        doctor = inv.get("doctor") or "?"
        clin_name = providers.get(doctor, doctor)

        for item in (inv.get("item") or []):
            kind, value = classify_item(item)
            if kind == "redemption":
                recognised_by_day[date_str] += value
                by_clinician[clin_name]["recognised"] += value
                redemption_count += 1
            elif kind == "package_sale":
                # Booking only - revenue recognised over time as sessions consumed
                bookings_by_day[date_str] += value
                by_clinician[clin_name]["bookings"] += value
                booking_count += 1
            else:  # 'sale' - single-use, collapse booking + recognised
                bookings_by_day[date_str] += value
                recognised_by_day[date_str] += value
                by_clinician[clin_name]["bookings"] += value
                by_clinician[clin_name]["recognised"] += value
                booking_count += 1

    # 3) Deferred revenue snapshot (today)
    print("Fetching outstanding packages snapshot...")
    r = session.get(f"{BASE}/{db}/reports/outstanding_packages",
                    params={"date": today}, timeout=TIMEOUT_S)
    r.raise_for_status()
    outstanding = r.json()
    deferred_today = sum(money(p.get("pro_rata_left")) for p in outstanding)
    sessions_outstanding = sum(int(p.get("total_left") or 0) for p in outstanding)
    packs_outstanding = len(outstanding)

    # 4) Print results
    print()
    print(f"=== Goji - last {args.days} days ({cutoff_date} to {today}) ===")
    print()
    print(f"{'Date':<12} {'Bookings':>14} {'Recognised':>14} {'Gap':>14}")
    print("-" * 60)
    all_days = sorted(set(bookings_by_day) | set(recognised_by_day))
    total_b = total_r = 0.0
    for d in all_days:
        b = bookings_by_day[d]
        rv = recognised_by_day[d]
        total_b += b
        total_r += rv
        print(f"{d:<12} ${b:>12,.2f} ${rv:>12,.2f} ${b - rv:>+12,.2f}")
    print("-" * 60)
    print(f"{'TOTAL':<12} ${total_b:>12,.2f} ${total_r:>12,.2f} ${total_b - total_r:>+12,.2f}")
    print()
    print(f"Booking line items:   {booking_count}")
    print(f"Redemption line items:{redemption_count}")
    print()

    print("=== By clinician ===")
    print(f"{'Clinician':<25} {'Bookings':>14} {'Recognised':>14}")
    print("-" * 56)
    for clin, vals in sorted(by_clinician.items(), key=lambda kv: -kv[1]["bookings"]):
        print(f"{clin:<25} ${vals['bookings']:>12,.2f} ${vals['recognised']:>12,.2f}")
    print()

    print(f"=== Deferred revenue snapshot ({today}) ===")
    print(f"Outstanding packs:        {packs_outstanding}")
    print(f"Sessions still owed:      {sessions_outstanding}")
    print(f"Deferred revenue liability: ${deferred_today:,.2f}")


if __name__ == "__main__":
    main()
