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
import json
import logging
import os
import re
import threading
import time
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, Response, request
from google.cloud import bigquery

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

_cache: dict[str, tuple[float, str]] = {}
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


def fetch_appointments() -> list[dict]:
    """Forward-looking unconfirmed appointments.

    Placeholder until /appointment ingestion lands — the v3 commission tab
    relies on this list but BQ doesn't have appointment data yet.
    """
    return []


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

    return {
        "generated_at":      datetime.now().astimezone().isoformat(timespec="seconds"),
        "default_range":     "30d",
        "deferred":          deferred,
        "cohorts":           cohorts,
        "appointments":      fetch_appointments(),
        "payment_by_method": payment_by_method,
        "ranges":            ranges,
    }


def get_rendered_html() -> str:
    """Return the dashboard HTML, using cache if fresh."""
    now = time.time()
    with _cache_lock:
        entry = _cache.get("html")
        if entry and now - entry[0] < CACHE_TTL:
            return entry[1]

    template = TEMPLATE.read_text()
    payload  = build_payload()
    html     = template.replace("__DATA_PLACEHOLDER__", json.dumps(payload))

    with _cache_lock:
        _cache["html"] = (now, html)
    return html


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
    return Response(get_rendered_html(), mimetype="text/html")


@app.route("/refresh", methods=["POST"])
@requires_auth
def refresh() -> Response:
    with _cache_lock:
        _cache.pop("html", None)
    return Response('{"ok": true}', mimetype="application/json")


@app.route("/healthz")
def healthz() -> Response:
    return Response("ok", mimetype="text/plain")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
