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
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

import requests
from flask import Flask, Response, request
from google.cloud import bigquery
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

PROJECT     = os.environ.get("GCP_PROJECT", "goji-bi")
CACHE_TTL   = int(os.environ.get("CACHE_TTL_SECONDS", "300"))
AUTH_USER   = os.environ.get("DASHBOARD_USER", "")
AUTH_PASS   = os.environ.get("DASHBOARD_PASS", "")

HERE     = Path(__file__).resolve().parent
TEMPLATE = HERE / "template.html"

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


def _bq() -> bigquery.Client:
    global _bq_client
    if _bq_client is None:
        _bq_client = bigquery.Client(project=PROJECT)
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


PLATO_BASE = "https://clinic.platomedical.com/api"
PLATO_DB   = os.environ.get("PLATO_DB", "gojihealth")
MISMATCH_WINDOW_DAYS = int(os.environ.get("MISMATCH_WINDOW_DAYS", "30"))


def fetch_invoice_doctor_mismatches() -> dict:
    """Alert-only check: list non-void invoices whose `doctor` disagrees
    with the same-day appointment-calendar doctor for the same patient.

    Cleared automatically — when an invoice is corrected, the next dashboard
    refresh (after CACHE_TTL) re-queries Plato and the resolved invoice drops
    off the list.

    Returns:
        {
          "available": bool,        # False if PLATO_API_KEY missing
          "window_days": int,
          "mismatches": [...],      # see fields below
          "no_appt_count": int,     # invoices we couldn't cross-ref
          "checked_at": iso ts,
          "error": str | None,
        }
    """
    api_key = os.environ.get("PLATO_API_KEY")
    result = {
        "available": bool(api_key),
        "window_days": MISMATCH_WINDOW_DAYS,
        "mismatches": [],
        "no_appt_count": 0,
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "error": None,
    }
    if not api_key:
        return result

    today = date.today()
    start = today - timedelta(days=MISMATCH_WINDOW_DAYS)
    end   = today
    log.info("  invoice-doctor mismatch check (%s -> %s)", start, end)

    try:
        s = requests.Session()
        s.headers.update({"accept": "application/json", "Authorization": f"Bearer {api_key}"})

        # 1. calendar color -> doctor map
        r = s.get(f"{PLATO_BASE}/{PLATO_DB}/appointment/calendars", timeout=20)
        r.raise_for_status()
        color_to_doctor: dict[str, str] = {}
        for cal in r.json():
            c, d = cal.get("color"), cal.get("doctor")
            if c and d:
                color_to_doctor[c] = d

        # 2. all appointments in window, paginated
        appts: list[dict] = []
        page = 1
        while True:
            r = s.get(
                f"{PLATO_BASE}/{PLATO_DB}/appointment",
                params={"start_date": start.isoformat(), "end_date": end.isoformat(), "current_page": page},
                timeout=30,
            )
            r.raise_for_status()
            body = r.json()
            rows = body if isinstance(body, list) else (body.get("appointments") or body.get("data") or [])
            if not rows:
                break
            appts.extend(rows)
            if len(rows) < 20:
                break
            page += 1
            time.sleep(1.5)

        # Index appointments by (patient_id, date)
        appt_idx: dict[tuple[str, str], set[str]] = {}
        for a in appts:
            pid = a.get("patient_id")
            d_str = (a.get("starttime") or "")[:10]
            if not pid or not d_str:
                continue
            doc = color_to_doctor.get(a.get("color") or "")
            if doc:
                appt_idx.setdefault((pid, d_str), set()).add(doc)

    except requests.RequestException as e:
        log.exception("Plato cross-ref failed: %s", e)
        result["error"] = f"Plato API error: {e}"
        return result

    # 3. latest invoice state for every invoice in window
    sql = f"""
WITH latest AS (
  SELECT
    invoice_id,
    invoice_date,
    JSON_VALUE(payload, '$.patient_id')     AS patient_id,
    JSON_VALUE(payload, '$.doctor')         AS doctor,
    JSON_VALUE(payload, '$.created_by')     AS created_by,
    JSON_VALUE(payload, '$.last_edited_by') AS last_edited_by,
    JSON_VALUE(payload, '$.invoice_prefix') AS invoice_prefix,
    SAFE_CAST(JSON_VALUE(payload, '$.invoice') AS INT64) AS invoice_no,
    SAFE_CAST(JSON_VALUE(payload, '$.void')      AS INT64) = 1 AS is_void,
    SAFE_CAST(JSON_VALUE(payload, '$.finalized') AS INT64) = 1 AS is_finalized,
    SAFE_CAST(JSON_VALUE(payload, '$.total')     AS NUMERIC) AS total
  FROM `{PROJECT}.raw_plato.invoices_raw`
  WHERE invoice_date BETWEEN '{start}' AND '{end}'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY invoice_id ORDER BY _loaded_at DESC) = 1
)
SELECT l.*, p.initial_lastname
FROM latest l
LEFT JOIN `{PROJECT}.marts.dim_patient` p USING (patient_id)
WHERE NOT COALESCE(l.is_void, FALSE)
ORDER BY l.invoice_date DESC, l.invoice_no DESC
"""
    invoices = _query(sql)

    mismatches: list[dict] = []
    no_appt = 0
    for inv in invoices:
        pid = inv.get("patient_id")
        inv_date = inv["invoice_date"].isoformat() if inv.get("invoice_date") else None
        if not pid or not inv_date:
            continue
        appt_doctors = appt_idx.get((pid, inv_date))
        if not appt_doctors:
            no_appt += 1
            continue
        doctor = inv.get("doctor")
        if doctor in appt_doctors:
            continue
        # Mismatch
        mismatches.append({
            "invoice_id":   inv["invoice_id"],
            "invoice_no":   f"{inv.get('invoice_prefix') or ''}{inv.get('invoice_no') or ''}".strip() or inv["invoice_id"][:8],
            "date":         inv_date,
            "patient":      inv.get("initial_lastname") or pid,
            "invoice_doctor":     doctor,
            "invoice_doctor_name": PROVIDERS.get(doctor or "", doctor or "(unset)"),
            "appt_doctors":       sorted(appt_doctors),
            "appt_doctor_names":  [PROVIDERS.get(d, d) for d in sorted(appt_doctors)],
            "created_by":   inv.get("created_by"),
            "last_edited_by": inv.get("last_edited_by"),
            "total":        _to_float(inv.get("total")),
        })

    result["mismatches"]    = mismatches
    result["no_appt_count"] = no_appt
    log.info("  mismatches found: %d (window=%dd, %d invoices had no same-day appt)",
             len(mismatches), MISMATCH_WINDOW_DAYS, no_appt)
    return result


def build_payload() -> dict:
    log.info("Building dashboard payload from BigQuery")
    deferred = fetch_deferred()
    cohorts  = fetch_cohorts()

    ranges: dict[str, dict] = {}
    for key, label, start, end in preset_ranges():
        log.info("  range %s (%s -> %s)", key, start, end)
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

    # P&L tab uses a fixed 30-day window for payment processing fees
    today = date.today()
    pmt_start = today - timedelta(days=30)
    log.info("  payment methods (%s -> %s)", pmt_start, today)
    payment_by_method = fetch_payment_methods(pmt_start, today)

    # Commission calculator needs the per-session ledger for the current pay
    # cycle plus a generous trailing window so custom-range reports still work.
    # 120 days covers ~4 pay cycles (26th -> 25th).
    appt_start = today - timedelta(days=120)
    log.info("  appointments (%s -> %s)", appt_start, today)
    appointments = fetch_appointments(appt_start, today)

    # Invoice attribution alert: cross-ref invoice.doctor against the same-day
    # appointment-calendar doctor. Hits Plato API live (cached for CACHE_TTL).
    doctor_mismatches = fetch_invoice_doctor_mismatches()

    return {
        "generated_at":      datetime.now().astimezone().isoformat(timespec="seconds"),
        "default_range":     "30d",
        "deferred":          deferred,
        "cohorts":           cohorts,
        "appointments":      appointments,
        "payment_by_method": payment_by_method,
        "ranges":            ranges,
        "doctor_mismatches": doctor_mismatches,
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

    payload = build_payload()

    with _cache_lock:
        _cache["payload"] = (now, payload)
    return payload


def get_shell_html() -> str:
    """Return the dashboard shell HTML. No BQ work — ships in milliseconds.

    Data placeholder is left as an empty object; the page fetches the real
    payload from `/api/data` after first paint.
    """
    return TEMPLATE.read_text().replace("__DATA_PLACEHOLDER__", "{}")


def fetch_pl_window(start: date, end: date) -> dict:
    """Recompute the P&L revenue + payment fee inputs for an arbitrary window.

    Reuses fetch_kpis / fetch_clinicians / fetch_payment_methods so the rules
    stay in lock-step with the main dashboard.
    """
    kpis              = fetch_kpis(start, end)
    clinicians        = fetch_clinicians(start, end)
    payment_by_method = fetch_payment_methods(start, end)
    return {
        "start":             start.isoformat(),
        "end":               end.isoformat(),
        "days":              (end - start).days + 1,
        "recognised":        kpis["recognised"],
        "bookings":          kpis["bookings"],
        "clinicians":        clinicians,
        "payment_by_method": payment_by_method,
    }


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
    write_line("Service revenue (recognised)", revenue, sub=False)
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
    ws.cell(row=row, column=1, value=(
        "Notes:  Prepared on an accrual basis. Revenue recognised when services "
        "are rendered (package burns) or sold (single-use). Singapore Dollar "
        "($SGD) throughout. Employer CPF computed at the statutory rate on "
        "Ordinary Wages (capped at the OW ceiling) plus Additional Wages "
        "(commission)."
    )).font = sub_font
    ws.row_dimensions[row].height = 30
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
    ws.cell(row=row, column=1).alignment = Alignment(wrap_text=True, vertical="top")

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def check_auth(user: str, password: str) -> bool:
    if not AUTH_USER or not AUTH_PASS:
        return False
    return (hmac.compare_digest(user, AUTH_USER)
            and hmac.compare_digest(password, AUTH_PASS))


def requires_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username or "", auth.password or ""):
            return Response(
                "Authentication required.",
                401,
                {"WWW-Authenticate": 'Basic realm="Goji Dashboard"'},
            )
        return f(*args, **kwargs)
    return wrapper


@app.route("/")
@requires_auth
def index() -> Response:
    return Response(get_shell_html(), mimetype="text/html")


@app.route("/api/data")
@requires_auth
def api_data() -> Response:
    return Response(json.dumps(get_payload()), mimetype="application/json")


@app.route("/api/pl_window")
@requires_auth
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
@requires_auth
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
@requires_auth
def refresh() -> Response:
    with _cache_lock:
        _cache.pop("payload", None)
    return Response('{"ok": true}', mimetype="application/json")


@app.route("/healthz")
def healthz() -> Response:
    return Response("ok", mimetype="text/plain")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
