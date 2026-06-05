"""
Flask server for the Goji Health operations dashboard.

Serves a single HTML page (template.html) populated with live data pulled from
BigQuery on each request. Sits behind HTTP Basic Auth so it is not publicly
browsable. Designed to run on Cloud Run with Application Default Credentials.

Auth credentials are read from the env vars DASHBOARD_USER and DASHBOARD_PASS
(Cloud Run mounts these from the `dashboard-basic-auth` secret).

A small in-process cache keeps the BQ bill nearly zero: data is recomputed at
most once per CACHE_TTL seconds even if the page is reloaded constantly.
"""
from __future__ import annotations

import hmac
import io
import json
import logging
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

import requests
from flask import Flask, Response, g, request
from google.auth import default as google_auth_default
from google.auth.transport.requests import AuthorizedSession
from google.cloud import bigquery
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from requests.adapters import HTTPAdapter

PROJECT     = os.environ.get("GCP_PROJECT", "goji-bi")
CACHE_TTL   = int(os.environ.get("CACHE_TTL_SECONDS", "300"))
# Founder credential — sees everything, including the financial dashboard.
AUTH_USER   = os.environ.get("DASHBOARD_USER", "")
AUTH_PASS   = os.environ.get("DASHBOARD_PASS", "")
# Staff credential — can reach ONLY the /admin section (patient ops). It must
# never satisfy the founder-only financial routes; see require_roles below.
STAFF_USER  = os.environ.get("STAFF_USER", "")
STAFF_PASS  = os.environ.get("STAFF_PASS", "")
# Local-dev mode: enables Flask reloader and persists BQ results to disk so
# process restarts don't trigger a fresh BQ fetch. Off in prod (Cloud Run).
DEV_MODE    = os.environ.get("DASHBOARD_DEV") == "1"

# Plato API — used ONLY to hydrate patient name + phone live for the staff
# retention worklist. These are never written to BigQuery (the warehouse stays
# PII-free by design). Absent key -> hydration silently no-ops and the worklist
# falls back to the PII-safe initials from dim_patient.
PLATO_BASE      = os.environ.get("PLATO_BASE", "https://clinic.platomedical.com/api")
PLATO_DB        = os.environ.get("PLATO_DB", "gojihealth")
PLATO_API_KEY   = os.environ.get("PLATO_API_KEY", "")
PLATO_TIMEOUT_S = int(os.environ.get("PLATO_TIMEOUT_S", "15"))
CONTACT_TTL     = int(os.environ.get("CONTACT_TTL_SECONDS", "900"))

HERE           = Path(__file__).resolve().parent
TEMPLATE       = HERE / "template.html"
ADMIN_TEMPLATE = HERE / "admin.html"
CACHE_DIR      = HERE / ".cache"

PROVIDERS = {
    "PCN": "Claire Ng",
    "PCL": "Cheryl Long",
    "PKN": "Kristy Ng",
}
DIRECTOR_ID = "PCL"

# Opening-promo "true discount cost" tile: for each pack SKU, we compute the
# implicit discount as (units * pack_size * usual_per_session) - sold_total.
# These usual single-session prices come from the published price list; they
# are not yet in BigQuery as a reference table. Update here when prices change.
#   prefix -> (display service name, usual price per single session SGD)
PROMO_PRICING: dict[str, tuple[str, float]] = {
    "SC":    ("S&C 1:1", 160.0),
    "PP1:1": ("PP 1:1",  150.0),
    "PP2:1": ("PP 1:2",  200.0),
}
PROMO_SKU_RE = re.compile(r"^([A-Z0-9:]+)-(\d+)OP$")


def parse_promo_sku(item_given_id: str) -> tuple[str, int] | None:
    """Return (prefix, pack_size) for an opening-promo SKU, else None."""
    if not item_given_id:
        return None
    m = PROMO_SKU_RE.match(item_given_id)
    if not m:
        return None
    return m.group(1), int(m.group(2))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dashboard")

app = Flask(__name__)

_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()
_bq_client: bigquery.Client | None = None
_bq_client_lock = threading.Lock()


def _disk_cache_get(key: str) -> dict | None:
    """Read a cached BQ result from disk. Dev-mode only — returns None in prod."""
    if not DEV_MODE:
        return None
    p = CACHE_DIR / f"{key}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _disk_cache_put(key: str, value: dict) -> None:
    if not DEV_MODE:
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.json").write_text(json.dumps(value, default=str))


def _make_bq_client() -> bigquery.Client:
    """Build a BigQuery client whose underlying HTTP session has a connection
    pool big enough for the parallel fan-out in build_payload.

    The default urllib3 pool size is 10. We fire ~27 concurrent queries, so
    17 connections were being discarded and remade per cold build (logged as
    'Connection pool is full, discarding connection'). Bumping pool_maxsize
    to 40 lets every concurrent query reuse a pooled TCP connection.
    """
    credentials, _ = google_auth_default()
    session = AuthorizedSession(credentials)
    adapter = HTTPAdapter(pool_connections=4, pool_maxsize=40)
    session.mount("https://", adapter)
    return bigquery.Client(project=PROJECT, _http=session)


def _bq() -> bigquery.Client:
    # Double-checked locking: build_payload fans the BQ queries out across
    # threads, and the first request after a cold start has all those threads
    # racing to lazy-init the client. Without the lock several would each
    # create a Client; the late ones would replace _bq_client and the earlier
    # ones would silently leak.
    global _bq_client
    if _bq_client is None:
        with _bq_client_lock:
            if _bq_client is None:
                _bq_client = _make_bq_client()
    return _bq_client


def _query(sql: str) -> list[dict]:
    return [dict(row) for row in _bq().query(sql).result()]


def _to_float(v) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _to_int(v) -> int:
    if v is None:
        return 0
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def preset_ranges() -> list[tuple[str, str, date, date]]:
    today = date.today()
    return [
        ("7d",  "Last 7 days",   today - timedelta(days=7),   today),
        ("30d", "Last 30 days",  today - timedelta(days=30),  today),
        ("90d", "Last 90 days",  today - timedelta(days=90),  today),
        ("all", "All time",      date(1970, 1, 1),            today + timedelta(days=365)),
    ]


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
    row = _query(sql)[0]
    return {
        "bookings":        _to_float(row["bookings"]),
        "recognised":      _to_float(row["recognised"]),
        "active_patients": _to_int(row["active_patients"]),
        "visits":          _to_int(row["visits"]),
    }


def _granularity_for(start: date, end: date) -> tuple[str, str]:
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
    return [{"label": r["label"], "value": _to_float(r["value"])} for r in _query(sql)]


def fetch_trends(start: date, end: date) -> dict:
    # Four independent BQ queries — fan out so the slowest single series is
    # the wall-time floor instead of their sum.
    gran, _ = _granularity_for(start, end)
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="trends") as ex:
        f_bookings        = ex.submit(_fetch_series, "marts.fct_invoice_line",      "invoice_date",  "SUM(booking_amount)",        start, end)
        f_recognised      = ex.submit(_fetch_series, "marts.fct_service_delivered", "delivery_date", "SUM(recognised_revenue)",    start, end)
        f_visits          = ex.submit(_fetch_series, "marts.fct_service_delivered", "delivery_date", "COUNT(*)",                   start, end)
        f_active_patients = ex.submit(_fetch_series, "marts.fct_service_delivered", "delivery_date", "COUNT(DISTINCT patient_id)", start, end, "AND patient_id IS NOT NULL")
        return {
            "granularity":     gran,
            "bookings":        f_bookings.result(),
            "recognised":      f_recognised.result(),
            "visits":          f_visits.result(),
            "active_patients": f_active_patients.result(),
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
    return [{
        "clinician_id": r["clinician_id"],
        "name":         PROVIDERS.get(r["clinician_id"], r["clinician_id"]),
        "bookings":     _to_float(r["bookings"]),
        "recognised":   _to_float(r["recognised"]),
        "is_director":  r["clinician_id"] == DIRECTOR_ID,
    } for r in _query(sql)]


def fetch_discounts(start: date, end: date) -> dict:
    """True discount cost: implicit opening-promo discount (usual single-session
    price * pack size vs sold price) on pack SKUs, plus ad-hoc line discounts
    on non-promo items. Shape matches v3 design.
    """
    # All sales in range, with per-line booking_amount + adhoc discount.
    sales_sql = f"""
SELECT
  item_given_id,
  item_name,
  COUNT(*)                                                    AS units,
  SUM(booking_amount)                                         AS sold_total,
  SUM(COALESCE(discount, 0))                                  AS adhoc_discount,
  SUM(CASE WHEN COALESCE(discount, 0) > 0 THEN 1 ELSE 0 END)  AS adhoc_lines
FROM `{PROJECT}.stg.invoice_items`
WHERE invoice_date BETWEEN '{start}' AND '{end}'
  AND classification IN ('sale', 'package_sale')
GROUP BY item_given_id, item_name
"""
    rows = _query(sales_sql)

    by_sku: list[dict] = []
    unknown: list[dict] = []
    promo_implicit       = 0.0
    promo_units_total    = 0
    adhoc_nonpromo_total = 0.0
    adhoc_by_item: dict[str, dict] = {}

    bookings_total = 0.0

    for r in rows:
        item_given_id = r["item_given_id"] or ""
        item_name     = r["item_name"] or "(unnamed)"
        units         = _to_int(r["units"])
        sold_total    = _to_float(r["sold_total"])
        adhoc         = _to_float(r["adhoc_discount"])
        adhoc_lines   = _to_int(r["adhoc_lines"])
        bookings_total += sold_total

        parsed = parse_promo_sku(item_given_id)
        if parsed is None:
            # Non-promo line: its discount is just the explicit ad-hoc column.
            if adhoc > 0:
                adhoc_nonpromo_total += adhoc
                existing = adhoc_by_item.get(item_name, {"discount": 0.0, "times": 0})
                adhoc_by_item[item_name] = {
                    "name":     item_name,
                    "discount": existing["discount"] + adhoc,
                    "times":    existing["times"] + adhoc_lines,
                }
            continue

        prefix, pack = parsed
        if prefix not in PROMO_PRICING:
            unknown.append({
                "item_given_id": item_given_id,
                "item_name":     item_name,
                "units":         units,
                "sold_total":    sold_total,
            })
            # Still count the explicit adhoc discount so it's not lost
            adhoc_nonpromo_total += adhoc
            continue

        service, unit_price = PROMO_PRICING[prefix]
        usual_total = units * pack * unit_price
        # Discount = usual_total - sold_total (covers both the implicit
        # promo gap and any extra ad-hoc discounts on top, since adhoc
        # already reduces sold_total).
        discount = usual_total - sold_total
        promo_implicit    += discount
        promo_units_total += units

        label = f"{service} {pack}-pack" if pack > 1 else f"{service} single"
        by_sku.append({
            "item_given_id": item_given_id,
            "service":       service,
            "pack":          pack,
            "label":         label,
            "units":         units,
            "usual_total":   round(usual_total, 2),
            "sold_total":    round(sold_total, 2),
            "discount":      round(discount, 2),
        })

    by_sku.sort(key=lambda x: x["discount"], reverse=True)
    top_adhoc = sorted(
        adhoc_by_item.values(), key=lambda x: x["discount"], reverse=True,
    )[:5]

    total_true = promo_implicit + adhoc_nonpromo_total
    pct = (total_true / bookings_total * 100.0) if bookings_total > 0 else 0.0

    return {
        "total_true":         round(total_true, 2),
        "promo_implicit":     round(promo_implicit, 2),
        "adhoc_nonpromo":     round(adhoc_nonpromo_total, 2),
        "pct_of_bookings":    round(pct, 1),
        "promo_units_total":  promo_units_total,
        "by_sku":             by_sku,
        "top_adhoc_items":    [{
            "name":     it["name"],
            "discount": round(it["discount"], 2),
            "times":    it["times"],
        } for it in top_adhoc],
        "unknown_promo_skus": unknown,
    }


def fetch_payment_methods(start: date, end: date) -> list[dict]:
    """Return [{method, total_amount, txn_count}] from unnested invoice payments.

    Plato stores payments as a JSON array on each invoice payload at
    `payload.payment[]`, with fields `mode`, `amount`, and a `void` flag.
    Method names are normalised to lowercase so the dashboard JS can find
    'platopay' regardless of how Plato cased it.
    """
    sql = f"""
WITH payments AS (
  SELECT
    LOWER(JSON_VALUE(p, '$.mode'))                     AS method,
    SAFE_CAST(JSON_VALUE(p, '$.amount') AS FLOAT64)    AS amount,
    SAFE_CAST(JSON_VALUE(p, '$.void')   AS INT64)      AS is_void
  FROM `{PROJECT}.stg.invoices` AS inv,
       UNNEST(JSON_QUERY_ARRAY(inv.payload, '$.payment')) AS p
  WHERE inv.invoice_date BETWEEN '{start}' AND '{end}'
    AND inv.is_finalized = TRUE
    AND NOT inv.is_void
)
SELECT
  method,
  ROUND(SUM(amount), 2) AS total_amount,
  COUNT(*)              AS txn_count
FROM payments
WHERE COALESCE(is_void, 0) = 0
  AND method IS NOT NULL
GROUP BY method
ORDER BY total_amount DESC
"""
    return [{
        "method":       r["method"],
        "total_amount": _to_float(r["total_amount"]),
        "txn_count":    _to_int(r["txn_count"]),
    } for r in _query(sql)]


def fetch_appointments(start: date, end: date) -> list[dict]:
    """Per-session deliveries used by the commission calculator.

    Surfaces `initial_lastname` (e.g. "C. Wong") from marts.dim_patient when
    available, falling back to patient_id. Full names are never stored in
    BQ — the ingestion job derives the initial + last token in memory and
    only the derived scalar lands.
    """
    sql = f"""
SELECT
  sd.delivery_date,
  sd.clinician_id,
  sd.patient_id,
  p.initial_lastname,
  sd.item_name,
  sd.recognised_revenue
FROM `{PROJECT}.marts.fct_service_delivered` sd
LEFT JOIN `{PROJECT}.marts.dim_patient` p USING (patient_id)
WHERE sd.delivery_date BETWEEN '{start}' AND '{end}'
  AND sd.clinician_id IS NOT NULL
  AND COALESCE(sd.recognised_revenue, 0) > 0
ORDER BY sd.delivery_date, sd.clinician_id
"""
    return [{
        "date":         r["delivery_date"].isoformat() if r["delivery_date"] else None,
        "clinician_id": r["clinician_id"],
        "patient":      r["initial_lastname"] or r["patient_id"] or "—",
        "service":      r["item_name"] or "(unnamed)",
        "value":        _to_float(r["recognised_revenue"]),
    } for r in _query(sql)]


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
    return [{
        "category": r["category"],
        "revenue":  _to_float(r["revenue"]),
        "visits":   _to_int(r["visits"]),
    } for r in _query(sql)]


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
    return _to_float(_query(sql)[0]["deferred"])


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
    return [{
        "cohort":     r["cohort"],
        "patients":   _to_int(r["patients"]),
        "avg_ltv":    _to_float(r["avg_ltv"]),
        "avg_visits": _to_float(r["avg_visits"]),
    } for r in _query(sql)]


# Patient base / demographics / referrals -----------------------------------
#
# These are range-independent like `deferred` and `cohorts`: "who are our
# patients and where did they come from" is a snapshot of the whole base, not
# a view of activity in the last N days. The range selector at the top of
# the page does not filter these tiles.

# Ordering used to plot the age-band chart. Anything not in this list (or
# NULL) is dropped — the chart shows only "known" bands so a stray legacy
# value doesn't poison the axis.
AGE_BANDS_ORDERED = ["Under 18", "18-29", "30-39", "40-49", "50-59", "60+"]


def fetch_patient_demographics() -> dict:
    """Patient-base composition: age band, sex, top clinical tags.

    Returns:
        {
          "total_patients": int,
          "age_bands":   [{"label": "30-39", "count": 32}, ...],   # fixed order
          "sex":         [{"label": "Female", "count": 46}, ...],  # desc by count
          "top_tags":    [{"label": "Musculoskeletal", "count": 25}, ...],  # top 8 desc
        }

    All-time snapshot of marts.dim_patient. Patients with missing age/sex are
    silently excluded from those tiles (each tile shows the populated subset)
    — `total_patients` is the row count of the whole table for reference.
    """
    total = _to_int(_query(
        f"SELECT COUNT(*) AS n FROM `{PROJECT}.marts.dim_patient`"
    )[0]["n"])

    age_rows = _query(f"""
SELECT age_band, COUNT(*) AS n
FROM `{PROJECT}.marts.dim_patient`
WHERE age_band IS NOT NULL
GROUP BY age_band
""")
    by_band = {r["age_band"]: _to_int(r["n"]) for r in age_rows}
    age_bands = [{"label": b, "count": by_band.get(b, 0)} for b in AGE_BANDS_ORDERED]

    sex_rows = _query(f"""
SELECT sex, COUNT(*) AS n
FROM `{PROJECT}.marts.dim_patient`
WHERE sex IS NOT NULL AND sex != ''
GROUP BY sex
ORDER BY n DESC
""")
    sex = [{"label": r["sex"], "count": _to_int(r["n"])} for r in sex_rows]

    tag_rows = _query(f"""
SELECT tag AS label, COUNT(*) AS n
FROM `{PROJECT}.marts.dim_patient`, UNNEST(tags) AS tag
WHERE tag IS NOT NULL AND tag != ''
GROUP BY label
ORDER BY n DESC
LIMIT 8
""")
    top_tags = [{"label": r["label"], "count": _to_int(r["n"])} for r in tag_rows]

    return {
        "total_patients": total,
        "age_bands":      age_bands,
        "sex":            sex,
        "top_tags":       top_tags,
    }


# Display order for the monthly-acquisition stacked bar. The chart legend
# reads in this order; the dashboard JS also relies on this list when picking
# colours so that "medical" is always GOJI red, "online" is always COBALT,
# etc. Keep in sync with the SOURCE_TYPE_* constants in
# scripts/ingestion/plato_contact/main.py.
SOURCE_TYPES_ORDERED = [
    "medical", "word_of_mouth", "partner", "online", "walk_in", "other", "unattributed",
]

# Human-friendly labels surfaced to the dashboard. "unattributed" is what we
# show when a patient has no referred_by recorded — distinct from "other"
# which is a contact in Plato that didn't match any classification rule.
SOURCE_TYPE_LABELS = {
    "medical":        "Medical referral",
    "word_of_mouth":  "Word-of-mouth",
    "partner":        "Partner",
    "online":         "Online booking",
    "walk_in":        "Walk-in",
    "other":          "Other contact",
    "unattributed":   "Not recorded",
}


def fetch_patient_referrals() -> dict:
    """Referral source breakdown joined against dim_referral_source.

    Returns:
        {
          "total_patients":   int,
          "referred":         int,    # have a non-null referred_by
          "pct_referred":     float,  # share in %, 1dp
          "by_source_type":   [{"source_type", "label", "count"}, ...],  # desc
          "top_sources":      [{"contact_id", "label", "source_type",
                                 "count"}, ...],                         # top 10
          "monthly":          [{"month": "2026-04", "label": "Apr 26",
                                 "<source_type>": count, ...}, ...],     # asc
          "source_types":     SOURCE_TYPES_ORDERED,
          "source_labels":    SOURCE_TYPE_LABELS,
        }

    All-time, range-independent — referral attribution is a snapshot of the
    whole patient base, not a window of recent activity. To restrict to
    recent acquisition, slice the result client-side on `monthly`.
    """
    base = _query(f"""
SELECT
  COUNT(*)                                                AS total,
  COUNTIF(referred_by IS NOT NULL AND referred_by != '')  AS referred
FROM `{PROJECT}.marts.dim_patient`
""")[0]
    total    = _to_int(base["total"])
    referred = _to_int(base["referred"])
    pct      = round((referred / total * 100), 1) if total else 0.0

    by_type_rows = _query(f"""
SELECT
  COALESCE(s.source_type, 'unattributed') AS source_type,
  COUNT(*)                                AS n
FROM `{PROJECT}.marts.dim_patient` p
LEFT JOIN `{PROJECT}.marts.dim_referral_source` s
  ON p.referred_by = s.contact_id
WHERE p.referred_by IS NOT NULL AND p.referred_by != ''
GROUP BY source_type
ORDER BY n DESC
""")
    by_source_type = [{
        "source_type": r["source_type"],
        "label":       SOURCE_TYPE_LABELS.get(r["source_type"], r["source_type"]),
        "count":       _to_int(r["n"]),
    } for r in by_type_rows]

    top_rows = _query(f"""
SELECT
  p.referred_by                                              AS contact_id,
  COALESCE(s.display_label, '(unknown contact)')             AS label,
  COALESCE(s.source_type, 'unattributed')                    AS source_type,
  COUNT(*)                                                   AS n
FROM `{PROJECT}.marts.dim_patient` p
LEFT JOIN `{PROJECT}.marts.dim_referral_source` s
  ON p.referred_by = s.contact_id
WHERE p.referred_by IS NOT NULL AND p.referred_by != ''
GROUP BY contact_id, label, source_type
ORDER BY n DESC, label
LIMIT 10
""")
    top_sources = [{
        "contact_id":  r["contact_id"],
        "label":       r["label"],
        "source_type": r["source_type"],
        "count":       _to_int(r["n"]),
    } for r in top_rows]

    # Monthly acquisition, pivoted to one column per source_type. The
    # 'unattributed' bucket captures patients with no referred_by recorded —
    # almost always the back-fill of legacy records, but we keep it visible
    # rather than silently dropping it.
    monthly_rows = _query(f"""
SELECT
  FORMAT_DATE('%Y-%m', DATE_TRUNC(p.created_on, MONTH))      AS month,
  FORMAT_DATE('%b %y', DATE_TRUNC(p.created_on, MONTH))      AS label,
  COALESCE(s.source_type, 'unattributed')                    AS source_type,
  COUNT(*)                                                   AS n
FROM `{PROJECT}.marts.dim_patient` p
LEFT JOIN `{PROJECT}.marts.dim_referral_source` s
  ON p.referred_by = s.contact_id
WHERE p.created_on IS NOT NULL
GROUP BY month, label, source_type
ORDER BY month
""")
    by_month: dict[str, dict] = {}
    for r in monthly_rows:
        m = r["month"]
        entry = by_month.setdefault(m, {"month": m, "label": r["label"]})
        # Use unattributed when patient had no referred_by recorded; that's
        # encoded by the COALESCE above. The COUNTIF in `base` already
        # measures the same thing differently — we deliberately keep both.
        st = r["source_type"]
        if st not in by_month[m]:
            entry[st] = 0
        entry[st] = entry[st] + _to_int(r["n"])
    monthly = sorted(by_month.values(), key=lambda x: x["month"])

    return {
        "total_patients": total,
        "referred":       referred,
        "pct_referred":   pct,
        "by_source_type": by_source_type,
        "top_sources":    top_sources,
        "monthly":        monthly,
        "source_types":   SOURCE_TYPES_ORDERED,
        "source_labels":  SOURCE_TYPE_LABELS,
    }


MISMATCH_WINDOW_DAYS = int(os.environ.get("MISMATCH_WINDOW_DAYS", "30"))


def fetch_invoice_doctor_mismatches() -> dict:
    """Alert-only check: list non-void invoices whose `doctor` disagrees
    with the same-day appointment-calendar doctor for the same patient.

    Reads `marts.fct_invoice_doctor_mismatches`, which does the cross-ref in
    pure SQL against stg.appointments + stg.invoices. The Plato API is no
    longer touched on the dashboard hot path — appointments land in BQ via the
    plato-appointments-ingest Cloud Run Job (15-min cadence).

    Cleared automatically — when an invoice is corrected in Plato, the next
    appointment ingestion + dashboard cache refresh drops the resolved invoice
    off the list.

    Returns:
        {
          "available": bool,        # False if the BQ read failed
          "window_days": int,
          "mismatches": [...],      # see fields below
          "no_appt_count": int,     # invoices we couldn't cross-ref
          "checked_at": iso ts,
          "error": str | None,
        }
    """
    result = {
        "available": True,
        "window_days": MISMATCH_WINDOW_DAYS,
        "mismatches": [],
        "no_appt_count": 0,
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "error": None,
    }

    sql = f"""
SELECT
  invoice_id,
  invoice_label,
  invoice_date,
  patient_id,
  initial_lastname,
  invoice_clinician_id,
  appt_clinician_ids,
  status,
  created_by,
  last_edited_by,
  total
FROM `{PROJECT}.marts.fct_invoice_doctor_mismatches`
WHERE invoice_date >= DATE_SUB(CURRENT_DATE(), INTERVAL {MISMATCH_WINDOW_DAYS} DAY)
  AND status IN ('mismatch', 'no_appointment')
ORDER BY invoice_date DESC, invoice_label DESC
"""
    try:
        rows = _query(sql)
    except Exception as e:
        log.exception("invoice-doctor mismatch query failed: %s", e)
        result["available"] = False
        result["error"] = f"BigQuery error: {e}"
        return result

    mismatches: list[dict] = []
    no_appt = 0
    for r in rows:
        if r["status"] == "no_appointment":
            no_appt += 1
            continue
        appt_ids = list(r.get("appt_clinician_ids") or [])
        invoice_clinician = r.get("invoice_clinician_id")
        mismatches.append({
            "invoice_id":          r["invoice_id"],
            "invoice_no":          r.get("invoice_label") or r["invoice_id"][:8],
            "date":                r["invoice_date"].isoformat() if r.get("invoice_date") else None,
            "patient":             r.get("initial_lastname") or r.get("patient_id") or "—",
            "invoice_doctor":      invoice_clinician,
            "invoice_doctor_name": PROVIDERS.get(invoice_clinician or "", invoice_clinician or "(unset)"),
            "appt_doctors":        sorted(appt_ids),
            "appt_doctor_names":   [PROVIDERS.get(d, d) for d in sorted(appt_ids)],
            "created_by":          r.get("created_by"),
            "last_edited_by":      r.get("last_edited_by"),
            "total":               _to_float(r.get("total")),
        })

    result["mismatches"]    = mismatches
    result["no_appt_count"] = no_appt
    log.info("  mismatches found: %d (window=%dd, %d invoices had no same-day appt)",
             len(mismatches), MISMATCH_WINDOW_DAYS, no_appt)
    return result


def build_payload() -> dict:
    """Fan all BQ queries out in parallel. ~27 queries; serial wall time was
    ~38s, parallel is limited by the slowest single query (~3-5s).

    BigQuery client is thread-safe; each fetch_* spawns its own job and
    blocks on .result() so threads sleep on I/O rather than spinning on the
    GIL. The thread pool is sized to comfortably cover all in-flight queries
    so nothing queues behind other work in this request.
    """
    log.info("Building dashboard payload from BigQuery (parallel)")
    today = date.today()
    pmt_start  = today - timedelta(days=30)
    # Commission calculator needs the per-session ledger for the current pay
    # cycle plus a generous trailing window so custom-range reports still work.
    # 120 days covers ~4 pay cycles (26th -> 25th).
    appt_start = today - timedelta(days=120)
    presets    = preset_ranges()

    # max_workers sized to cover every concurrent fetch this request fires:
    # 7 top-level + 4 ranges × 5 metrics = 27. Round up to 32 for headroom.
    with ThreadPoolExecutor(max_workers=32, thread_name_prefix="bq") as ex:
        # Range-independent (or fixed-window) fetches.
        f_deferred      = ex.submit(fetch_deferred)
        f_cohorts       = ex.submit(fetch_cohorts)
        f_demographics  = ex.submit(fetch_patient_demographics)
        f_referrals     = ex.submit(fetch_patient_referrals)
        f_payments      = ex.submit(fetch_payment_methods, pmt_start, today)
        f_appointments  = ex.submit(fetch_appointments, appt_start, today)
        f_mismatches    = ex.submit(fetch_invoice_doctor_mismatches)

        # Per-range fetches. Each fetch_* is independent so they all race.
        range_jobs: dict[str, dict] = {}
        for key, label, start, end in presets:
            range_jobs[key] = {
                "label":         label,
                "start":         start.isoformat(),
                "end":           end.isoformat(),
                "kpis":          ex.submit(fetch_kpis, start, end),
                "trends":        ex.submit(fetch_trends, start, end),
                "clinicians":    ex.submit(fetch_clinicians, start, end),
                "discounts":     ex.submit(fetch_discounts, start, end),
                "treatment_mix": ex.submit(fetch_treatment_mix, start, end),
            }

        # Block on results. If any future raised, .result() re-raises here and
        # the still-running ones get cancelled when the executor exits.
        ranges: dict[str, dict] = {}
        for key, v in range_jobs.items():
            ranges[key] = {
                "label":         v["label"],
                "start":         v["start"],
                "end":           v["end"],
                "kpis":          v["kpis"].result(),
                "trends":        v["trends"].result(),
                "clinicians":    v["clinicians"].result(),
                "discounts":     v["discounts"].result(),
                "treatment_mix": v["treatment_mix"].result(),
            }

        return {
            "generated_at":      datetime.now().astimezone().isoformat(timespec="seconds"),
            "default_range":     "30d",
            "deferred":          f_deferred.result(),
            "cohorts":           f_cohorts.result(),
            "demographics":      f_demographics.result(),
            "referrals":         f_referrals.result(),
            "appointments":      f_appointments.result(),
            "payment_by_method": f_payments.result(),
            "ranges":            ranges,
            "doctor_mismatches": f_mismatches.result(),
        }


def get_payload() -> dict:
    """Return the dashboard JSON payload, using cache if fresh.

    The shell HTML is served immediately on `/` without touching BQ; the
    browser then fetches this via `/api/data`. Splitting the two phases lets
    the user see a loading state from the first byte instead of staring at a
    blank tab during the cold-cache BQ work.
    """
    now = time.time()
    with _cache_lock:
        entry = _cache.get("payload")
        if entry and now - entry[0] < CACHE_TTL:
            return entry[1]

    cached = _disk_cache_get("payload")
    if cached is not None:
        with _cache_lock:
            _cache["payload"] = (now, cached)
        return cached

    payload = build_payload()

    with _cache_lock:
        _cache["payload"] = (now, payload)
    _disk_cache_put("payload", payload)
    return payload


def get_shell_html() -> str:
    """Return the dashboard shell HTML. No BQ work — ships in milliseconds.

    Data placeholder is left as an empty object; the page fetches the real
    payload from `/api/data` after first paint.
    """
    return TEMPLATE.read_text().replace("__DATA_PLACEHOLDER__", "{}")


# Staff admin dashboard: patient retention worklist --------------------------
#
# A front-desk tool, separate from the founder financials. It tiers patients by
# how long since their last visit and surfaces an actionable call list. The
# retention facts come from BigQuery (PII-free); patient name + phone are
# hydrated LIVE from Plato at render time and never persisted.

TIER_RANK = {"red": 0, "orange": 1, "yellow": 2, "green": 3}
ACTIONABLE_TIERS = ("yellow", "orange", "red")
VALID_FOLLOWUP_STATUSES = {"contacted", "snoozed", "dismissed", "active"}
DEFAULT_SNOOZE_DAYS = 7


def is_snoozed(status: str | None, snooze_until: date | None, today: date) -> bool:
    """A snooze is only active while snooze_until is still in the future."""
    return status == "snoozed" and snooze_until is not None and snooze_until > today


def is_actionable(tier: str, has_future_appt: bool, status: str | None,
                  snooze_until: date | None, today: date) -> bool:
    """Whether a patient should appear on the front desk's call list.

    Actionable = lapsed (yellow/orange/red) AND has no future appointment booked
    AND hasn't been dismissed or is currently snoozed. 'contacted' stays
    actionable — reaching out once doesn't take them off the list until they
    re-book (which shows as a future appointment) or are dismissed.
    """
    if tier not in ACTIONABLE_TIERS:
        return False
    if has_future_appt or status == "dismissed":
        return False
    return not is_snoozed(status, snooze_until, today)

# Plato patient records aren't documented field-for-field, so probe the phone
# under the keys we've seen across Plato deployments, in priority order.
_PHONE_KEYS = (
    "mobile", "handphone", "hp", "phone", "tel", "telephone",
    "contact_number", "contactnumber", "contact",
)

_plato_session: requests.Session | None = None
_plato_session_lock = threading.Lock()
_contact_cache: dict[str, tuple[float, dict]] = {}
_contact_cache_lock = threading.Lock()


def _plato() -> requests.Session | None:
    """Lazily build the Plato API session, or None if no key is configured."""
    global _plato_session
    if not PLATO_API_KEY:
        return None
    if _plato_session is None:
        with _plato_session_lock:
            if _plato_session is None:
                s = requests.Session()
                s.headers.update({
                    "accept": "application/json",
                    "Authorization": f"Bearer {PLATO_API_KEY}",
                })
                _plato_session = s
    return _plato_session


def _extract_full_name(patient: dict) -> str | None:
    """Plato exposes `name` as a string or a {first,last} dict. Return the full
    name (front desk needs it to make the call), or None."""
    name = patient.get("name")
    if isinstance(name, dict):
        full = f"{name.get('first', '') or ''} {name.get('last', '') or ''}".strip()
        return full or None
    if isinstance(name, str):
        return name.strip() or None
    return None


def _extract_phone(patient: dict) -> str | None:
    """Pull a phone number out of a Plato patient record, defensively probing
    the keys we've observed (top-level string or nested {number/value})."""
    for k in _PHONE_KEYS:
        v = patient.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            for kk in ("number", "value", "mobile", "phone"):
                vv = v.get(kk)
                if isinstance(vv, str) and vv.strip():
                    return vv.strip()
    return None


def _fetch_one_contact(patient_id: str) -> tuple[str, dict]:
    """Fetch one patient's name + phone from Plato, with a short in-process TTL
    cache. Never raises and never persists — on any failure returns {} so the
    worklist falls back to the PII-safe initials."""
    sess = _plato()
    if sess is None:
        return patient_id, {}
    now = time.time()
    with _contact_cache_lock:
        entry = _contact_cache.get(patient_id)
        if entry and now - entry[0] < CONTACT_TTL:
            return patient_id, entry[1]
    info: dict = {}
    try:
        r = sess.get(f"{PLATO_BASE}/{PLATO_DB}/patient/{patient_id}",
                     timeout=PLATO_TIMEOUT_S)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                data = data[0] if data else {}
            if isinstance(data, dict):
                info = {
                    "full_name": _extract_full_name(data),
                    "phone":     _extract_phone(data),
                }
        else:
            log.warning("plato patient lookup %s -> %s", patient_id, r.status_code)
    except (requests.RequestException, ValueError) as e:
        log.warning("plato patient lookup %s failed: %s", patient_id, e)
    with _contact_cache_lock:
        _contact_cache[patient_id] = (now, info)
    return patient_id, info


def hydrate_plato_contacts(patient_ids: list[str]) -> dict[str, dict]:
    """Fetch name + phone for a set of patient_ids live from Plato, in parallel.

    Called only for the actionable worklist (a small set), so call volume to
    Plato stays low. Returns {patient_id: {"full_name", "phone"}}; missing or
    failed lookups map to {} and the caller degrades to initials.
    """
    ids = [p for p in dict.fromkeys(patient_ids) if p]
    if not ids or _plato() is None:
        return {pid: {} for pid in ids}
    out: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(8, len(ids)),
                            thread_name_prefix="plato") as ex:
        for pid, info in ex.map(_fetch_one_contact, ids):
            out[pid] = info
    return out


def fetch_patient_retention() -> dict:
    """Build the retention worklist: per-tier summary + a per-patient list.

    Tiers and future-appointment status come from marts.fct_patient_retention
    (PII-free). Follow-up state (contacted/snoozed/dismissed) comes from
    marts.patient_followup_latest. A patient is "actionable" — i.e. needs a
    call — when they're yellow/orange/red, have no future appointment booked,
    and haven't been dismissed or snoozed. Names + phones are hydrated live for
    the actionable set only.
    """
    sql = f"""
SELECT
  r.patient_id,
  r.tier,
  r.days_since_last,
  r.last_visit_date,
  r.next_appt_date,
  r.has_future_appt,
  r.clinician_id,
  r.age_band,
  r.initial_lastname,
  f.status       AS followup_status,
  f.snooze_until AS followup_snooze_until,
  f.note         AS followup_note,
  f.updated_at   AS followup_at,
  f.updated_by   AS followup_by
FROM `{PROJECT}.marts.fct_patient_retention` r
LEFT JOIN `{PROJECT}.marts.patient_followup_latest` f USING (patient_id)
"""
    rows = _query(sql)
    today = date.today()
    summary = {
        "total": 0, "green": 0, "yellow": 0, "orange": 0, "red": 0,
        "needs_followup": 0, "already_booked": 0, "snoozed": 0, "dismissed": 0,
    }
    patients: list[dict] = []
    actionable_ids: list[str] = []

    for r in rows:
        tier   = r["tier"]
        status = r.get("followup_status")
        snooze_until = r.get("followup_snooze_until")
        has_future   = bool(r["has_future_appt"])

        summary["total"] += 1
        if tier in summary:
            summary[tier] += 1
        if has_future:
            summary["already_booked"] += 1
        if status == "dismissed":
            summary["dismissed"] += 1
        if is_snoozed(status, snooze_until, today):
            summary["snoozed"] += 1

        actionable = is_actionable(tier, has_future, status, snooze_until, today)
        if actionable:
            summary["needs_followup"] += 1
            actionable_ids.append(r["patient_id"])

        patients.append({
            "patient_id":       r["patient_id"],
            "tier":             tier,
            "days_since_last":  _to_int(r["days_since_last"]),
            "last_visit":       r["last_visit_date"].isoformat() if r["last_visit_date"] else None,
            "next_appt":        r["next_appt_date"].isoformat() if r["next_appt_date"] else None,
            "has_future_appt":  has_future,
            "clinician_id":     r["clinician_id"],
            "clinician":        PROVIDERS.get(r["clinician_id"], r["clinician_id"] or "—"),
            "age_band":         r["age_band"],
            "initial_lastname": r["initial_lastname"],
            "followup_status":  status,
            "followup_note":    r.get("followup_note"),
            "snooze_until":     snooze_until.isoformat() if snooze_until else None,
            "actionable":       actionable,
        })

    contacts = hydrate_plato_contacts(actionable_ids)
    for p in patients:
        c = contacts.get(p["patient_id"]) or {}
        p["name"]  = c.get("full_name") or p["initial_lastname"] or "—"
        p["phone"] = c.get("phone")

    # Most urgent first: actionable before the rest, then by tier severity, then
    # by how long they've been away.
    patients.sort(key=lambda x: (
        0 if x["actionable"] else 1,
        TIER_RANK.get(x["tier"], 9),
        -x["days_since_last"],
    ))

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "summary":      summary,
        "patients":     patients,
    }


def get_retention() -> dict:
    """Cached accessor for the retention worklist (same TTL as the financials).

    Caching also keeps live Plato hydration cheap. The cache key is invalidated
    when a follow-up action is recorded so the worklist reflects it on reload.
    """
    now = time.time()
    with _cache_lock:
        entry = _cache.get("retention")
        if entry and now - entry[0] < CACHE_TTL:
            return entry[1]
    data = fetch_patient_retention()
    with _cache_lock:
        _cache["retention"] = (now, data)
    return data


def get_admin_shell_html() -> str:
    """Return the admin dashboard HTML. No BQ work; it fetches /api/admin/retention."""
    return ADMIN_TEMPLATE.read_text()


def record_followup(patient_id: str, status: str, *, note: str | None = None,
                    snooze_days: int | None = None,
                    updated_by: str | None = None) -> None:
    """Append one follow-up event (append-only; latest wins). Snoozing without
    an explicit duration defaults to one week."""
    snooze_until: str | None = None
    if status == "snoozed":
        days = snooze_days if isinstance(snooze_days, int) and snooze_days > 0 else DEFAULT_SNOOZE_DAYS
        snooze_until = (date.today() + timedelta(days=days)).isoformat()

    row = {
        "event_id":     str(uuid.uuid4()),
        "patient_id":   patient_id,
        "status":       status,
        "note":         (note or None),
        "snooze_until": snooze_until,
        "updated_by":   updated_by,
        "updated_at":   datetime.now(timezone.utc).isoformat(),
    }
    # Explicit schema so the append never depends on autodetect (e.g. a row with
    # a null snooze_until). Matches sql/marts/40_patient_followup_events.sql.
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema=[
            bigquery.SchemaField("event_id",     "STRING",    mode="REQUIRED"),
            bigquery.SchemaField("patient_id",   "STRING",    mode="REQUIRED"),
            bigquery.SchemaField("status",       "STRING",    mode="REQUIRED"),
            bigquery.SchemaField("note",         "STRING"),
            bigquery.SchemaField("snooze_until", "DATE"),
            bigquery.SchemaField("updated_by",   "STRING"),
            bigquery.SchemaField("updated_at",   "TIMESTAMP", mode="REQUIRED"),
        ],
    )
    _bq().load_table_from_json(
        [row], f"{PROJECT}.marts.patient_followup_events", job_config=job_config,
    ).result()
    with _cache_lock:
        _cache.pop("retention", None)


def fetch_pl_window(start: date, end: date) -> dict:
    """Recompute the P&L revenue + payment fee inputs for an arbitrary window.

    Reuses fetch_kpis / fetch_clinicians / fetch_payment_methods so the rules
    stay in lock-step with the main dashboard.
    """
    key = f"pl_window_{start.isoformat()}_{end.isoformat()}"
    cached = _disk_cache_get(key)
    if cached is not None:
        return cached

    kpis              = fetch_kpis(start, end)
    clinicians        = fetch_clinicians(start, end)
    payment_by_method = fetch_payment_methods(start, end)
    result = {
        "start":             start.isoformat(),
        "end":               end.isoformat(),
        "days":              (end - start).days + 1,
        "recognised":        kpis["recognised"],
        "bookings":          kpis["bookings"],
        "clinicians":        clinicians,
        "payment_by_method": payment_by_method,
    }
    _disk_cache_put(key, result)
    return result


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


# Singapore P&L Excel export ------------------------------------------------

_SGD_FMT = '_-"$"* #,##0.00_-;[Red]_-"$"* (#,##0.00);_-"$"* "-"??_-;_-@_-'

def _xlsx_pl_statement(payload: dict) -> bytes:
    """Build a Singapore-style P&L statement xlsx from the client's snapshot.

    The browser already has all the figures rendered on screen, so the client
    POSTs them and we just format them — guarantees the Excel file matches
    what the user saw at the moment they clicked Download.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "P&L Statement"
    ws.sheet_view.showGridLines = False

    # Column widths: A=label, B=sub-amount, C=total
    ws.column_dimensions["A"].width = 48
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 18

    # Styles
    title_font   = Font(name="Calibri", size=14, bold=True)
    sub_font     = Font(name="Calibri", size=10, italic=True, color="555555")
    section_font = Font(name="Calibri", size=11, bold=True)
    label_font   = Font(name="Calibri", size=10)
    total_font   = Font(name="Calibri", size=11, bold=True)
    net_font     = Font(name="Calibri", size=12, bold=True)
    header_fill  = PatternFill("solid", fgColor="F2EEE5")
    thin         = Side(style="thin", color="C9C2B6")
    medium       = Side(style="medium", color="2A2622")
    top_thin     = Border(top=thin)
    top_medium   = Border(top=medium)
    double_btm   = Border(top=thin, bottom=Side(style="double", color="2A2622"))

    entity = payload.get("entity") or "Goji Health Pte Ltd"
    period = payload.get("period") or {}
    period_label = period.get("label") or ""
    start = period.get("start") or ""
    end   = period.get("end") or ""
    days  = period.get("days") or ""
    view  = payload.get("view") or "cash"  # 'cash' or 'full'

    row = 1
    ws.cell(row=row, column=1, value=entity).font = title_font
    row += 1
    ws.cell(row=row, column=1, value="Statement of Profit or Loss").font = section_font
    row += 1
    sub = f"For the period {start} to {end}" if (start and end) else period_label
    if days:
        sub = f"{sub}  ({days} days)"
    ws.cell(row=row, column=1, value=sub).font = sub_font
    row += 1
    ws.cell(row=row, column=1, value="All amounts in SGD").font = sub_font
    row += 2

    # Header row
    ws.cell(row=row, column=1, value="").fill = header_fill
    c = ws.cell(row=row, column=2, value="Sub-total")
    c.font = section_font; c.fill = header_fill; c.alignment = Alignment(horizontal="right")
    c = ws.cell(row=row, column=3, value="Amount")
    c.font = section_font; c.fill = header_fill; c.alignment = Alignment(horizontal="right")
    a = ws.cell(row=row, column=1, value="Description")
    a.font = section_font; a.fill = header_fill
    row += 2

    def write_section_header(title: str):
        nonlocal row
        c = ws.cell(row=row, column=1, value=title)
        c.font = section_font
        row += 1

    def write_line(label: str, amount, *, sub: bool = False, bold: bool = False, indent: int = 1):
        nonlocal row
        cell_label = ws.cell(row=row, column=1, value=("  " * indent) + label)
        cell_label.font = total_font if bold else label_font
        col = 2 if sub else 3
        val = ws.cell(row=row, column=col, value=amount)
        val.number_format = _SGD_FMT
        val.font = total_font if bold else label_font
        row += 1

    def write_subtotal(label: str, amount, *, double: bool = False, indent: int = 0):
        nonlocal row
        c = ws.cell(row=row, column=1, value=("  " * indent) + label)
        c.font = total_font
        v = ws.cell(row=row, column=3, value=amount)
        v.number_format = _SGD_FMT
        v.font = total_font
        v.border = double_btm if double else top_thin
        ws.cell(row=row, column=2).border = top_thin if not double else double_btm
        row += 1

    def write_net(label: str, amount):
        nonlocal row
        c = ws.cell(row=row, column=1, value=label)
        c.font = net_font
        v = ws.cell(row=row, column=3, value=amount)
        v.number_format = _SGD_FMT
        v.font = net_font
        v.border = top_medium
        row += 1

    def blank():
        nonlocal row
        row += 1

    # REVENUE
    write_section_header("Revenue")
    revenue = float(payload.get("revenue") or 0)
    revenue_mode = payload.get("revenue_mode") or "recognised"
    rev_label = "Service revenue (bookings)" if revenue_mode == "bookings" \
                else "Service revenue (recognised)"
    write_line(rev_label, revenue, sub=False)
    write_subtotal("Total revenue", revenue)
    blank()

    # OPERATING EXPENSES
    write_section_header("Operating expenses")

    payroll = payload.get("payroll") or {}
    base_salaries = payroll.get("base_salaries") or []
    base_total = sum(float(p.get("amount") or 0) for p in base_salaries)
    commission = float(payroll.get("commission") or 0)
    cpf        = float(payroll.get("employer_cpf") or 0)

    # Payroll subgroup
    write_section_header("  Staff costs")
    for p in base_salaries:
        write_line(f"Salary — {p.get('name', '?')}", float(p.get('amount') or 0), sub=True, indent=2)
    if commission:
        write_line("Commission", commission, sub=True, indent=2)
    if cpf:
        write_line("Employer CPF contributions", cpf, sub=True, indent=2)
    staff_total = base_total + commission + cpf
    write_subtotal("Total staff costs", staff_total, indent=1)
    blank()

    # Opex subgroup
    opex_items = payload.get("opex") or []
    pmt_fee = float(payload.get("payment_processing_fee") or 0)
    write_section_header("  Other operating expenses")
    for item in opex_items:
        write_line(item.get("name", "?"), float(item.get("amount") or 0), sub=True, indent=2)
    if pmt_fee:
        write_line("Payment processing fees (Plato Terminal)", pmt_fee, sub=True, indent=2)
    other_opex_total = sum(float(i.get("amount") or 0) for i in opex_items) + pmt_fee
    write_subtotal("Total other operating expenses", other_opex_total, indent=1)
    blank()

    total_opex = staff_total + other_opex_total
    write_subtotal("Total operating expenses", total_opex)
    blank()

    # OPERATING PROFIT (EBITDA in cash view)
    ebitda = revenue - total_opex
    ebitda_label = "Operating profit / (loss) — EBITDA" if view == "cash" else "Operating profit / (loss) before amortisation"
    write_net(ebitda_label, ebitda)
    blank()

    # AMORTISATION
    amort = float(payload.get("amortisation") or 0) if view == "full" else 0
    if view == "full":
        write_section_header("Amortisation")
        capex = payload.get("capex") or {}
        if capex:
            capex_total = float(capex.get("total") or 0)
            months      = int(capex.get("months") or 0)
            write_line(
                f"Capex amortisation ({capex_total:,.0f} over {months} months)",
                amort, sub=True, indent=2,
            )
        else:
            write_line("Capex amortisation", amort, sub=True, indent=2)
        write_subtotal("Total amortisation", amort)
        blank()

    # NET PROFIT BEFORE TAX
    net_before_tax = ebitda - amort
    write_net("Net profit / (loss) before tax", net_before_tax)
    row += 1

    # Footnote
    if revenue_mode == "bookings":
        revenue_note = (
            "Revenue is reported on a cash/booking basis — invoice totals at the "
            "time of sale, regardless of when services are rendered."
        )
    else:
        revenue_note = (
            "Prepared on an accrual basis. Revenue recognised when services "
            "are rendered (package burns) or sold (single-use)."
        )
    ws.cell(row=row, column=1, value=(
        f"Notes:  {revenue_note} Singapore Dollar ($SGD) throughout. "
        "Employer CPF computed at the statutory rate on Ordinary Wages "
        "(capped at the OW ceiling) plus Additional Wages (commission)."
    )).font = sub_font
    ws.row_dimensions[row].height = 30
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
    ws.cell(row=row, column=1).alignment = Alignment(wrap_text=True, vertical="top")

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _creds_match(user: str, password: str, want_user: str, want_pass: str) -> bool:
    """Constant-time match against one configured credential pair.

    Returns False if the target pair isn't configured, so an unset secret can
    never be satisfied by empty input.
    """
    if not want_user or not want_pass:
        return False
    return (hmac.compare_digest(user, want_user)
            and hmac.compare_digest(password, want_pass))


def resolve_role(user: str, password: str) -> str | None:
    """Map a basic-auth credential pair to a role, or None if it matches neither.

    'founder' -> full access (financial dashboard + admin). 'staff' -> admin
    section only. Both pairs are checked so the timing of a staff login doesn't
    reveal whether the founder credential exists.
    """
    is_founder = _creds_match(user, password, AUTH_USER, AUTH_PASS)
    is_staff   = _creds_match(user, password, STAFF_USER, STAFF_PASS)
    if is_founder:
        return "founder"
    if is_staff:
        return "staff"
    return None


def require_roles(*roles: str):
    """Gate a route to the given roles. A credential for a role NOT in `roles`
    gets a 401 — this is what keeps a staff login out of the founder-only
    financial routes entirely (it never even reaches the handler).
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            auth = request.authorization
            role = resolve_role(auth.username or "", auth.password or "") if auth else None
            if role is None or role not in roles:
                return Response(
                    "Authentication required.",
                    401,
                    {"WWW-Authenticate": 'Basic realm="Goji Dashboard"'},
                )
            g.role = role
            g.user = (auth.username or "") if auth else ""
            return f(*args, **kwargs)
        return wrapper
    return decorator


@app.route("/")
@require_roles("founder")
def index() -> Response:
    return Response(get_shell_html(), mimetype="text/html")


@app.route("/api/data")
@require_roles("founder")
def api_data() -> Response:
    return Response(json.dumps(get_payload()), mimetype="application/json")


@app.route("/api/pl_window")
@require_roles("founder")
def api_pl_window() -> Response:
    """Recompute the P&L revenue + payment fees for an arbitrary date window.

    Used by the P&L tab's date selector ("Last 30D" / "Pay cycle" / "Custom").
    """
    start = _parse_iso_date(request.args.get("start"))
    end   = _parse_iso_date(request.args.get("end"))
    if not start or not end or start > end:
        return Response('{"error": "invalid start/end"}', status=400,
                        mimetype="application/json")
    log.info("P&L window query %s -> %s", start, end)
    return Response(json.dumps(fetch_pl_window(start, end)),
                    mimetype="application/json")


@app.route("/api/pl.xlsx", methods=["POST"])
@require_roles("founder")
def api_pl_xlsx() -> Response:
    """Generate a Singapore-style P&L statement xlsx from the client's snapshot.

    POST body: JSON describing the period, revenue, payroll lines, opex lines,
    and amortisation — exactly the figures the user sees on screen.
    """
    payload = request.get_json(silent=True) or {}
    blob = _xlsx_pl_statement(payload)
    period = payload.get("period") or {}
    end = period.get("end") or date.today().isoformat()
    filename = f"goji-pl-{end}.xlsx"
    return Response(
        blob,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/refresh", methods=["POST"])
@require_roles("founder")
def refresh() -> Response:
    with _cache_lock:
        _cache.pop("payload", None)
        _cache.pop("retention", None)
    if DEV_MODE and CACHE_DIR.exists():
        for f in CACHE_DIR.glob("*.json"):
            f.unlink()
    return Response('{"ok": true}', mimetype="application/json")


@app.route("/admin")
@require_roles("founder", "staff")
def admin_index() -> Response:
    """Staff admin dashboard shell. Open to staff and founders; no financials."""
    return Response(get_admin_shell_html(), mimetype="text/html")


@app.route("/api/admin/retention")
@require_roles("founder", "staff")
def api_admin_retention() -> Response:
    """Patient retention worklist: tier summary + per-patient call list."""
    return Response(json.dumps(get_retention(), default=str),
                    mimetype="application/json")


@app.route("/api/admin/followup", methods=["POST"])
@require_roles("founder", "staff")
def api_admin_followup() -> Response:
    """Record a follow-up action (contacted / snoozed / dismissed / active).

    Body: {patient_id, status, note?, snooze_days?}. Appends one event row;
    the worklist reflects it on the next reload.
    """
    body   = request.get_json(silent=True) or {}
    pid    = (body.get("patient_id") or "").strip()
    status = (body.get("status") or "").strip()
    if not pid or status not in VALID_FOLLOWUP_STATUSES:
        return Response('{"error": "patient_id and a valid status are required"}',
                        status=400, mimetype="application/json")
    snooze_days = body.get("snooze_days")
    if snooze_days is not None and not isinstance(snooze_days, int):
        snooze_days = None
    try:
        record_followup(pid, status, note=body.get("note"),
                        snooze_days=snooze_days, updated_by=getattr(g, "user", None))
    except Exception as e:
        log.exception("follow-up write failed: %s", e)
        return Response('{"error": "write failed"}', status=500,
                        mimetype="application/json")
    return Response('{"ok": true}', mimetype="application/json")


@app.route("/healthcheck")
def healthcheck() -> Response:
    # NB: not /healthz — Cloud Run's edge load balancer reserves /healthz for
    # its own internal probes and returns a Google-branded 404 before the
    # request reaches the container. /healthcheck is the public uptime ping.
    return Response("ok", mimetype="text/plain")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=DEV_MODE)
