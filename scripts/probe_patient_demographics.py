#!/usr/bin/env python3
"""
One-shot probe: assess coverage of demographic + referral fields across all patients.

For each candidate dashboard attribute (age, sex, postal sector, tag, doctor,
referred_by), prints:
  - how many patients have it populated
  - the value distribution (top 20)

Privacy: nothing is written to disk. Only aggregated counts + value
distributions are printed. DOB is bucketed to age band; postal is reduced to
the first two digits (SG sector). Names/contacts are never logged.

Run:
    cd "/Users/charles/Documents/Claude/Projects/Goji Business Inteligence/scripts"
    python3 probe_patient_demographics.py
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter
from datetime import date

import requests

BASE = "https://clinic.platomedical.com/api"
TIMEOUT_S = 30
PAGE_SLEEP_S = 3


def must_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        sys.exit(f"missing env var: {name}")
    return v


def age_band(dob_str: str | None) -> str | None:
    """Bucket DOB → 'Under 18' / '18-29' / '30-39' / '40-49' / '50-59' / '60+'."""
    if not dob_str:
        return None
    try:
        y, m, d = (int(x) for x in dob_str.split("-"))
        if y < 1900:
            return None
        today = date.today()
        age = today.year - y - ((today.month, today.day) < (m, d))
    except (ValueError, AttributeError):
        return None
    if age < 18:  return "Under 18"
    if age < 30:  return "18-29"
    if age < 40:  return "30-39"
    if age < 50:  return "40-49"
    if age < 60:  return "50-59"
    return "60+"


def postal_sector(postal: str | None) -> str | None:
    """SG postal sector = first 2 digits (e.g. '78' for Yishun/Lentor)."""
    if not postal:
        return None
    p = "".join(c for c in str(postal) if c.isdigit())
    if len(p) < 2:
        return None
    return p[:2]


def main() -> None:
    db = must_env("PLATO_DB")
    key = must_env("PLATO_API_KEY")

    s = requests.Session()
    s.headers.update({"accept": "application/json", "Authorization": f"Bearer {key}"})

    total = 0
    age_counts: Counter = Counter()
    sex_counts: Counter = Counter()
    sector_counts: Counter = Counter()
    tag_counts: Counter = Counter()
    doctor_counts: Counter = Counter()
    referred_by_present = 0
    has_corp = 0
    created_month: Counter = Counter()

    page = 1
    while True:
        r = s.get(f"{BASE}/{db}/patient", params={"current_page": page}, timeout=TIMEOUT_S)
        if r.status_code == 429:
            time.sleep(60); continue
        r.raise_for_status()
        batch = r.json()
        if not isinstance(batch, list) or not batch:
            break
        for p in batch:
            total += 1
            band = age_band(p.get("dob"))
            age_counts[band or "<missing>"] += 1
            sex_counts[(p.get("sex") or "<missing>")] += 1
            sec = postal_sector(p.get("postal"))
            sector_counts[sec or "<missing>"] += 1
            doctors = p.get("doctor") or []
            if isinstance(doctors, list):
                for d in doctors:
                    doctor_counts[d or "<empty>"] += 1
            tags = p.get("tag") or []
            if isinstance(tags, list):
                for t in tags:
                    if isinstance(t, dict):
                        tag_counts[t.get("tag") or "<empty>"] += 1
                    elif isinstance(t, str):
                        tag_counts[t] += 1
            if p.get("referred_by"):
                referred_by_present += 1
            corp = p.get("corporate") or []
            if isinstance(corp, list) and any((c.get("corp") or "").strip() for c in corp if isinstance(c, dict)):
                has_corp += 1
            created = p.get("created_on") or ""
            if isinstance(created, str) and len(created) >= 7:
                created_month[created[:7]] += 1

        rem = r.headers.get("x-ratelimit-remaining")
        time.sleep(60 if rem and rem.isdigit() and int(rem) < 2 else PAGE_SLEEP_S)
        page += 1

    print(f"\n=== {total} patients ===\n")

    def dump(label, counter, total_for_pct=total):
        pop = sum(v for k, v in counter.items() if k not in ("<missing>", "<empty>"))
        cov = (pop / total_for_pct * 100) if total_for_pct else 0
        print(f"--- {label}  ({pop}/{total_for_pct} populated, {cov:.0f}%) ---")
        for k, v in counter.most_common(20):
            print(f"  {v:>4}  {k}")
        print()

    dump("Age band (from dob)", age_counts)
    dump("Sex", sex_counts)
    dump("Postal sector (first 2 digits)", sector_counts)
    dump("Clinical tag", tag_counts)
    dump("Primary doctor (PCL/PKN/PCN)", doctor_counts)
    print(f"--- referred_by populated: {referred_by_present}/{total}  "
          f"({referred_by_present/total*100:.0f}%) ---\n")
    print(f"--- corporate plan populated: {has_corp}/{total}  "
          f"({has_corp/total*100:.0f}%) ---\n")
    print("--- created_on by month ---")
    for k, v in sorted(created_month.items()):
        print(f"  {v:>4}  {k}")


if __name__ == "__main__":
    main()
