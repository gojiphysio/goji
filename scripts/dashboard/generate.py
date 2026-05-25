#!/usr/bin/env python3
"""
Generate the Goji dashboard HTML with real BigQuery data baked in.

Runs each tile's query for four preset date ranges (7d, 30d, 90d, all), packages
the results into one JSON blob, and substitutes it into template.html. The
resulting file is self-contained and can be opened anywhere or emailed.

No pip dependencies. Uses the `bq` CLI via subprocess, so any Google account
that's already authenticated with `gcloud auth login` and has BigQuery read
access on goji-bi can run this.

Usage:
    cd scripts/dashboard/
    python3 generate.py
    open ../../mockups/dashboard_v2.html
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT = "goji-bi"

HERE     = Path(__file__).resolve().parent
ROOT     = HERE.parent.parent
TEMPLATE = HERE / "template.html"
OUTPUT   = ROOT / "mockups" / "dashboard_v2.html"

PROVIDERS = {
    "PCN": "Claire Ng",
    "PCL": "Cheryl Long",
    "PKN": "Kristy Ng",
}
DIRECTOR_ID = "PCL"


def preset_ranges() -> list[tuple[str, str, date, date]]:
    today = date.today()
    return [
        ("7d",  "Last 7 days",   today - timedelta(days=7),   today),
        ("30d", "Last 30 days",  today - timedelta(days=30),  today),
        ("90d", "Last 90 days",  today - timedelta(days=90),  today),
        # "all" stretches well beyond the data so future-dated invoices show up too
        ("all", "All time",      date(1970, 1, 1),            today + timedelta(days=365)),
    ]


def bq_query(sql: str) -> list[dict]:
    """Run a SQL query via the bq CLI and return result rows as dicts."""
    cmd = [
        "bq", "query",
        "--project_id", PROJECT,
        "--use_legacy_sql=false",
        "--format=json",
        "--quiet",
        sql,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"\nbq query failed:\n{res.stderr}\n--- SQL ---\n{sql}", file=sys.stderr)
        sys.exit(1)
    out = res.stdout.strip()
    return json.loads(out) if out else []


def to_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def to_int(v) -> int:
    if v is None or v == "":
        return 0
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def fetch_kpis(start: date, end: date) -> dict:
    sql = f"""
SELECT
  (SELECT SUM(booking_amount)
   FROM `{PROJECT}.marts.fct_invoice_line`
   WHERE invoice_date BETWEEN '{start}' AND '{end}')                      AS bookings,
  (SELECT SUM(recognised_revenue)
   FROM `{PROJECT}.marts.fct_service_delivered`
   WHERE delivery_date BETWEEN '{start}' AND '{end}')                     AS recognised,
  (SELECT COUNT(DISTINCT patient_id)
   FROM `{PROJECT}.marts.fct_service_delivered`
   WHERE delivery_date BETWEEN '{start}' AND '{end}'
     AND patient_id IS NOT NULL)                                          AS active_patients,
  (SELECT COUNT(*)
   FROM `{PROJECT}.marts.fct_service_delivered`
   WHERE delivery_date BETWEEN '{start}' AND '{end}')                     AS visits
"""
    row = bq_query(sql)[0]
    return {
        "bookings":        to_float(row["bookings"])   or 0.0,
        "recognised":      to_float(row["recognised"]) or 0.0,
        "active_patients": to_int(row["active_patients"]),
        "visits":          to_int(row["visits"]),
    }


def _granularity_for(start: date, end: date) -> tuple[str, str]:
    """Pick bucketing granularity based on the range width.
    Returns (sql_unit, date_format) for use in DATE_TRUNC and FORMAT_DATE."""
    days = (end - start).days
    if days <= 31:
        return "DAY", "%-d %b"
    if days <= 120:
        return "WEEK", "%-d %b"
    return "MONTH", "%b %y"


def _fetch_series(table: str, date_col: str, value_expr: str,
                  start: date, end: date, extra_where: str = "") -> list[dict]:
    gran, date_fmt = _granularity_for(start, end)
    sql = f"""
SELECT
  FORMAT_DATE('{date_fmt}', DATE_TRUNC({date_col}, {gran})) AS label,
  DATE_TRUNC({date_col}, {gran})                            AS bucket,
  {value_expr}                                              AS value
FROM `{PROJECT}.{table}`
WHERE {date_col} BETWEEN '{start}' AND '{end}'
  {extra_where}
GROUP BY bucket, label
ORDER BY bucket
"""
    return [{"label": r["label"], "value": to_float(r["value"]) or 0.0}
            for r in bq_query(sql)]


def fetch_trends(start: date, end: date) -> dict:
    gran, _ = _granularity_for(start, end)
    return {
        "granularity":     gran,
        "bookings":        _fetch_series("marts.fct_invoice_line",       "invoice_date",  "SUM(booking_amount)",        start, end),
        "recognised":      _fetch_series("marts.fct_service_delivered",  "delivery_date", "SUM(recognised_revenue)",    start, end),
        "visits":          _fetch_series("marts.fct_service_delivered",  "delivery_date", "COUNT(*)",                   start, end),
        "active_patients": _fetch_series("marts.fct_service_delivered",  "delivery_date", "COUNT(DISTINCT patient_id)", start, end, "AND patient_id IS NOT NULL"),
    }


def fetch_clinicians(start: date, end: date) -> list[dict]:
    sql = f"""
WITH b AS (
  SELECT clinician_id, SUM(booking_amount) AS bookings
  FROM `{PROJECT}.marts.fct_invoice_line`
  WHERE invoice_date BETWEEN '{start}' AND '{end}'
  GROUP BY clinician_id
),
r AS (
  SELECT clinician_id, SUM(recognised_revenue) AS recognised
  FROM `{PROJECT}.marts.fct_service_delivered`
  WHERE delivery_date BETWEEN '{start}' AND '{end}'
  GROUP BY clinician_id
)
SELECT
  COALESCE(b.clinician_id, r.clinician_id) AS clinician_id,
  COALESCE(b.bookings,   0)                AS bookings,
  COALESCE(r.recognised, 0)                AS recognised
FROM b
FULL OUTER JOIN r USING (clinician_id)
WHERE COALESCE(b.clinician_id, r.clinician_id) IS NOT NULL
ORDER BY bookings DESC
"""
    rows = bq_query(sql)
    return [{
        "clinician_id": r["clinician_id"],
        "name":         PROVIDERS.get(r["clinician_id"], r["clinician_id"]),
        "bookings":     to_float(r["bookings"])   or 0.0,
        "recognised":   to_float(r["recognised"]) or 0.0,
        "is_director":  r["clinician_id"] == DIRECTOR_ID,
    } for r in rows]


def fetch_discounts(start: date, end: date) -> dict:
    totals_sql = f"""
SELECT
  SUM(COALESCE(discount, 0)) AS total_discount,
  SUM(booking_amount)        AS bookings_total
FROM `{PROJECT}.stg.invoice_items`
WHERE invoice_date BETWEEN '{start}' AND '{end}'
  AND classification IN ('sale', 'package_sale')
"""
    t = bq_query(totals_sql)[0]
    total_discount = to_float(t["total_discount"]) or 0.0
    bookings_total = to_float(t["bookings_total"]) or 0.0
    pct = (total_discount / bookings_total * 100.0) if bookings_total > 0 else 0.0

    top_sql = f"""
SELECT
  item_name,
  SUM(COALESCE(discount, 0)) AS total_discount,
  COUNT(*)                   AS times
FROM `{PROJECT}.stg.invoice_items`
WHERE invoice_date BETWEEN '{start}' AND '{end}'
  AND COALESCE(discount, 0) > 0
GROUP BY item_name
ORDER BY total_discount DESC
LIMIT 5
"""
    top_rows = bq_query(top_sql)
    return {
        "total":           total_discount,
        "pct_of_bookings": round(pct, 1),
        "top_items": [{
            "name":     r["item_name"] or "(unnamed)",
            "discount": to_float(r["total_discount"]) or 0.0,
            "times":    to_int(r["times"]),
        } for r in top_rows],
    }


def fetch_treatment_mix(start: date, end: date) -> list[dict]:
    sql = f"""
WITH classified AS (
  SELECT
    CASE
      WHEN STARTS_WITH(item_given_id, 'PHY')    THEN 'Physiotherapy'
      WHEN STARTS_WITH(item_given_id, 'MB-')    THEN 'Physiotherapy'
      WHEN STARTS_WITH(item_given_id, 'CorpPT') THEN 'Physiotherapy'
      WHEN STARTS_WITH(item_given_id, 'CP1:1')
        OR STARTS_WITH(item_given_id, 'CP2:1') THEN 'Clinical Pilates'
      WHEN STARTS_WITH(item_given_id, 'PP1:1')
        OR STARTS_WITH(item_given_id, 'PP2:1') THEN 'Private Pilates'
      WHEN STARTS_WITH(item_given_id, 'SC-')    THEN 'S&C'
      WHEN STARTS_WITH(item_given_id, 'HV-')    THEN 'Home Visit'
      ELSE 'Other'
    END AS category,
    recognised_amount,
    classification
  FROM `{PROJECT}.stg.invoice_items`
  WHERE invoice_date BETWEEN '{start}' AND '{end}'
)
SELECT
  category,
  ROUND(SUM(recognised_amount), 2) AS revenue,
  SUM(CASE WHEN classification IN ('redemption', 'sale') THEN 1 ELSE 0 END) AS visits
FROM classified
GROUP BY category
ORDER BY revenue DESC
"""
    rows = bq_query(sql)
    return [{
        "category": r["category"],
        "revenue":  to_float(r["revenue"]) or 0.0,
        "visits":   to_int(r["visits"]),
    } for r in rows]


def fetch_deferred() -> float:
    sql = f"""
SELECT
  COALESCE(
    (SELECT SUM(booking_amount) FROM `{PROJECT}.marts.fct_invoice_line` WHERE is_package_sale),
    0
  )
  - COALESCE(
    (SELECT SUM(recognised_revenue) FROM `{PROJECT}.marts.fct_service_delivered`
     WHERE delivery_method = 'package_burn'),
    0
  ) AS deferred
"""
    row = bq_query(sql)[0]
    return to_float(row["deferred"]) or 0.0


def fetch_cohorts() -> list[dict]:
    sql = f"""
WITH first_visit AS (
  SELECT patient_id, MIN(delivery_date) AS first_visit_date
  FROM `{PROJECT}.marts.fct_service_delivered`
  WHERE patient_id IS NOT NULL
  GROUP BY patient_id
),
patient_rev AS (
  SELECT patient_id,
         SUM(recognised_revenue) AS lifetime_revenue,
         COUNT(*)                AS lifetime_visits
  FROM `{PROJECT}.marts.fct_service_delivered`
  WHERE patient_id IS NOT NULL
  GROUP BY patient_id
)
SELECT
  FORMAT_DATE('%b %Y', f.first_visit_date) AS cohort,
  EXTRACT(YEAR FROM f.first_visit_date) * 100
    + EXTRACT(MONTH FROM f.first_visit_date)                    AS sort_key,
  COUNT(*)                                                      AS patients,
  ROUND(AVG(pr.lifetime_revenue), 2)                            AS avg_ltv,
  ROUND(AVG(pr.lifetime_visits), 1)                             AS avg_visits
FROM first_visit f
JOIN patient_rev pr USING (patient_id)
GROUP BY cohort, sort_key
ORDER BY sort_key
"""
    rows = bq_query(sql)
    return [{
        "cohort":     r["cohort"],
        "patients":   to_int(r["patients"]),
        "avg_ltv":    to_float(r["avg_ltv"])    or 0.0,
        "avg_visits": to_float(r["avg_visits"]) or 0.0,
    } for r in rows]


def main() -> None:
    if not TEMPLATE.exists():
        print(f"template.html not found at {TEMPLATE}", file=sys.stderr)
        sys.exit(1)

    print("Fetching deferred revenue (range-independent)...")
    deferred = fetch_deferred()

    print("Fetching cohorts (range-independent)...")
    cohorts = fetch_cohorts()

    ranges: dict[str, dict] = {}
    for key, label, start, end in preset_ranges():
        print(f"Fetching {label} ({start} to {end})...")
        ranges[key] = {
            "label":         label,
            "start":         start.isoformat(),
            "end":           end.isoformat(),
            "kpis":          fetch_kpis(start, end),
            "trends":        fetch_trends(start, end),
            "clinicians":    fetch_clinicians(start, end),
            "discounts":     fetch_discounts(start, end),
            "treatment_mix": fetch_treatment_mix(start, end),
        }

    data = {
        "generated_at":  datetime.now().astimezone().isoformat(timespec="seconds"),
        "default_range": "30d",
        "deferred":      deferred,
        "cohorts":       cohorts,
        "ranges":        ranges,
    }

    template = TEMPLATE.read_text()
    if "__DATA_PLACEHOLDER__" not in template:
        print("template.html is missing the __DATA_PLACEHOLDER__ marker", file=sys.stderr)
        sys.exit(1)
    output_html = template.replace("__DATA_PLACEHOLDER__", json.dumps(data, indent=2))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(output_html)
    print(f"\nWrote {OUTPUT}")
    print(f"Open with: open '{OUTPUT}'")


if __name__ == "__main__":
    main()
