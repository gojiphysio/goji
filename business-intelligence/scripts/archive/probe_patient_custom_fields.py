#!/usr/bin/env python3
"""
One-shot probe: identify what Plato's per-patient custom fields actually capture.

Plato exposes three opaque custom-field IDs on every patient record
(custom.WjbS / custom.CrKA / custom.YuGW). Their human labels aren't returned
by /systemsetup and don't appear in the Plato web UI under the IDs we see.
This script pulls every patient, aggregates value frequencies per custom key,
and prints a frequency table. We can then read off whether any of them is
the "How did you hear about us?" referral-source picker.

Privacy: nothing is written to disk. Only the aggregated frequency table is
printed to stdout. Patient names/DOBs/contacts are never logged.

Run:
    cd "/Users/charles/Documents/Claude/Projects/Goji Business Inteligence/scripts"
    python3 probe_patient_custom_fields.py
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter, defaultdict

import requests

BASE = "https://clinic.platomedical.com/api"
TIMEOUT_S = 30
PAGE_SLEEP_S = 3


def must_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        sys.exit(f"missing env var: {name}")
    return v


def main() -> None:
    db = must_env("PLATO_DB")
    key = must_env("PLATO_API_KEY")

    s = requests.Session()
    s.headers.update({"accept": "application/json", "Authorization": f"Bearer {key}"})

    custom_keys: set[str] = set()
    per_key_values: dict[str, Counter] = defaultdict(Counter)
    per_key_present: Counter = Counter()
    total = 0

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
            custom = p.get("custom") or {}
            if not isinstance(custom, dict):
                continue
            for k, v in custom.items():
                custom_keys.add(k)
                if v is None or v == "":
                    per_key_values[k]["<null/empty>"] += 1
                else:
                    per_key_values[k][str(v)] += 1
                    per_key_present[k] += 1
        rem = r.headers.get("x-ratelimit-remaining")
        time.sleep(60 if rem and rem.isdigit() and int(rem) < 2 else PAGE_SLEEP_S)
        page += 1

    print(f"\n=== Probed {total} patients across {page - 1} pages ===\n")
    print(f"custom keys seen: {sorted(custom_keys)}\n")

    for k in sorted(custom_keys):
        present = per_key_present[k]
        coverage = (present / total * 100) if total else 0
        print(f"--- custom.{k}  ({present}/{total} populated, {coverage:.0f}%) ---")
        for val, n in per_key_values[k].most_common(30):
            print(f"  {n:>4}  {val}")
        print()


if __name__ == "__main__":
    main()
