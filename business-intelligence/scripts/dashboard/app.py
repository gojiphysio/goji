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
from zoneinfo import ZoneInfo
from functools import wraps
from pathlib import Path

from urllib.parse import quote

from flask import Flask, Response, g, redirect, request
from google.auth import default as google_auth_default
from google.auth.transport.requests import AuthorizedSession
from google.cloud import bigquery
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from requests.adapters import HTTPAdapter

PROJECT     = os.environ.get("GCP_PROJECT", "goji-bi")
CACHE_TTL   = int(os.environ.get("CACHE_TTL_SECONDS", "300"))
# GA4 BigQuery export (free native daily export). GA4_DATASET is the
# `analytics_<propertyId>` dataset; unset until the export is linked, in which
# case the Website-sessions card just stays empty. See DEPLOY.md.
GA4_PROJECT = os.environ.get("GA4_PROJECT", PROJECT)
GA4_DATASET = os.environ.get("GA4_DATASET", "")
# Founder credential — sees everything, including the financial dashboard.
AUTH_USER   = os.environ.get("DASHBOARD_USER", "")
AUTH_PASS   = os.environ.get("DASHBOARD_PASS", "")

# Staff credentials — multiple pairs supported so every team member (front
# desk, clinicians) can have their own login. The legacy single-pair env vars
# STAFF_USER / STAFF_PASS continue to work; additional staff accounts are
# added via STAFF_<N>_USER / STAFF_<N>_PASS for N = 1, 2, 3, ...
# All of these map to the 'staff' role and can only reach the Front Desk routes.
def _load_staff_creds() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    # Legacy single pair
    u, p = os.environ.get("STAFF_USER", ""), os.environ.get("STAFF_PASS", "")
    if u and p:
        pairs.append((u, p))
    # Numbered extras: STAFF_1_USER/PASS, STAFF_2_USER/PASS, ...
    n = 1
    while True:
        u = os.environ.get(f"STAFF_{n}_USER", "")
        p = os.environ.get(f"STAFF_{n}_PASS", "")
        if not u and not p:
            break
        if u and p:
            pairs.append((u, p))
        n += 1
    return pairs

STAFF_CREDS: list[tuple[str, str]] = _load_staff_creds()

# APP_MODE controls which subdomain this instance serves.
#   "dashboard"  — financial dashboard (default); founder-only.
#   "frontdesk"  — patient ops portal; staff + founders.
#   "links"      — public click-to-WhatsApp redirect surface only
#                  (go.gojiphysio.com/<slug>); no dashboard/auth routes exist.
APP_MODE = os.environ.get("APP_MODE", "dashboard").lower()
# Local-dev mode: enables Flask reloader and persists BQ results to disk so
# process restarts don't trigger a fresh BQ fetch. Off in prod (Cloud Run).
DEV_MODE    = os.environ.get("DASHBOARD_DEV") == "1"

# Patient name + phone for the staff worklist come from marts.dim_patient_contact
# (written by the plato-patients-ingest job). The dashboard no longer calls Plato.

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

# --- Click-to-WhatsApp / booking tracking ---------------------------------
# WhatsApp is the primary CTA (customers message before booking), but socials
# (gojiphysio.com/links, which replaced bio.site in Oct 2026) also link straight to our /book form, so we track both. Every
# outbound CTA routes through the public GET /r/<slug> route (and the public
# go.gojiphysio.com/<slug>), which logs the click and 302-redirects to the slug's
# destination. WhatsApp slugs carry a channel-specific prefilled message.
# Adding an entry point = add a slug here.
# Digits only — wa.me wants no '+', spaces, or dashes, so we strip them defensively
# (the repo variable might be entered as "+65 8377 0401").
WHATSAPP_NUMBER = re.sub(r"\D", "", os.environ.get("WHATSAPP_NUMBER", ""))
# Our own website booking form — the only booking CTA now. 'book' ('*-book')
# slugs redirect here so a click lands on /book and is still logged +
# attributable. Legacy '*-plato' slugs (the old Plato online-booking page, which
# we no longer offer) alias to the same URL below — old published QR codes,
# GBP listings, etc. still work, they just land on the flow we actually track.
SITE_BOOKING_URL = os.environ.get("SITE_BOOKING_URL", "https://www.gojiphysio.com/book")
# Where a click goes when its target isn't configured yet or the slug is unknown.
WHATSAPP_FALLBACK_URL = os.environ.get("WHATSAPP_FALLBACK_URL",
                                       "https://www.gojiphysio.com")
# 9.9 promo (Pilates / S&C packages) — one prefilled template, reused by every
# channel's campaign slug below. WhatsApp has no form, so the message is a
# fill-in block that hands the front desk name/mobile/email + which package in
# the very first message, and still reads sensibly if the customer sends it
# untouched. PDPA: details volunteered here are an inbound enquiry, NOT consent
# to market — record consent in Front Desk → Contactability before any outbound
# send (see repo AGENTS.md).
PROMO_99_TEXT = (
    "Hi Goji! I'd like to claim the 9.9 offer on your Pilates / S&C packages.\n"
    "\n"
    "Package: Interchangeable Pilates and S&C\n"
    "Name:\n"
    "Mobile:\n"
    "Email:"
)
# slug -> {kind, label, text?}. kind="whatsapp" → wa.me deep link with `text`;
# kind="book" → our website /book form (also covers legacy '*-plato' slugs —
# see LINK_SLUGS below). The founder signs off on the WhatsApp wording.
LINK_SLUGS: dict[str, dict] = {
    # Slug = "<channel>-<destination>" — both explicit, no assumed default, so a
    # channel whose primary CTA isn't WhatsApp reads just as clearly.
    #   destination: "wa" = WhatsApp deep link, "book"/"plato" = website /book
    #                form ("plato" is the retired Plato-booking page name, kept
    #                only so old published links redirect somewhere real).
    # --- WhatsApp ---
    "web-wa": {"kind": "whatsapp", "label": "Web",      "text": "Hi Goji! I have a question about physio (via your website)."},
    "bio-wa": {"kind": "whatsapp", "label": "Link in bio", "text": "Hi Goji! I found you via your Instagram/socials and have a question about physio."},
    "gbp-wa": {"kind": "whatsapp", "label": "Google",   "text": "Hi Goji! I found you on Google and have a question about physio."},
    "ads-wa": {"kind": "whatsapp", "label": "Ads",      "text": "Hi Goji! I saw your ad and have a question about physio."},
    "qr-wa":  {"kind": "whatsapp", "label": "QR",       "text": "Hi Goji! I scanned your QR code and have a question about physio."},
    "ig-wa":  {"kind": "whatsapp", "label": "IG",       "text": "Hi Goji! I found you on Instagram and have a question about physio."},
    # Outbound: the CTA in the automated 48-hour appointment reminder email
    # (scripts/reminders). Its own slug so reminder-driven WhatsApp traffic —
    # mostly reschedules and cancellations — is separable from inbound enquiry
    # channels in the link-click stats.
    "reminder-wa": {"kind": "whatsapp", "label": "Reminder", "text": "Hi Goji! I have a question about my upcoming appointment."},
    "wa":     {"kind": "whatsapp", "label": "Social",   "text": "Hi Goji! I have a question about physio."},  # generic fallback
    # --- Website /book form (current booking CTA) ---
    "web-book": {"kind": "book", "label": "Web"},
    "bio-book": {"kind": "book", "label": "Link in bio"},
    "gbp-book": {"kind": "book", "label": "Google"},
    # Button on GBP posts auto-created from Instagram (ingestion/gbp_post_sync),
    # kept apart from the profile's own Book button so posts are measurable.
    "gbp-post-book": {"kind": "book", "label": "Google post"},
    "ads-book": {"kind": "book", "label": "Ads"},
    "qr-book":  {"kind": "book", "label": "QR"},
    "book":     {"kind": "book", "label": "Social"},  # generic fallback
    # --- Legacy Plato-booking slugs (retired; alias to the native /book form
    #     below so old published links never dead-end) ---
    "web-plato": {"kind": "book", "label": "Web"},
    "bio-plato": {"kind": "book", "label": "Link in bio"},
    "gbp-plato": {"kind": "book", "label": "Google"},
    "ads-plato": {"kind": "book", "label": "Ads"},
    "qr-plato":  {"kind": "book", "label": "QR"},
    "plato":     {"kind": "book", "label": "Social"},  # generic fallback
    # --- Campaign: 9.9 Pilates / S&C packages (retire when the offer ends) ---
    # Campaign slugs keep the channel + destination explicit and slot the
    # campaign in between: "<channel>-99-wa". Kept in their own block so the
    # whole campaign can be deleted in one edit without touching the evergreen
    # slugs above (published links then fall back to the site, never dead-end).
    "web-99-wa": {"kind": "whatsapp", "label": "Web",      "text": PROMO_99_TEXT},
    "bio-99-wa": {"kind": "whatsapp", "label": "Link in bio", "text": PROMO_99_TEXT},
    "gbp-99-wa": {"kind": "whatsapp", "label": "Google",   "text": PROMO_99_TEXT},
    "ads-99-wa": {"kind": "whatsapp", "label": "Ads",      "text": PROMO_99_TEXT},
    "qr-99-wa":  {"kind": "whatsapp", "label": "QR",       "text": PROMO_99_TEXT},
    "ig-99-wa":  {"kind": "whatsapp", "label": "IG",       "text": PROMO_99_TEXT},
    "99-wa":     {"kind": "whatsapp", "label": "Social",   "text": PROMO_99_TEXT},  # generic fallback
    # --- Shop: "<channel>-pay-<item>" → that item's Stripe Payment Link ---
    **{f"web-pay-{item}": {"kind": "pay", "label": "Web", "item": item} for item in (
        "pp-1to1-5", "pp-1to1-10", "pp-2to1-5", "pp-2to1-10",
        "cpsc-5", "cpsc-10", "gift-voucher",
        "socks-girl", "socks-gang",
    )},
}
# Shop item → Stripe Payment Link (scripts/shop/stripe_catalog.py writes these to
# shop_links.<mode>.json; paste the live ones here). An item with no URL yet
# falls back to the /shop page, so a published shop link never dead-ends.
SHOP_PAY_URLS: dict[str, str] = {
    "pp-1to1-5": "https://buy.stripe.com/00w00idHW32u1564CuejK00",
    "pp-1to1-10": "https://buy.stripe.com/8x28wO33icD44hi0meejK01",
    "pp-2to1-5": "https://buy.stripe.com/dRm00i6fu8mOaFG2umejK02",
    "pp-2to1-10": "https://buy.stripe.com/00waEW6fu0Um7tud90ejK03",
    "gift-voucher": "https://buy.stripe.com/14A9AS0Va0Um1569WOejK04",
}
SHOP_FALLBACK_URL = "https://www.gojiphysio.com/shop/"
# slug -> kind, for splitting the click metric (WhatsApp vs booking).
LINK_SLUG_KIND = {s: c["kind"] for s, c in LINK_SLUGS.items()}

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
    today = datetime.now(ZoneInfo("Asia/Singapore")).date()
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
   WHERE delivery_date BETWEEN '{start}' AND '{end}')                     AS visits,
  (SELECT COUNT(*)
   FROM (
     SELECT patient_id, MIN(delivery_date) AS first_visit
     FROM `{PROJECT}.marts.fct_service_delivered`
     WHERE patient_id IS NOT NULL
     GROUP BY patient_id
   )
   WHERE first_visit BETWEEN '{start}' AND '{end}')                       AS new_patients
"""
    row = _query(sql)[0]
    return {
        "bookings":        _to_float(row["bookings"]),
        "recognised":      _to_float(row["recognised"]),
        "active_patients": _to_int(row["active_patients"]),
        "visits":          _to_int(row["visits"]),
        "new_patients":    _to_int(row["new_patients"]),
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


def _fetch_new_patients_series(start: date, end: date) -> list[dict]:
    """New-patients series (first-visit cohort size) bucketed at the range's
    granularity — the north-star companion to the active-patients series.

    Can't use _fetch_series: "new" is per-patient (MIN(delivery_date)), not a
    row count by date, so it needs a first-visit CTE. Buckets/format match
    _granularity_for so the two north-star series share an x-axis.
    """
    gran, date_fmt = _granularity_for(start, end)
    sql = f"""
WITH fv AS (
  SELECT patient_id, MIN(delivery_date) AS first_visit
  FROM `{PROJECT}.marts.fct_service_delivered`
  WHERE patient_id IS NOT NULL
  GROUP BY patient_id
)
SELECT
  FORMAT_DATE('{date_fmt}', DATE_TRUNC(first_visit, {gran})) AS label,
  DATE_TRUNC(first_visit, {gran})                            AS bucket,
  COUNT(*)                                                   AS value
FROM fv
WHERE first_visit BETWEEN '{start}' AND '{end}'
GROUP BY bucket, label
ORDER BY bucket
"""
    return [{"label": r["label"], "value": _to_float(r["value"])} for r in _query(sql)]


def fetch_trends(start: date, end: date) -> dict:
    # Five independent BQ queries — fan out so the slowest single series is
    # the wall-time floor instead of their sum.
    gran, _ = _granularity_for(start, end)
    with ThreadPoolExecutor(max_workers=5, thread_name_prefix="trends") as ex:
        f_bookings        = ex.submit(_fetch_series, "marts.fct_invoice_line",      "invoice_date",  "SUM(booking_amount)",        start, end)
        f_recognised      = ex.submit(_fetch_series, "marts.fct_service_delivered", "delivery_date", "SUM(recognised_revenue)",    start, end)
        f_visits          = ex.submit(_fetch_series, "marts.fct_service_delivered", "delivery_date", "COUNT(*)",                   start, end)
        f_active_patients = ex.submit(_fetch_series, "marts.fct_service_delivered", "delivery_date", "COUNT(DISTINCT patient_id)", start, end, "AND patient_id IS NOT NULL")
        f_new_patients    = ex.submit(_fetch_new_patients_series, start, end)
        return {
            "granularity":     gran,
            "bookings":        f_bookings.result(),
            "recognised":      f_recognised.result(),
            "visits":          f_visits.result(),
            "active_patients": f_active_patients.result(),
            "new_patients":    f_new_patients.result(),
        }


def fetch_weekly_visits(start: date, end: date) -> list[dict]:
    sql = f"""
SELECT
  FORMAT_DATE('%-d %b', DATE_TRUNC(delivery_date, WEEK(MONDAY))) AS label,
  DATE_TRUNC(delivery_date, WEEK(MONDAY))                        AS bucket,
  COUNT(*)                                                        AS value
FROM `{PROJECT}.marts.fct_service_delivered`
WHERE delivery_date BETWEEN '{start}' AND '{end}'
GROUP BY bucket, label
ORDER BY bucket
"""
    try:
        return [{"label": r["label"], "value": _to_float(r["value"])} for r in _query(sql)]
    except Exception as exc:
        log.warning("fetch_weekly_visits failed: %s", exc)
        return []


def _business_days(start: date, end: date) -> int:
    """Count Mon–Sat days (inclusive) between start and end."""
    count = 0
    d = start
    while d <= end:
        if d.weekday() != 6:  # skip Sunday
            count += 1
        d += timedelta(days=1)
    return count


def _fiscal_period(today: date) -> tuple[date, date]:
    """Return (start, end) of the calendar month containing today (1st → last day).

    The month end is derived as first-of-next-month minus one day, so 28/29/30/31
    day months (and leap years) all fall out correctly.
    """
    fs = today.replace(day=1)
    next_month_start = date(today.year + 1, 1, 1) if today.month == 12 \
                       else date(today.year, today.month + 1, 1)
    fe = next_month_start - timedelta(days=1)
    return fs, fe


def _prior_fiscal_start(fs: date) -> date:
    """Return the 1st of the calendar month before fs."""
    return date(fs.year - 1, 12, 1) if fs.month == 1 \
           else date(fs.year, fs.month - 1, 1)


def fetch_monthly_projection(today: date) -> dict:
    try:
        period_start, period_end = _fiscal_period(today)

        # 3 prior complete calendar months
        p1_start = _prior_fiscal_start(period_start)
        p1_end   = period_start - timedelta(days=1)
        p2_start = _prior_fiscal_start(p1_start)
        p2_end   = p1_start - timedelta(days=1)
        p3_start = _prior_fiscal_start(p2_start)
        p3_end   = p2_start - timedelta(days=1)

        # Labels named by the month itself (e.g. "May 26" = 1–31 May 2026)
        lbl = lambda d: d.strftime('%b %y')
        p1_lbl, p2_lbl, p3_lbl = lbl(p1_end), lbl(p2_end), lbl(p3_end)

        kpi_sql = f"""
SELECT
  (SELECT COALESCE(SUM(recognised_revenue), 0)
   FROM `{PROJECT}.marts.fct_service_delivered`
   WHERE delivery_date BETWEEN '{period_start}' AND '{today}') AS actual_mtd,
  (SELECT COALESCE(SUM(recognised_revenue), 0)
   FROM `{PROJECT}.marts.fct_service_delivered`
   WHERE delivery_date BETWEEN '{p1_start}' AND '{p1_end}')   AS prev_month_actual,
  (SELECT COALESCE(SUM(booking_amount), 0)
   FROM `{PROJECT}.marts.fct_invoice_line`
   WHERE invoice_date BETWEEN '{period_start}' AND '{today}') AS bookings_mtd,
  (SELECT COALESCE(SUM(booking_amount), 0)
   FROM `{PROJECT}.marts.fct_invoice_line`
   WHERE invoice_date BETWEEN '{p1_start}' AND '{p1_end}')    AS prev_month_bookings
"""
        history_sql = f"""
SELECT
  CASE
    WHEN delivery_date BETWEEN '{p3_start}' AND '{p3_end}' THEN '{p3_lbl}'
    WHEN delivery_date BETWEEN '{p2_start}' AND '{p2_end}' THEN '{p2_lbl}'
    WHEN delivery_date BETWEEN '{p1_start}' AND '{p1_end}' THEN '{p1_lbl}'
  END AS label,
  COALESCE(SUM(recognised_revenue), 0) AS actual
FROM `{PROJECT}.marts.fct_service_delivered`
WHERE delivery_date BETWEEN '{p3_start}' AND '{p1_end}'
GROUP BY 1
"""
        bookings_history_sql = f"""
SELECT
  CASE
    WHEN invoice_date BETWEEN '{p3_start}' AND '{p3_end}' THEN '{p3_lbl}'
    WHEN invoice_date BETWEEN '{p2_start}' AND '{p2_end}' THEN '{p2_lbl}'
    WHEN invoice_date BETWEEN '{p1_start}' AND '{p1_end}' THEN '{p1_lbl}'
  END AS label,
  COALESCE(SUM(booking_amount), 0) AS bookings
FROM `{PROJECT}.marts.fct_invoice_line`
WHERE invoice_date BETWEEN '{p3_start}' AND '{p1_end}'
GROUP BY 1
"""
        with ThreadPoolExecutor(max_workers=3) as ex:
            f_kpi      = ex.submit(_query, kpi_sql)
            f_history  = ex.submit(_query, history_sql)
            f_bhistory = ex.submit(_query, bookings_history_sql)
            row      = f_kpi.result()[0]
            history  = f_history.result()
            bhistory = f_bhistory.result()

        # Month order is fixed (oldest -> newest) rather than derived from the
        # rows, so a month with no delivered sessions / no invoices still shows
        # as a zero bar instead of dropping out of the series.
        rec_by_label  = {r["label"]: _to_float(r["actual"])   for r in history}
        book_by_label = {r["label"]: _to_float(r["bookings"]) for r in bhistory}
        monthly_history = [
            {"label": lb,
             "actual":   rec_by_label.get(lb, 0.0),
             "bookings": book_by_label.get(lb, 0.0)}
            for lb in (p3_lbl, p2_lbl, p1_lbl)
        ]

        actual_mtd          = _to_float(row["actual_mtd"])
        prev_month_actual   = _to_float(row["prev_month_actual"])
        bookings_mtd        = _to_float(row["bookings_mtd"])
        prev_month_bookings = _to_float(row["prev_month_bookings"])
        days_elapsed        = _business_days(period_start, today)
        days_total          = _business_days(period_start, period_end)
        run_rate            = lambda v: (v / days_elapsed * days_total) if days_elapsed else 0.0
        projected_eom          = run_rate(actual_mtd)
        projected_bookings_eom = run_rate(bookings_mtd)

        return {
            "actual_mtd":             actual_mtd,
            "projected_eom":          projected_eom,
            "prev_month_actual":      prev_month_actual,
            "bookings_mtd":           bookings_mtd,
            "projected_bookings_eom": projected_bookings_eom,
            "prev_month_bookings":    prev_month_bookings,
            "days_elapsed":           days_elapsed,
            "days_total":             days_total,
            "month_label":            period_end.strftime("%b %Y"),
            "prev_month_label":       p1_end.strftime("%b %Y"),
            "monthly_history":        monthly_history,
        }
    except Exception as exc:
        log.warning("fetch_monthly_projection failed: %s", exc)
        return {
            "actual_mtd": None, "projected_eom": None,
            "prev_month_actual": None, "bookings_mtd": None,
            "projected_bookings_eom": None, "prev_month_bookings": None,
            "days_elapsed": None,
            "days_total": None, "month_label": None, "prev_month_label": None,
            "monthly_history": [],
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


def fetch_upcoming_sessions(today: date) -> dict:
    """Booked patient SESSIONS in the next 7 and 30 days (founder demand card).

    Counts distinct clinician time-slots, not appointment rows, so a group /
    2:1 class (two patients sharing one clinician + start + end) counts once —
    this is the calendar-occupancy number, matching how the clinic thinks about
    capacity. Mirrors marts.fct_new_patient_welcome's qualifier; keep the two in
    sync.

    A slot qualifies as a patient session when it isn't cancelled / void /
    no-show AND it looks like a real booking: a linked patient_id, OR inline
    contact (handphone/email — how a profile-less website/walk-in booking still
    carries the patient), OR a real treatment_type. That drops lunches, 1:1s,
    time blocks, shifts, travel and admin.

    GHOST GUARD: the plato_appointments ingestion is append-only with no
    deletion detection, so a deleted Plato appointment lingers in
    stg.appointments as its last-known version. Every run re-pulls the whole
    window, so a live appointment's _loaded_at advances while a deleted one goes
    stale; we count only forward slots reloaded in the most recent run
    (_loaded_at within 30 min of the newest load). The trailing "previous"
    windows are actual past sessions, so they don't need (and can't get, beyond
    the past ingest window) the freshness filter.
    """
    # Session-date windows. Forward windows include today (upcoming incl. today);
    # the trailing comparison windows stop yesterday so they never overlap.
    d7   = today + timedelta(days=7)
    d30  = today + timedelta(days=30)
    p7   = today - timedelta(days=7)
    p30  = today - timedelta(days=30)
    yday = today - timedelta(days=1)
    slot = "FORMAT('%s|%d|%d', COALESCE(calendar_color,''), UNIX_SECONDS(start_at), UNIX_SECONDS(end_at))"
    sql = f"""
WITH fresh AS (
  SELECT TIMESTAMP_SUB(MAX(_loaded_at), INTERVAL 30 MINUTE) AS min_loaded_at
  FROM `{PROJECT}.stg.appointments`
),
base AS (
  SELECT calendar_color, start_at, end_at, appt_date, _loaded_at
  FROM `{PROJECT}.stg.appointments`
  WHERE appt_date BETWEEN '{p30}' AND '{d30}'
    AND COALESCE(SAFE_CAST(JSON_VALUE(payload, '$.cancelled') AS INT64), 0) = 0
    AND COALESCE(SAFE_CAST(JSON_VALUE(payload, '$.void')      AS INT64), 0) = 0
    AND LOWER(COALESCE(JSON_VALUE(payload, '$.status'), '')) NOT IN
        ('cancelled', 'canceled', 'no_show', 'noshow', 'no-show')
    AND (
         (patient_id IS NOT NULL AND patient_id != '')
      OR COALESCE(JSON_VALUE(payload, '$.handphone'), '') != ''
      OR COALESCE(JSON_VALUE(payload, '$.email'), '')     != ''
      OR treatment_type NOT IN ('Untyped', 'Unknown')
    )
)
SELECT
  COUNT(DISTINCT IF(appt_date BETWEEN '{today}' AND '{d7}'
                    AND _loaded_at >= f.min_loaded_at, {slot}, NULL)) AS next_7,
  COUNT(DISTINCT IF(appt_date BETWEEN '{today}' AND '{d30}'
                    AND _loaded_at >= f.min_loaded_at, {slot}, NULL)) AS next_30,
  COUNT(DISTINCT IF(appt_date BETWEEN '{p7}'  AND '{yday}', {slot}, NULL)) AS prev_7,
  COUNT(DISTINCT IF(appt_date BETWEEN '{p30}' AND '{yday}', {slot}, NULL)) AS prev_30,
  -- Furthest forward day we hold *fresh* data for. The ingestion pulls only
  -- FUTURE_DAYS ahead, so if that's < 30 the "next 30 days" count is
  -- incomplete; the card uses this to avoid showing a misleading number until
  -- the window is widened (then it self-heals).
  DATE_DIFF(MAX(IF(appt_date >= '{today}' AND _loaded_at >= f.min_loaded_at,
                   appt_date, NULL)), '{today}', DAY) AS covered_days
FROM base, fresh f
"""
    try:
        r = _query(sql)[0]
        return {
            "next_7":       _to_int(r["next_7"]),
            "next_30":      _to_int(r["next_30"]),
            "prev_7":       _to_int(r["prev_7"]),
            "prev_30":      _to_int(r["prev_30"]),
            "covered_days": _to_int(r["covered_days"]),
        }
    except Exception as e:
        log.warning("fetch_upcoming_sessions failed: %s", e)
        return {"next_7": 0, "next_30": 0, "prev_7": 0, "prev_30": 0, "covered_days": 0}


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


def fetch_deferred(end: date) -> dict:
    """Outstanding deferred revenue liability as of `end`.

    = packages sold on or before `end`
    - sessions delivered (package burns) on or before `end`

    This is the balance-sheet liability at the close of the selected period,
    so switching the date range shows how the deferred balance evolved over
    time rather than always showing the current all-time snapshot.
    """
    sql = f"""
SELECT
  COALESCE(
    (SELECT SUM(booking_amount) FROM `{PROJECT}.marts.fct_invoice_line`
     WHERE is_package_sale AND invoice_date <= '{end}'),
    0
  ) AS sold_through_end,
  COALESCE(
    (SELECT SUM(recognised_revenue) FROM `{PROJECT}.marts.fct_service_delivered`
     WHERE delivery_method = 'package_burn' AND delivery_date <= '{end}'),
    0
  ) AS recognised_through_end
"""
    row   = _query(sql)[0]
    sold  = _to_float(row["sold_through_end"])
    recog = _to_float(row["recognised_through_end"])
    return {
        "deferred":      sold - recog,
        "sold":          sold,
        "recognised":    recog,
        "consumed_pct":  round(recog / sold * 100, 1) if sold else None,
    }


def fetch_packages(start: date, end: date) -> dict:
    sql_summary = f"""
SELECT
  COALESCE(SUM(qty), 0)            AS total_units,
  COALESCE(SUM(booking_amount), 0) AS total_revenue,
  (SELECT COUNT(DISTINCT a.patient_id)
   FROM (
     SELECT DISTINCT patient_id
     FROM `{PROJECT}.marts.fct_invoice_line`
     WHERE is_package_sale
       AND invoice_date BETWEEN '{start}' AND '{end}'
       AND patient_id IS NOT NULL
   ) a
   WHERE NOT EXISTS (
     SELECT 1 FROM `{PROJECT}.marts.fct_invoice_line` b
     WHERE b.is_package_sale
       AND b.patient_id = a.patient_id
       AND b.invoice_date < '{start}'
   )) AS new_buyers
FROM `{PROJECT}.marts.fct_invoice_line`
WHERE is_package_sale
  AND invoice_date BETWEEN '{start}' AND '{end}'
"""
    sql_breakdown = f"""
SELECT
  COALESCE(NULLIF(TRIM(item_name), ''), item_given_id, 'Unknown') AS name,
  CAST(SUM(qty) AS INT64)          AS units,
  SUM(booking_amount)              AS revenue
FROM `{PROJECT}.marts.fct_invoice_line`
WHERE is_package_sale
  AND invoice_date BETWEEN '{start}' AND '{end}'
GROUP BY 1
ORDER BY revenue DESC
"""
    try:
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_s = ex.submit(_query, sql_summary)
            f_b = ex.submit(_query, sql_breakdown)
        summary      = f_s.result()[0]
        breakdown_rows = f_b.result()
    except Exception:
        log.exception("fetch_packages failed")
        return {"total_units": 0, "total_revenue": 0.0, "new_buyers": 0, "breakdown": []}

    total_units   = int(summary.get("total_units") or 0)
    total_revenue = _to_float(summary.get("total_revenue"))
    new_buyers    = int(summary.get("new_buyers") or 0)

    breakdown = []
    for row in breakdown_rows:
        units   = int(row.get("units") or 0)
        revenue = _to_float(row.get("revenue"))
        breakdown.append({
            "name":      row.get("name") or "Unknown",
            "units":     units,
            "revenue":   revenue,
            "pct_count": round(units   / total_units   * 100, 1) if total_units   else 0,
            "pct_value": round(revenue / total_revenue * 100, 1) if total_revenue else 0,
        })

    return {
        "total_units":   total_units,
        "total_revenue": total_revenue,
        "new_buyers":    new_buyers,
        "breakdown":     breakdown,
    }


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


def fetch_dismissed_mismatch_ids() -> set[str]:
    """Invoice ids whose provider-attribution alert has been dismissed
    (latest action = 'dismissed'). Used to hide them from the live alert list.

    Dismissals are persistent and server-side (marts.mismatch_dismissal_events),
    replacing the old browser-local localStorage dismiss. Degrades gracefully to
    an empty set if the view hasn't been deployed yet (see DEPLOY.md) — the alert
    must still render.
    """
    try:
        rows = _query(f"""
SELECT invoice_id
FROM `{PROJECT}.marts.mismatch_dismissal_latest`
WHERE action = 'dismissed'
""")
    except Exception as e:
        log.warning("mismatch_dismissal_latest unavailable (run deploy_all.sh?): %s", e)
        return set()
    return {r["invoice_id"] for r in rows}


def fetch_mismatch_history() -> list[dict]:
    """Currently-dismissed provider-attribution alerts, for the Alert-history
    tab. Reads the snapshot captured at dismiss time, so a row still renders even
    after the invoice fell out of the 30-day window or was corrected in Plato.

    Degrades gracefully to [] if the table hasn't been deployed yet.
    """
    try:
        rows = _query(f"""
SELECT invoice_id, reason, invoice_label, invoice_date, patient,
       invoice_doctor, appt_doctors, total, created_by, last_edited_by,
       updated_by, updated_at
FROM `{PROJECT}.marts.mismatch_dismissal_latest`
WHERE action = 'dismissed'
ORDER BY updated_at DESC
""")
    except Exception as e:
        log.warning("mismatch history unavailable (run deploy_all.sh?): %s", e)
        return []
    return [{
        "invoice_id":     r["invoice_id"],
        "invoice_no":     r.get("invoice_label") or (r["invoice_id"] or "")[:8],
        "date":           r["invoice_date"].isoformat() if r.get("invoice_date") else None,
        "patient":        r.get("patient") or "—",
        "invoice_doctor": r.get("invoice_doctor"),
        "appt_doctors":   r.get("appt_doctors"),
        "total":          _to_float(r.get("total")),
        "created_by":     r.get("created_by"),
        "last_edited_by": r.get("last_edited_by"),
        "reason":         r.get("reason"),
        "dismissed_by":   r.get("updated_by"),
        "dismissed_at":   r["updated_at"].isoformat() if r.get("updated_at") else None,
    } for r in rows]


def fetch_invoice_doctor_mismatches() -> dict:
    """Alert-only check: list non-void invoices whose `doctor` disagrees
    with the same-day appointment-calendar doctor for the same patient.

    Reads `marts.fct_invoice_doctor_mismatches`, which does the cross-ref in
    pure SQL against stg.appointments + stg.invoices. The Plato API is no
    longer touched on the dashboard hot path — appointments land in BQ via the
    plato-appointments-ingest Cloud Run Job (15-min cadence).

    Cleared automatically — when an invoice is corrected in Plato, the next
    appointment ingestion + dashboard cache refresh drops the resolved invoice
    off the list. Rows the founder explicitly dismisses are also hidden here
    (persistent, server-side — see fetch_dismissed_mismatch_ids); they live on in
    the Alert-history tab and can be restored.

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

    # Hide invoices the founder has explicitly dismissed (persistent, server-side).
    dismissed = fetch_dismissed_mismatch_ids()
    if dismissed:
        mismatches = [m for m in mismatches if m["invoice_id"] not in dismissed]

    result["mismatches"]    = mismatches
    result["no_appt_count"] = no_appt
    log.info("  mismatches found: %d (window=%dd, %d invoices had no same-day appt, %d dismissed)",
             len(mismatches), MISMATCH_WINDOW_DAYS, no_appt, len(dismissed))
    return result


LINK_CLICK_TABLE = f"{PROJECT}.marts.link_click_events"


def _record_link_click(click_id: str, slug: str, user_agent: str | None, referer: str | None,
                       session_id: str | None = None, page: str | None = None) -> None:
    """Append one click via the streaming insert API (insert_rows_json), NOT
    DML: clicks are public/high-frequency, so this dodges BigQuery's 1,500
    DML-statements-per-table-per-day cap and the latency of a query job.
    Best-effort — never raise into the request; a logging hiccup must not break
    the redirect. `click_id` is minted by the caller so the same id can be passed
    through to the /book landing (?cid=…) for an exact origin→booking join.
    `session_id`/`page` come from on-site CTA taps (the site appends ?sid=&p=) so
    a WhatsApp tap can be tied back to the booking session it came from — the
    golden-flow join. NULL for off-site channels."""
    try:
        row = {
            "click_id":   click_id,
            "slug":       (slug or "")[:64],
            "clicked_at": datetime.now(timezone.utc).isoformat(),
            "user_agent": ((user_agent or "")[:512] or None),
            "referer":    ((referer or "")[:512] or None),
            "session_id": ((session_id or "")[:128] or None),
            "page":       ((page or "")[:512] or None),
        }
        errors = _bq().insert_rows_json(LINK_CLICK_TABLE, [row])
        if errors:
            log.warning("link click insert returned errors: %s", errors)
    except Exception as e:
        log.warning("link click not recorded (slug=%s): %s", slug, e)


def _record_link_click_async(click_id: str, slug: str, user_agent: str | None, referer: str | None,
                             session_id: str | None = None, page: str | None = None) -> None:
    """Fire-and-forget so the public redirect returns immediately."""
    threading.Thread(target=_record_link_click,
                     args=(click_id, slug, user_agent, referer, session_id, page),
                     daemon=True).start()


# Crawlers, link previewers, scripts and our own audit runner all follow go-links.
# Google's renderer poses as a Nexus 5X phone, so it's matched by device string.
BOT_UA_RE = (r"bot|crawl|spider|slurp|headless|lighthouse|preview|python|curl|wget|"
             r"go-http|okhttp|axios|node-fetch|httpclient|facebookexternalhit|"
             r"whatsapp/|nexus 5x build/mmb29p|gojisiteaudit")
# On-site taps carry the tab's session id (?sid=) from this date on.
WEB_TAP_SID_SINCE = "2026-07-14"


def fetch_link_clicks(start: date, end: date) -> dict:
    """Tracked-link clicks for [start, end], split into WhatsApp vs booking
    (the two CTAs) with a per-channel breakdown each.

    Counts real taps only. Every slug drops bot/tooling user agents. On-site
    `web-*` taps must also belong to a beacon session (with a visitor id) that
    started under 6 hours earlier: crawlers don't run the script that adds
    ?sid=, and the long-open desktop tabs of our own QA and audit tools tap the
    same CTA for days. Raw counts were up to 8x real in Oct 2026. Taps from
    before the ?sid= passthrough existed keep the UA filter only.

    Degrades to zeros if the table isn't deployed yet (see DEPLOY.md): the
    Marketing tab must still render.
    """
    empty = {"whatsapp": 0, "booking": 0, "total": 0, "wa_by_slug": {}, "book_by_slug": {}}
    try:
        rows = _query(f"""
WITH s AS (
  SELECT session_id, MIN(occurred_at) AS first_seen
  FROM `{PROJECT}.marts.web_session_events`
  WHERE DATE(occurred_at) BETWEEN DATE_SUB('{start}', INTERVAL 1 DAY) AND '{end}'
    AND visitor_id IS NOT NULL
  GROUP BY session_id
)
SELECT c.slug, COUNT(*) AS clicks
FROM `{PROJECT}.marts.link_click_events` c
LEFT JOIN s USING (session_id)
WHERE DATE(c.clicked_at) BETWEEN '{start}' AND '{end}'
  AND c.user_agent IS NOT NULL
  AND NOT REGEXP_CONTAINS(LOWER(c.user_agent), r'{BOT_UA_RE}')
  AND (NOT STARTS_WITH(c.slug, 'web-')
       OR DATE(c.clicked_at) < '{WEB_TAP_SID_SINCE}'
       OR c.clicked_at < TIMESTAMP_ADD(s.first_seen, INTERVAL 6 HOUR))
GROUP BY c.slug
""")
    except Exception as e:
        log.warning("link_click_events unavailable (run deploy_all.sh?): %s", e)
        return empty
    wa_by_slug: dict[str, int] = {}
    book_by_slug: dict[str, int] = {}
    for r in rows:
        kind = LINK_SLUG_KIND.get(r["slug"])
        if kind is None or kind == "pay":
            # unknown slug = bot/scanner traffic, not a marketing channel; shop
            # (pay) clicks are neither a WhatsApp nor a booking CTA.
            continue
        n = _to_int(r["clicks"])
        if kind == "book":  # website /book form (incl. retired *-plato slugs)
            book_by_slug[r["slug"]] = n
        else:
            wa_by_slug[r["slug"]] = n
    wa, bk = sum(wa_by_slug.values()), sum(book_by_slug.values())
    return {"whatsapp": wa, "booking": bk, "total": wa + bk,
            "wa_by_slug": wa_by_slug, "book_by_slug": book_by_slug}


# Ordered website booking-funnel stages (event stage -> display label).
# date_picked only started recording 2026-07-22, so ranges before that show 0
# for it — the render treats a zero mid-stage as "no data", not a 100% drop.
BOOKING_FUNNEL_STAGES = [
    ("page_view", "Viewed"),
    ("service_selected", "Chose service"),
    ("date_picked", "Picked date"),
    ("time_selected", "Chose time"),
    ("details", "Entered details"),
    ("submitted", "Submitted"),
    ("confirmed", "Booked"),
]


def fetch_booking_funnel(start: date, end: date) -> dict:
    """Website /book funnel for [start, end]: distinct sessions reaching each
    stage, in order, from marts.booking_funnel_events (written by goji-booking).

    Degrades to zeros if the table isn't deployed yet, like fetch_link_clicks —
    the Marketing tab must still render.
    """
    labels = dict(BOOKING_FUNNEL_STAGES)
    order = [s for s, _ in BOOKING_FUNNEL_STAGES]
    empty = {"stages": [{"stage": s, "label": labels[s], "sessions": 0} for s in order],
             "viewed": 0, "booked": 0, "conversion_pct": 0.0,
             "clinician_changed": 0,
             "stuck": {"availability_empty": 0, "availability_error": 0,
                       "validation_error": 0,
                       "book_error": 0, "book_error_by_code": {}}}
    try:
        # One pass, but detail is collapsed for every stage except book_error
        # (whose reason code we split on). Several stages now carry a detail
        # (date_picked = the date, clinician_changed = the clinician id) —
        # grouping raw (stage, detail) would over-count a session that e.g.
        # picked three dates, so the distinct-session count must be per stage.
        rows = _query(f"""
SELECT stage, IF(stage = 'book_error', detail, NULL) AS detail,
       COUNT(DISTINCT session_id) AS sessions
FROM `{PROJECT}.marts.booking_funnel_events`
WHERE DATE(occurred_at) BETWEEN '{start}' AND '{end}'
GROUP BY stage, detail
""")
    except Exception as e:
        log.warning("booking_funnel_events unavailable (run deploy_all.sh?): %s", e)
        return empty
    counts: dict[str, int] = {}
    book_error_by_code: dict[str, int] = {}
    for r in rows:
        stage, n = r["stage"], _to_int(r["sessions"])
        counts[stage] = counts.get(stage, 0) + n
        if stage == "book_error":
            code = r.get("detail") or "error"
            book_error_by_code[code] = book_error_by_code.get(code, 0) + n
    viewed = counts.get("page_view", 0)
    booked = counts.get("confirmed", 0)
    return {
        "stages": [{"stage": s, "label": labels[s], "sessions": counts.get(s, 0)} for s in order],
        "viewed": viewed,
        "booked": booked,
        "conversion_pct": round(booked / viewed * 100.0, 1) if viewed else 0.0,
        # Behaviour note, not a stage: sessions that touched the clinician
        # picker (the default "First available" needs no interaction).
        "clinician_changed": counts.get("clinician_changed", 0),
        # "Where they get stuck" — silent dead-ends, distinct sessions each.
        "stuck": {
            "availability_empty": counts.get("availability_empty", 0),
            "availability_error": counts.get("availability_error", 0),
            "validation_error":   counts.get("validation_error", 0),
            "book_error":         counts.get("book_error", 0),
            "book_error_by_code": book_error_by_code,
        },
    }


def fetch_google_ads(start: date, end: date) -> dict:
    """Google Ads spend/clicks/impressions for [start, end] from the BQ Data Transfer dataset.

    Queries goji-bi.google_ads directly (US region; a mart view can't cross regions).
    Degrades to zeros if the transfer hasn't run yet or tables have an unexpected schema.
    """
    empty = {"spend": 0.0, "clicks": 0, "impressions": 0, "cpc": None}
    try:
        # Pick the table deterministically. The old regex
        # (`campaign.*(basic)?stats|account.*(basic)?stats`) matched ~20 tables
        # and took `tables[0]` with no ORDER BY, so the choice depended on
        # whatever INFORMATION_SCHEMA happened to return first. Two ways that
        # bit us: it landed on `p_ads_HourlyAccountStats` (account-level, whose
        # impressions disagree with the campaign roll-up — 21,202 vs 12,851 for
        # Aug 2026), and a *ConversionStats table is one row-order change away
        # from being picked, which has no cost/click columns at all and would
        # silently degrade the whole card to zeros.
        #
        # CampaignBasicStats is the canonical spend/clicks/impressions grain.
        # Prefer the plain table, then its `p_`-prefixed partitioned twin, and
        # only then fall back to account-level basic stats.
        tables = _query(f"""
SELECT table_name,
       CASE
         WHEN REGEXP_CONTAINS(LOWER(table_name), r'^ads_campaignbasicstats_')   THEN 1
         WHEN REGEXP_CONTAINS(LOWER(table_name), r'^p_ads_campaignbasicstats_') THEN 2
         WHEN REGEXP_CONTAINS(LOWER(table_name), r'^ads_accountbasicstats_')    THEN 3
         WHEN REGEXP_CONTAINS(LOWER(table_name), r'^p_ads_accountbasicstats_')  THEN 4
       END AS preference
FROM `{PROJECT}.google_ads.INFORMATION_SCHEMA.TABLES`
WHERE REGEXP_CONTAINS(LOWER(table_name),
        r'^p?_?ads_(campaign|account)basicstats_')
ORDER BY preference, table_name
LIMIT 1
""")
        if not tables:
            return empty
        table_name = tables[0]["table_name"]
        # Google Ads API transfer uses metrics_* and segments_date
        sql = f"""
SELECT SUM(metrics_cost_micros) / 1e6 AS spend, SUM(metrics_clicks) AS clicks, SUM(metrics_impressions) AS impressions
FROM `{PROJECT}.google_ads.{table_name}`
WHERE segments_date BETWEEN '{start}' AND '{end}'
"""
        rows = _query(sql)
        if not rows or rows[0]["clicks"] is None:
            return empty
        r      = rows[0]
        spend  = float(r["spend"] or 0)
        clicks = _to_int(r["clicks"])
        return {
            "spend":       spend,
            "clicks":      clicks,
            "impressions": _to_int(r["impressions"]),
            "cpc":         round(spend / clicks, 2) if clicks else None,
        }
    except Exception as e:
        log.warning("google_ads unavailable: %s", e)
        return empty


def fetch_paid_funnel(start: date, end: date) -> dict:
    """On-site outcome of paid (gclid-carrying) sessions in [start, end].

    The other half of cost-per-booking: `fetch_google_ads` has the money,
    this has what the money bought. Kept as a separate query on purpose —
    `google_ads` lives in the US multi-region and cannot be joined to `marts`
    in one statement, so the two are combined in Python (same reason
    `fetch_google_ads` talks to the transfer dataset directly).

    A session is "paid" when its **first** event carries a `gclid`. Using the
    first event matters: `web_session_events` rows persist across navigation
    (a session can span 11 paths), so keying off any-row would count a session
    that merely *passed through* a tagged landing. Auto-tagging puts the gclid
    on the ad click's landing only.

    Degrades to zeros if the beacon tables aren't deployed, like the rest of
    the Marketing tab.
    """
    empty = {"sessions": 0, "entered_funnel": 0, "bookings": 0,
             "funnel_entry_pct": 0.0, "booking_pct": 0.0}
    try:
        rows = _query(f"""
WITH first_hit AS (
  SELECT session_id, gclid,
         ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY occurred_at) AS rn
  FROM `{PROJECT}.marts.web_session_events`
  WHERE DATE(occurred_at) BETWEEN '{start}' AND '{end}'
),
paid AS (
  SELECT session_id FROM first_hit
  WHERE rn = 1 AND gclid IS NOT NULL AND gclid != ''
),
funnel AS (
  SELECT DISTINCT session_id
  FROM `{PROJECT}.marts.booking_funnel_events`
  WHERE DATE(occurred_at) BETWEEN '{start}' AND '{end}'
),
booked AS (
  SELECT DISTINCT session_id
  FROM `{PROJECT}.marts.booking_funnel_events`
  WHERE DATE(occurred_at) BETWEEN '{start}' AND '{end}' AND stage = 'confirmed'
)
SELECT COUNT(*)                                        AS sessions,
       COUNTIF(f.session_id IS NOT NULL)               AS entered_funnel,
       COUNTIF(b.session_id IS NOT NULL)               AS bookings
FROM paid p
LEFT JOIN funnel f USING (session_id)
LEFT JOIN booked b USING (session_id)
""")
        if not rows or rows[0]["sessions"] is None:
            return empty
        r        = rows[0]
        sessions = _to_int(r["sessions"])
        entered  = _to_int(r["entered_funnel"])
        booked   = _to_int(r["bookings"])
        return {
            "sessions":         sessions,
            "entered_funnel":   entered,
            "bookings":         booked,
            "funnel_entry_pct": round(entered / sessions * 100.0, 1) if sessions else 0.0,
            "booking_pct":      round(booked / sessions * 100.0, 2) if sessions else 0.0,
        }
    except Exception as e:
        log.warning("paid_funnel unavailable (run deploy_all.sh?): %s", e)
        return empty


def _paid_performance(ads: dict, paid: dict) -> dict:
    """Combine ad spend with the paid on-site outcome into the numbers the
    Marketing tab actually decides on.

    `cost_per_booking` is genuinely undefined at zero bookings, so it stays
    None rather than collapsing to the spend figure — a card reading
    "SGD 607 per booking" when nothing was booked is a different (and much
    rosier) claim than "SGD 607, nothing booked". The UI needs both numbers to
    say the true thing, so `spend` and `bookings` travel alongside it and
    `spend_without_booking` names the at-risk case explicitly.

    `cost_per_funnel_entry` is the leading indicator: at SGD 20/day, bookings
    are too sparse to move week to week, but funnel entries move first.
    """
    spend    = float(ads.get("spend") or 0.0)
    bookings = _to_int(paid.get("bookings") or 0)
    entered  = _to_int(paid.get("entered_funnel") or 0)
    return {
        "spend":                 round(spend, 2),
        "bookings":              bookings,
        "entered_funnel":        entered,
        "cost_per_booking":      round(spend / bookings, 2) if bookings else None,
        "spend_without_booking": round(spend, 2) if spend and not bookings else None,
        "cost_per_funnel_entry": round(spend / entered, 2) if entered else None,
    }


def fetch_organic_search(start: date, end: date) -> dict:
    """Organic Google Search performance for [start, end] from
    marts.fct_search_console_daily (fed by the marketing_ingest `search_console`
    source).

    Clicks and impressions SUM. **Average position is impression-weighted** —
    SUM(position_weight)/SUM(impressions), never AVG(position_avg) — which is
    exactly why the mart carries `position_weight`. CTR is likewise recomputed
    from the summed clicks/impressions, not averaged.

    Degrades to zeros if the ingestion hasn't run yet, so the Marketing tab
    renders before Search Console is wired up.
    """
    empty = {"clicks": 0, "impressions": 0, "ctr": None, "position": None}
    try:
        rows = _query(f"""
SELECT SUM(clicks)          AS clicks,
       SUM(impressions)     AS impressions,
       SUM(position_weight) AS position_weight
FROM `{PROJECT}.marts.fct_search_console_daily`
WHERE metric_date BETWEEN '{start}' AND '{end}'
""")
        if not rows or rows[0]["impressions"] is None:
            return empty
        r      = rows[0]
        clicks = _to_int(r["clicks"])
        impr   = _to_int(r["impressions"])
        weight = float(r["position_weight"] or 0)
        return {
            "clicks":      clicks,
            "impressions": impr,
            "ctr":         round(clicks / impr * 100.0, 2) if impr else None,
            "position":    round(weight / impr, 1) if impr else None,
        }
    except Exception as e:
        log.warning("organic_search unavailable (search_console ingested?): %s", e)
        return empty


def fetch_instagram_reach(start: date, end: date) -> dict:
    """Instagram account reach (de-duplicated) from marts.fct_instagram_reach,
    fed by the marketing_ingest Cloud Run Job (Meta Graph API).

    Reach counts *unique accounts reached*, so it is NOT additive — monthly reach
    is not the sum of daily reach. We ingest Meta's rolling 28-day reach once a
    day and here return the latest reading on or before `end` (reach "as of" the
    period end); the trend compares that against the reading at the previous
    period's end. Windowing by [start, end] would wrongly imply summability, so
    we intentionally read a single snapshot, not a range aggregate.

    Degrades to zero if the table/data isn't there yet (like fetch_google_ads),
    so the Marketing tab still renders.
    """
    empty = {"reach": 0}
    try:
        rows = _query(f"""
SELECT reach
FROM `{PROJECT}.marts.fct_instagram_reach`
WHERE metric_date <= '{end}'
ORDER BY metric_date DESC
LIMIT 1
""")
        if not rows or rows[0]["reach"] is None:
            return empty
        return {"reach": _to_int(rows[0]["reach"])}
    except Exception as e:
        log.warning("instagram_reach unavailable: %s", e)
        return empty


def fetch_instagram_engagement(start: date, end: date) -> dict:
    """Actionable Instagram signals beyond reach — the "did reach turn into
    interest, and is the audience growing?" step — fed by the marketing_ingest job.

    - profile_views: ADDITIVE daily count → SUM over [start, end]
      (marts.fct_instagram_profile_views).
    - followers: a running TOTAL snapshot → the latest reading ≤ end for the
      count, and growth = latest − first-in-window (marts.fct_instagram_followers,
      same read-latest pattern as fetch_instagram_reach; never SUM a total).

    Each metric degrades independently to None if its data isn't there yet, so the
    card shows "—" per-metric rather than breaking the tab.
    """
    out: dict[str, int | None] = {"profile_views": None, "followers": None, "follower_growth": None}
    try:
        rows = _query(f"""
SELECT SUM(profile_views) AS profile_views
FROM `{PROJECT}.marts.fct_instagram_profile_views`
WHERE metric_date BETWEEN '{start}' AND '{end}'
""")
        if rows and rows[0]["profile_views"] is not None:
            out["profile_views"] = _to_int(rows[0]["profile_views"])
    except Exception as e:
        log.warning("instagram profile_views unavailable: %s", e)
    try:
        rows = _query(f"""
SELECT
  (SELECT followers FROM `{PROJECT}.marts.fct_instagram_followers`
   WHERE metric_date <= '{end}' ORDER BY metric_date DESC LIMIT 1)   AS latest,
  (SELECT followers FROM `{PROJECT}.marts.fct_instagram_followers`
   WHERE metric_date BETWEEN '{start}' AND '{end}'
   ORDER BY metric_date ASC LIMIT 1)                                 AS first_in_window
""")
        if rows and rows[0]["latest"] is not None:
            latest = _to_int(rows[0]["latest"])
            out["followers"] = latest
            first = rows[0]["first_in_window"]
            if first is not None:
                out["follower_growth"] = latest - _to_int(first)
    except Exception as e:
        log.warning("instagram followers unavailable: %s", e)
    return out


def fetch_web_sessions(start: date, end: date) -> dict:
    """Website sessions & pageviews for [start, end] from the GA4 BigQuery export
    (the free native daily export; dataset `analytics_<propertyId>`, tables
    `events_YYYYMMDD`).

    Like fetch_google_ads, this queries a separate — and possibly cross-region —
    dataset directly, and degrades to zeros if the export isn't linked yet
    (GA4_DATASET unset) or the tables aren't there, so the Website card simply
    stays empty until GA4 data flows. A GA4 session is the distinct pair
    (user_pseudo_id, ga_session_id); pageviews are `page_view` events. Daily
    `events_intraday_*` tables are excluded naturally — their _TABLE_SUFFIX
    ("intraday_…") sorts outside a YYYYMMDD range.
    """
    empty = {"sessions": 0, "pageviews": 0}
    if not GA4_DATASET:
        return empty
    try:
        rows = _query(f"""
SELECT
  COUNT(DISTINCT CONCAT(
    user_pseudo_id, '-',
    CAST((SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS STRING)
  ))                                AS sessions,
  COUNTIF(event_name = 'page_view') AS pageviews
FROM `{GA4_PROJECT}.{GA4_DATASET}.events_*`
WHERE _TABLE_SUFFIX BETWEEN '{start.strftime("%Y%m%d")}' AND '{end.strftime("%Y%m%d")}'
""")
        if not rows or rows[0]["sessions"] is None:
            return empty
        return {"sessions": _to_int(rows[0]["sessions"]), "pageviews": _to_int(rows[0]["pageviews"])}
    except Exception as e:
        log.warning("web_sessions unavailable (GA4 export linked? GA4_DATASET set?): %s", e)
        return empty


def fetch_lead_wins(start: date, end: date) -> dict:
    """Won leads (became a patient) by channel for leads that *entered* in
    [start, end] (bucketed by first_seen — the cohort funnel view). Reads
    marts.lead_latest; 'won' is terminal, so the latest stage captures it.

    Feeds the funnel's patient outcome. Degrades to {} so the patient node
    simply doesn't draw until the front desk logs and wins leads.
    """
    try:
        rows = _query(f"""
SELECT COALESCE(channel, 'other') AS channel, COUNTIF(stage = 'won') AS won
FROM `{PROJECT}.marts.lead_latest`
WHERE DATE(first_seen) BETWEEN '{start}' AND '{end}'
GROUP BY channel
""")
    except Exception as e:
        log.warning("lead_wins unavailable (run deploy_all.sh?): %s", e)
        return {}
    return {r["channel"]: _to_int(r["won"]) for r in rows}


# Discovery-channel classification, shared by fetch_web_channels (the channel
# totals feeding the Sankey) and fetch_referral_domains (which de-blackboxes the
# 'Referral' catch-all below) so the two classifiers can never drift apart.
_WEB_CHANNEL_CASE_SQL = """
CASE
  WHEN gclid IS NOT NULL AND gclid != '' THEN 'Google Ads'
  WHEN LOWER(utm_medium) IN ('cpc','ppc','paid') AND LOWER(utm_source) LIKE 'google%' THEN 'Google Ads'
  WHEN (fbclid IS NOT NULL AND fbclid != '') OR LOWER(utm_source) IN ('facebook','meta','fb') THEN 'Meta Ads'
  WHEN LOWER(utm_source) IN ('instagram','ig') OR REGEXP_CONTAINS(LOWER(referer), r'instagram') THEN 'Instagram'
  WHEN LOWER(utm_source) LIKE 'gbp%' OR LOWER(utm_source) LIKE 'google_business%' THEN 'Google'
  WHEN LOWER(utm_source) IN ('chatgpt.com','perplexity','openai')
    OR REGEXP_CONTAINS(LOWER(referer), r'^https?://([a-z0-9-]+\\.)*(chatgpt\\.com|openai\\.com|perplexity\\.ai|claude\\.ai|gemini\\.google\\.com|copilot\\.microsoft\\.com)') THEN 'AI assistants'
  WHEN LOWER(utm_source) LIKE 'google%' OR REGEXP_CONTAINS(LOWER(referer), r'google\\.') THEN 'Google'
  WHEN REGEXP_CONTAINS(LOWER(referer), r'^https?://([a-z0-9-]+\\.)*(bing\\.com|duckduckgo\\.com|search\\.yahoo\\.com|ecosia\\.org|search\\.brave\\.com)') THEN 'Other search'
  WHEN utm_source IS NOT NULL AND utm_source != '' THEN utm_source
  WHEN referer IS NULL OR referer = '' THEN 'Direct'
  -- Our own domain (pre-Nov-2026 rows stored the page URL, not the visitor's
  -- referrer; a new tab opened from the site does the same) is not a referral.
  WHEN REGEXP_CONTAINS(LOWER(referer), r'^https?://([a-z0-9-]+\\.)*(gojiphysio\\.com|goji-bgb\\.pages\\.dev)') THEN 'Direct'
  ELSE 'Referral'
END
"""


def fetch_web_channels(start: date, end: date) -> dict:
    """Website landings for [start, end] grouped into a discovery *channel*, from
    the first-party landing beacon (marts.web_session_events). This is the top of
    the funnel — how visitors ARRIVE at the site — so "Website" becomes the owned
    surface fed by Google Ads / Instagram / Google / Direct, not a phantom source.

    A session (distinct session_id) is one landing. Degrades to {} until the
    beacon is deployed and PUBLIC_BOOKING_API is set, so the funnel just omits the
    discovery→Website edges rather than breaking.

    Sessions that LAND on /links (the Instagram link-in-bio page) are split out
    under the "Link in bio" surface instead of "Website": returns
    {"website": {channel: n}, "links": {channel: n}}. Without the split an
    Instagram visitor to /links was counted twice — once as an Instagram →
    Website landing and again on the Instagram → Link in bio tap edge.
    """
    try:
        rows = _query(f"""
WITH links_sessions AS (
  SELECT DISTINCT session_id
  FROM `{PROJECT}.marts.web_session_events`
  WHERE DATE(occurred_at) BETWEEN '{start}' AND '{end}'
    AND event_type = 'session_start' AND landing_path LIKE '/links%'
)
SELECT
  {_WEB_CHANNEL_CASE_SQL} AS channel,
  session_id IN (SELECT session_id FROM links_sessions) AS on_links,
  COUNT(DISTINCT session_id) AS sessions
FROM `{PROJECT}.marts.web_session_events`
WHERE DATE(occurred_at) BETWEEN '{start}' AND '{end}'
GROUP BY channel, on_links
""")
    except Exception as e:
        log.warning("web_session_events unavailable (run deploy_all.sh?): %s", e)
        return {"website": {}, "links": {}}
    out: dict = {"website": {}, "links": {}}
    for r in rows:
        if not r["channel"]:
            continue
        bucket = out["links"] if r["on_links"] else out["website"]
        bucket[r["channel"]] = bucket.get(r["channel"], 0) + _to_int(r["sessions"])
    return out


REFERRAL_DOMAIN_TOP_N = 5


def fetch_referral_domains(start: date, end: date) -> dict:
    """De-blackboxes the Sankey's "Referral" catch-all: the actual registrable
    domains behind untagged external-referrer landings (fetch_web_channels
    collapses every one of these into a single 'Referral' node — this recovers
    what's actually in it). Rendered as a hover tooltip on the Referral legend
    swatch rather than a table, so it stays glanceable.

    Top REFERRAL_DOMAIN_TOP_N domains by distinct-session count; the remainder
    rolls into "other" so a long tail of one-off domains doesn't dominate.
    Shares _WEB_CHANNEL_CASE_SQL with fetch_web_channels so "which rows count as
    Referral" can't drift between the two. Degrades to {} like every fetch_* here.
    """
    try:
        rows = _query(f"""
WITH classified AS (
  SELECT session_id, referer, {_WEB_CHANNEL_CASE_SQL} AS channel
  FROM `{PROJECT}.marts.web_session_events`
  WHERE DATE(occurred_at) BETWEEN '{start}' AND '{end}'
)
SELECT NET.REG_DOMAIN(NET.HOST(referer)) AS domain, COUNT(DISTINCT session_id) AS sessions
FROM classified
WHERE channel = 'Referral'
GROUP BY domain
ORDER BY sessions DESC
""")
    except Exception as e:
        log.warning("referral domain breakdown unavailable: %s", e)
        return {}
    domains = [(r["domain"] or "unknown", _to_int(r["sessions"])) for r in rows]
    top = dict(domains[:REFERRAL_DOMAIN_TOP_N])
    rest = sum(n for _, n in domains[REFERRAL_DOMAIN_TOP_N:])
    if rest:
        top["other"] = rest
    return top


# Website page taxonomy for per-page attribution. The landing beacon records
# location.pathname on EVERY event (session_start AND page_view — see
# BaseLayout.astro), so web_session_events.landing_path is the current page per
# pageview, not just the session's first landing. This CASE turns raw paths into
# a small, stable set of pages so "Website" splits into Home / Booking /
# Conditions / … instead of one vague surface. Keep buckets in sync with the
# site's route tree (marketing/website/src/pages).
_WEB_PAGE_CASE_SQL = """
CASE
  WHEN landing_path = '/' OR landing_path = '' OR landing_path IS NULL THEN 'Home'
  WHEN landing_path LIKE '/book%'       THEN 'Booking'
  WHEN landing_path LIKE '/conditions%' THEN 'Conditions'
  WHEN landing_path LIKE '/services%'   THEN 'Services'
  WHEN landing_path LIKE '/team%'       THEN 'Team'
  WHEN landing_path LIKE '/blog%'       THEN 'Blog'
  WHEN landing_path LIKE '/links%'      THEN 'Link in bio'
  ELSE 'Other'
END
"""

# Display order for the per-page bars (buckets not present are simply skipped).
WEB_PAGE_ORDER = ["Home", "Booking", "Conditions", "Services", "Team", "Blog", "Link in bio", "Other"]


def fetch_web_pages(start: date, end: date) -> list[dict]:
    """Per-page website engagement for [start, end] from the landing beacon
    (marts.web_session_events): landings (sessions that STARTED on the page) and
    total pageviews per page bucket. De-blackboxes the old single "Website"
    surface into Home / Booking / Conditions / … so we can see which pages pull
    people in and which get browsed.

    A "landing" is a session_start row (where the visit began); a "pageview" is
    any event on that page. Ordered by WEB_PAGE_ORDER. Degrades to [] until the
    beacon is deployed, like fetch_web_channels.
    """
    try:
        rows = _query(f"""
SELECT
  {_WEB_PAGE_CASE_SQL} AS page,
  COUNTIF(event_type = 'session_start') AS landings,
  COUNT(*)                              AS pageviews
FROM `{PROJECT}.marts.web_session_events`
WHERE DATE(occurred_at) BETWEEN '{start}' AND '{end}'
GROUP BY page
""")
    except Exception as e:
        log.warning("web_session_events per-page unavailable (run deploy_all.sh?): %s", e)
        return []
    by_page = {r["page"]: {"landings": _to_int(r["landings"]),
                           "pageviews": _to_int(r["pageviews"])} for r in rows}
    return [{"page": p, "landings": by_page[p]["landings"], "pageviews": by_page[p]["pageviews"]}
            for p in WEB_PAGE_ORDER if p in by_page]


def fetch_onsite_flow(start: date, end: date) -> dict:
    """Golden-flow outcomes for on-site booking-page sessions in [start, end]:
    of the sessions that reached /book, how many BOOKED, how many bailed to
    WhatsApp, and how many DROPPED (left with neither).

    Booking-page sessions and their confirmed count come from
    marts.booking_funnel_events (session_id grain). The WhatsApp bail-out is the
    golden-flow join enabled by the on-site CTA passthrough: link_click_events
    rows for WhatsApp slugs carrying a session_id that also appears in the
    booking funnel (see marts/51_link_click_events.sql). Until the passthrough
    has data, tapped_whatsapp is 0 and the section shows booked-vs-dropped only.

    Degrades to zeros if either table is missing — the Marketing tab still renders.
    """
    empty = {"booking_sessions": 0, "booked": 0, "tapped_whatsapp": 0, "dropped": 0}
    try:
        rows = _query(f"""
WITH bf AS (
  SELECT
    COUNT(DISTINCT session_id)                                          AS booking_sessions,
    COUNT(DISTINCT IF(stage = 'confirmed', session_id, NULL))          AS booked,
    ARRAY_AGG(DISTINCT session_id IGNORE NULLS)                        AS sids
  FROM `{PROJECT}.marts.booking_funnel_events`
  WHERE DATE(occurred_at) BETWEEN '{start}' AND '{end}'
),
wa AS (
  SELECT COUNT(DISTINCT c.session_id) AS tapped_whatsapp
  FROM `{PROJECT}.marts.link_click_events` c, bf
  WHERE DATE(c.clicked_at) BETWEEN '{start}' AND '{end}'
    AND c.session_id IS NOT NULL
    AND ENDS_WITH(c.slug, '-wa')
    AND c.session_id IN UNNEST(bf.sids)
    AND c.session_id NOT IN UNNEST(
      (SELECT ARRAY_AGG(DISTINCT session_id IGNORE NULLS)
       FROM `{PROJECT}.marts.booking_funnel_events`
       WHERE DATE(occurred_at) BETWEEN '{start}' AND '{end}' AND stage = 'confirmed'))
)
SELECT bf.booking_sessions, bf.booked, wa.tapped_whatsapp
FROM bf, wa
""")
    except Exception as e:
        log.warning("onsite_flow unavailable (run deploy_all.sh?): %s", e)
        return empty
    if not rows or rows[0]["booking_sessions"] is None:
        return empty
    r = rows[0]
    sessions = _to_int(r["booking_sessions"])
    booked   = _to_int(r["booked"])
    tapped   = _to_int(r["tapped_whatsapp"])
    dropped  = max(0, sessions - booked - tapped)
    return {"booking_sessions": sessions, "booked": booked,
            "tapped_whatsapp": tapped, "dropped": dropped}


# Funnel-path source label per link slug prefix (slug = "<source>-<cta>", see
# LINK_SLUGS). `bio` is handled specially: /links is the Instagram link-in-bio
# page, so bio-* taps flow Instagram -> Link in bio -> CTA. `web` is the owned
# Website surface (fed by discovery channels from the landing beacon), not a
# discovery source itself. A generic slug with no prefix ('wa'/'book') is "Other".
FUNNEL_SOURCE = {"gbp": "Google", "ads": "Ads", "qr": "QR", "ig": "Instagram"}
# Discovery channels below this many arrival sessions fold into "Other" so the
# Sankey doesn't sprout hairline bands for one-off referrers (see _build_funnel_paths).
FUNNEL_DISCOVERY_MIN = 2
# CTA label per slug suffix. "plato" (the retired Plato-booking flow) merges
# into "Native booking" — those taps now land on the same tracked /book form.
# Campaign slugs ("<channel>-99-wa") partition to the suffix "99-wa"; map it so
# the Sankey attributes campaign taps to WhatsApp explicitly, not by fallback.
FUNNEL_CTA = {"wa": "WhatsApp", "book": "Native booking", "plato": "Native booking",
              "99-wa": "WhatsApp", "post-book": "Native booking"}


def _build_funnel_paths(link_clicks: dict, kpis: dict, lead_wins: dict,
                        web_channels: dict, booking_funnel: dict,
                        referral_domains: dict | None = None) -> dict:
    """Build the acquisition-funnel Sankey as a 4-column hierarchy so the *web is
    no longer the top of funnel* — it's the owned surface that discovery channels
    drive people into:

        Discovery ─▶ Owned surface ─▶ CTA / intent ─▶ Outcome
        (how they arrive)  (Website,     (WhatsApp,      (Booked)
                            Link in bio)  Native booking)

    Data, joined across the three first-party event streams (each edge is its own
    honest measure; units shift across columns — sessions → taps → bookings —
    like any acquisition funnel):
      - Discovery → Website: landings by channel from the beacon (`web_channels`,
        marts.web_session_events). This is the arrival layer. "Referral" is a
        catch-all for untagged external referrers — see `referral_domains`
        (from `fetch_referral_domains`) for what's actually in it.
      - Surface → CTA: go-link taps (`link_clicks`, marts.link_click_events),
        slug = "<source>-<cta>". web-* sit under Website; bio-* under Link in bio
        (plus an Instagram → Link in bio edge); gbp-/ads-/qr-/ig-* bypass our site,
        so they run Discovery → CTA directly. Retired Plato-booking slugs
        (`*-plato`) merge into "Native booking" — they redirect to the same
        /book form now, so there's a single trackable booking CTA.
      - CTA → Booked: Native booking → Booked = confirmed bookings
        (`booking_funnel`); WhatsApp → Booked = won WhatsApp leads (`lead_wins`,
        the one channel→patient bridge).

    `first_visits` (all-source new patients) rides along as a stat so the gap to
    tracked conversions stays visible. Degrades gracefully: any missing stream
    just drops its edges rather than breaking the chart.
    """
    lc = link_clicks or {}
    wa = lc.get("wa_by_slug", {}) or {}
    bk = lc.get("book_by_slug", {}) or {}

    flows: dict[tuple[str, str], int] = {}
    def add(src: str, dst: str, n: int) -> None:
        if n:
            flows[(src, dst)] = flows.get((src, dst), 0) + n

    # 1) Discovery → Website (arrival), from the landing beacon. Fold the tiny
    # long-tail (a stray session or two from an odd channel) into "Other" so the
    # Sankey stays readable — the granular per-page/per-domain story lives in the
    # separate on-site-path viz and the Referral hover, not in a forest of
    # hairline bands. "Direct" is never folded (it's a meaningful arrival mode).
    # web_channels is {"website": {...}, "links": {...}} (fetch_web_channels);
    # a flat {channel: n} is still accepted as all-Website.
    wc = web_channels or {}
    split = isinstance(wc.get("website"), dict) or isinstance(wc.get("links"), dict)
    web_ch = dict(wc.get("website") or {}) if split else dict(wc)
    links_ch = dict(wc.get("links") or {}) if split else {}
    for surface, by_channel in (("Website", web_ch), ("Link in bio", links_ch)):
        folded = 0
        for channel, n in by_channel.items():
            if channel != "Direct" and n < FUNNEL_DISCOVERY_MIN:
                folded += n
            else:
                add(channel, surface, n)
        if folded:
            add("Other", surface, folded)

    # 2) Surface → CTA (taps). Suffix = CTA; prefix = surface/source.
    bio_total = 0
    for by_slug in (wa, bk):
        for slug, n in by_slug.items():
            prefix, _, suffix = slug.partition("-")
            cta = FUNNEL_CTA.get(suffix or prefix, "WhatsApp")
            if suffix == "" :  # generic slug ('wa'/'book'/'plato') → Other source
                add("Other", cta, n)
            elif prefix == "web":
                add("Website", cta, n)
            elif prefix == "bio":
                add("Link in bio", cta, n)
                bio_total += n
            elif prefix == "ig":
                add("Instagram", cta, n)          # direct IG tap (story/post)
            else:
                add(FUNNEL_SOURCE.get(prefix, "Other"), cta, n)  # gbp/ads/qr bypass the site
    # Arrivals on Link in bio come from the beacon's /links landings. Only when
    # there are none (ranges before /links replaced bio.site in Oct 2026, whose
    # taps happened on bio.site) fall back to inferring them from the taps.
    if bio_total and not links_ch:
        add("Instagram", "Link in bio", bio_total)

    wa_taps   = sum(wa.values())
    book_taps = sum(bk.values())  # native /book taps, incl. retired plato-slug clicks

    # 3) CTA → Booked. Native booking's outcome is the real confirmed count from
    # the on-site funnel; WhatsApp's is the won-lead bridge (clamped to taps).
    booked_native = _to_int((booking_funnel or {}).get("booked", 0))
    add("Native booking", "Booked", booked_native)
    booked_wa = min(wa_taps, _to_int((lead_wins or {}).get("whatsapp", 0)))
    add("WhatsApp", "Booked", booked_wa)

    return {
        "flows":            [{"from": a, "to": b, "flow": n} for (a, b), n in flows.items()],
        "total_taps":       wa_taps + book_taps,
        "wa_taps":          wa_taps,
        "book_taps":        book_taps,
        "booked_native":    booked_native,
        "booked_wa":        booked_wa,
        "sessions":         sum(web_ch.values()) + sum(links_ch.values()),
        # De-blackboxes the "Referral" node — top domains, rendered as a hover
        # tooltip on its legend swatch (see renderFunnelSankey in template.html).
        "referral_domains": referral_domains or {},
        "first_visits":  (kpis or {}).get("new_patients"),
    }


def build_payload() -> dict:
    """Fan all BQ queries out in parallel. ~27 queries; serial wall time was
    ~38s, parallel is limited by the slowest single query (~3-5s).

    BigQuery client is thread-safe; each fetch_* spawns its own job and
    blocks on .result() so threads sleep on I/O rather than spinning on the
    GIL. The thread pool is sized to comfortably cover all in-flight queries
    so nothing queues behind other work in this request.
    """
    log.info("Building dashboard payload from BigQuery (parallel)")
    today      = datetime.now(ZoneInfo("Asia/Singapore")).date()
    pmt_start  = today - timedelta(days=30)
    # Commission calculator needs the per-session ledger for the current
    # calendar month plus a generous trailing window so custom-range reports work.
    # 120 days covers ~4 calendar months.
    appt_start = today - timedelta(days=120)
    presets    = preset_ranges()

    # max_workers sized to cover every concurrent fetch this request fires:
    # 9 top-level + 4 ranges × 15 metrics + 3 ranges × 5 previous-window jobs = 84.
    # Round up to 70 for headroom.
    with ThreadPoolExecutor(max_workers=90, thread_name_prefix="bq") as ex:
        # Range-independent (or fixed-window) fetches.
        # fetch_deferred is now per-range (moved into range_jobs below).
        f_cohorts       = ex.submit(fetch_cohorts)
        f_demographics  = ex.submit(fetch_patient_demographics)
        f_referrals     = ex.submit(fetch_patient_referrals)
        f_payments      = ex.submit(fetch_payment_methods, pmt_start, today)
        f_appointments  = ex.submit(fetch_appointments, appt_start, today)
        f_mismatches    = ex.submit(fetch_invoice_doctor_mismatches)
        f_mismatch_hist = ex.submit(fetch_mismatch_history)
        f_projection    = ex.submit(fetch_monthly_projection, today)
        f_upcoming      = ex.submit(fetch_upcoming_sessions, today)

        # Per-range fetches. Each fetch_* is independent so they all race.
        range_jobs: dict[str, dict] = {}
        for key, label, start, end in presets:
            range_jobs[key] = {
                "label":          label,
                "start":          start.isoformat(),
                "end":            end.isoformat(),
                "kpis":           ex.submit(fetch_kpis, start, end),
                "trends":         ex.submit(fetch_trends, start, end),
                "weekly_visits":  ex.submit(fetch_weekly_visits, start, end),
                "clinicians":     ex.submit(fetch_clinicians, start, end),
                "discounts":      ex.submit(fetch_discounts, start, end),
                "treatment_mix":  ex.submit(fetch_treatment_mix, start, end),
                "packages":       ex.submit(fetch_packages, start, end),
                "deferred":       ex.submit(fetch_deferred, end),
                "link_clicks":    ex.submit(fetch_link_clicks, start, end),
                "booking_funnel": ex.submit(fetch_booking_funnel, start, end),
                "google_ads":     ex.submit(fetch_google_ads, start, end),
                "paid_funnel":    ex.submit(fetch_paid_funnel, start, end),
                "organic_search": ex.submit(fetch_organic_search, start, end),
                "instagram_reach": ex.submit(fetch_instagram_reach, start, end),
                "instagram_engagement": ex.submit(fetch_instagram_engagement, start, end),
                "web_sessions":   ex.submit(fetch_web_sessions, start, end),
                "web_channels":     ex.submit(fetch_web_channels, start, end),
                "web_pages":        ex.submit(fetch_web_pages, start, end),
                "referral_domains": ex.submit(fetch_referral_domains, start, end),
                "lead_wins":        ex.submit(fetch_lead_wins, start, end),
                "onsite_flow":      ex.submit(fetch_onsite_flow, start, end),
            }
            # Trend indicators compare each range against the immediately
            # preceding window of equal length (e.g. the 30 days before the
            # last 30). "All time" has no comparable prior window, so it gets
            # no previous-period KPIs.
            if key == "all":
                range_jobs[key]["prev_kpis"]         = None
                range_jobs[key]["link_clicks_prev"]  = None
                range_jobs[key]["google_ads_prev"]   = None
                range_jobs[key]["paid_funnel_prev"]  = None
                range_jobs[key]["organic_search_prev"] = None
                range_jobs[key]["instagram_reach_prev"] = None
                range_jobs[key]["instagram_engagement_prev"] = None
                range_jobs[key]["web_sessions_prev"] = None
                range_jobs[key]["prev_start"]        = None
                range_jobs[key]["prev_end"]          = None
            else:
                prev_end   = start - timedelta(days=1)
                prev_start = prev_end - (end - start)
                range_jobs[key]["prev_kpis"]         = ex.submit(fetch_kpis, prev_start, prev_end)
                range_jobs[key]["link_clicks_prev"]  = ex.submit(fetch_link_clicks, prev_start, prev_end)
                range_jobs[key]["google_ads_prev"]   = ex.submit(fetch_google_ads, prev_start, prev_end)
                range_jobs[key]["paid_funnel_prev"]  = ex.submit(fetch_paid_funnel, prev_start, prev_end)
                range_jobs[key]["organic_search_prev"] = ex.submit(fetch_organic_search, prev_start, prev_end)
                range_jobs[key]["instagram_reach_prev"] = ex.submit(fetch_instagram_reach, prev_start, prev_end)
                range_jobs[key]["instagram_engagement_prev"] = ex.submit(fetch_instagram_engagement, prev_start, prev_end)
                range_jobs[key]["web_sessions_prev"] = ex.submit(fetch_web_sessions, prev_start, prev_end)
                range_jobs[key]["prev_start"]        = prev_start.isoformat()
                range_jobs[key]["prev_end"]          = prev_end.isoformat()

        # Block on results. If any future raised, .result() re-raises here and
        # the still-running ones get cancelled when the executor exits.
        ranges: dict[str, dict] = {}
        for key, v in range_jobs.items():
            ranges[key] = {
                "label":            v["label"],
                "start":            v["start"],
                "end":              v["end"],
                "prev_start":       v["prev_start"],
                "prev_end":         v["prev_end"],
                "kpis":             v["kpis"].result(),
                "prev_kpis":        v["prev_kpis"].result() if v["prev_kpis"] else None,
                "trends":           v["trends"].result(),
                "weekly_visits":    v["weekly_visits"].result(),
                "clinicians":       v["clinicians"].result(),
                "discounts":        v["discounts"].result(),
                "treatment_mix":    v["treatment_mix"].result(),
                "packages":         v["packages"].result(),
                "deferred_stats":   v["deferred"].result(),
                "link_clicks":      v["link_clicks"].result(),
                "link_clicks_prev": v["link_clicks_prev"].result() if v["link_clicks_prev"] else None,
                "booking_funnel":   v["booking_funnel"].result(),
                "google_ads":       v["google_ads"].result(),
                "google_ads_prev":  v["google_ads_prev"].result() if v["google_ads_prev"] else None,
                "paid_funnel":      v["paid_funnel"].result(),
                "organic_search":      v["organic_search"].result(),
                "organic_search_prev": v["organic_search_prev"].result() if v["organic_search_prev"] else None,
                # Cost-per-booking: ad spend (US-region transfer) meets the
                # on-site outcome (marts). Assembled here because the two
                # sources can't be joined in one query.
                "paid_performance": _paid_performance(v["google_ads"].result(),
                                                      v["paid_funnel"].result()),
                "paid_performance_prev": (
                    _paid_performance(v["google_ads_prev"].result(),
                                      v["paid_funnel_prev"].result())
                    if v["google_ads_prev"] and v["paid_funnel_prev"] else None),
                "instagram_reach":      v["instagram_reach"].result(),
                "instagram_reach_prev": v["instagram_reach_prev"].result() if v["instagram_reach_prev"] else None,
                "instagram_engagement":      v["instagram_engagement"].result(),
                "instagram_engagement_prev": v["instagram_engagement_prev"].result() if v["instagram_engagement_prev"] else None,
                "web_sessions":      v["web_sessions"].result(),
                "web_sessions_prev": v["web_sessions_prev"].result() if v["web_sessions_prev"] else None,
                "web_pages":         v["web_pages"].result(),
                "onsite_flow":       v["onsite_flow"].result(),
                "funnel_paths":     _build_funnel_paths(v["link_clicks"].result(), v["kpis"].result(),
                                                        v["lead_wins"].result(),
                                                        v["web_channels"].result(),
                                                        v["booking_funnel"].result(),
                                                        v["referral_domains"].result()),
            }

        return {
            "generated_at":      datetime.now().astimezone().isoformat(timespec="seconds"),
            "default_range":     "30d",
            "cohorts":           f_cohorts.result(),
            "demographics":      f_demographics.result(),
            "referrals":         f_referrals.result(),
            "appointments":      f_appointments.result(),
            "payment_by_method": f_payments.result(),
            "ranges":            ranges,
            "doctor_mismatches": f_mismatches.result(),
            "mismatch_history":  f_mismatch_hist.result(),
            "projection":        f_projection.result(),
            "upcoming_sessions": f_upcoming.result(),
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


def fetch_active_patient_count() -> int:
    """Distinct patients with a delivered visit in the last 12 months."""
    sql = f"""
SELECT COUNT(DISTINCT patient_id) AS n
FROM `{PROJECT}.marts.fct_service_delivered`
WHERE patient_id IS NOT NULL
  AND delivery_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 365 DAY)
"""
    return _to_int(_query(sql)[0]["n"])


def fetch_patient_retention() -> dict:
    """Build the retention worklist: per-tier summary + a per-patient list.

    Tiers and future-appointment status come from marts.fct_patient_retention
    (PII-free). Follow-up state (contacted/snoozed/dismissed) comes from
    marts.patient_followup_latest. Full name + phone come from
    marts.dim_patient_contact (populated by the patients-ingest job) — no live
    Plato calls. A patient is "actionable" — i.e. needs a call — when they're
    yellow/orange/red, have no future appointment booked, and haven't been
    dismissed or snoozed.
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
  c.full_name    AS full_name,
  c.phone        AS phone,
  f.status       AS followup_status,
  f.snooze_until AS followup_snooze_until,
  f.note         AS followup_note,
  f.updated_at   AS followup_at,
  f.updated_by   AS followup_by
FROM `{PROJECT}.marts.fct_patient_retention` r
LEFT JOIN `{PROJECT}.marts.dim_patient_contact`     c USING (patient_id)
LEFT JOIN `{PROJECT}.marts.patient_followup_latest` f USING (patient_id)
"""
    rows = _query(sql)
    today = date.today()
    summary = {
        "total": 0, "green": 0, "yellow": 0, "orange": 0, "red": 0,
        "needs_followup": 0, "already_booked": 0, "snoozed": 0, "dismissed": 0,
        "active_12m": fetch_active_patient_count(),
    }
    patients: list[dict] = []

    for r in rows:
        tier   = r["tier"]
        status = r.get("followup_status")
        snooze_until = r.get("followup_snooze_until")
        has_future   = bool(r["has_future_appt"])

        summary["total"] += 1
        # Green is a healthy/context total. The red/orange/yellow card counts
        # are deliberately the *actionable* ("to call") numbers — incremented
        # below — so that red + orange + yellow == needs_followup and the cards
        # visibly tally.
        if tier == "green":
            summary["green"] += 1
        if has_future:
            summary["already_booked"] += 1
        if status == "dismissed":
            summary["dismissed"] += 1
        if is_snoozed(status, snooze_until, today):
            summary["snoozed"] += 1

        actionable = is_actionable(tier, has_future, status, snooze_until, today)
        if actionable:
            summary["needs_followup"] += 1
            summary[tier] += 1  # red/orange/yellow, actionable-only

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
            # Full name from the contact table; fall back to PII-safe initials.
            "name":             r.get("full_name") or r.get("initial_lastname") or "—",
            "phone":            r.get("phone"),
            "followup_status":  status,
            "followup_note":    r.get("followup_note"),
            "snooze_until":     snooze_until.isoformat() if snooze_until else None,
            "actionable":       actionable,
        })

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

    The cache key is invalidated when a follow-up action is recorded so the
    worklist reflects it on reload.
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


def get_frontdesk_shell_html() -> str:
    """Return the Front Desk portal HTML. No BQ work; the page fetches its data
    from /api/frontdesk/*."""
    return ADMIN_TEMPLATE.read_text()


def record_followup(patient_id: str, status: str, *, note: str | None = None,
                    snooze_days: int | None = None,
                    updated_by: str | None = None) -> None:
    """Append one follow-up event (append-only; latest wins). Snoozing without
    an explicit duration defaults to one week.

    Uses a parameterised DML INSERT (a query job), NOT a load job: query/DML
    writes honour the dashboard SA's *table-level* dataEditor grant on
    patient_followup_events, whereas load jobs effectively need dataset-level
    write. This keeps least-privilege (no broad write on the marts dataset) and
    is immediately visible to patient_followup_latest. Parameters avoid any
    injection from the free-text note.
    """
    snooze_until: date | None = None
    if status == "snoozed":
        days = snooze_days if isinstance(snooze_days, int) and snooze_days > 0 else DEFAULT_SNOOZE_DAYS
        snooze_until = date.today() + timedelta(days=days)

    sql = f"""
INSERT INTO `{PROJECT}.marts.patient_followup_events`
  (event_id, patient_id, status, note, snooze_until, updated_by, updated_at)
VALUES
  (@event_id, @patient_id, @status, @note, @snooze_until, @updated_by, CURRENT_TIMESTAMP())
"""
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("event_id",   "STRING", str(uuid.uuid4())),
        bigquery.ScalarQueryParameter("patient_id", "STRING", patient_id),
        bigquery.ScalarQueryParameter("status",     "STRING", status),
        bigquery.ScalarQueryParameter("note",       "STRING", (note or None)),
        bigquery.ScalarQueryParameter("snooze_until", "DATE", snooze_until),
        bigquery.ScalarQueryParameter("updated_by", "STRING", updated_by),
    ])
    _bq().query(sql, job_config=job_config).result()
    with _cache_lock:
        _cache.pop("retention", None)


# Front-desk portal: package alerts ------------------------------------------
#
# The worklists Plato doesn't give you. Package Alerts reads
# marts.fct_package_balance (PII-free) and hydrates name + phone live from
# marts.dim_patient_contact at render time — the same boundary as the retention
# worklist. (Today's schedule / call list used to live here too; they mirrored
# Plato's own calendar, so they were removed — the team works appointments in
# Plato directly.)

# Patients with this many prepaid sessions left (or fewer) show on Package
# Alerts. 0 first — they've run out and most urgently need a renewal call.
PACKAGE_ALERT_THRESHOLD = 2


def _clinician_name(clinician_id: str | None) -> str:
    return PROVIDERS.get(clinician_id, clinician_id or "—")


def fetch_package_alerts() -> dict:
    """Patients with PACKAGE_ALERT_THRESHOLD or fewer prepaid sessions left.

    Sorted by urgency: fewest sessions first (0 = ran out), then most-recently
    seen first so the front desk reaches people still in the habit of coming in.
    sessions_remaining is NULL for patients whose pack size we can't read from
    the SKU; those are excluded by fct_package_balance's filter here, so we
    never raise a false 'about to run out' alarm.
    """
    sql = f"""
SELECT
  pb.patient_id,
  pb.sessions_remaining,
  pb.last_visit_date,
  p.initial_lastname,
  p.age_band,
  p.primary_doctor,
  c.full_name AS full_name,
  c.phone     AS phone
FROM `{PROJECT}.marts.fct_package_balance` pb
LEFT JOIN `{PROJECT}.marts.dim_patient`         p USING (patient_id)
LEFT JOIN `{PROJECT}.marts.dim_patient_contact` c USING (patient_id)
WHERE pb.sessions_remaining IS NOT NULL
  AND pb.sessions_remaining <= {PACKAGE_ALERT_THRESHOLD}
ORDER BY pb.sessions_remaining ASC, pb.last_visit_date DESC
"""
    patients = [{
        "patient_id":         r["patient_id"],
        "sessions_remaining": _to_int(r["sessions_remaining"]),
        "last_visit":         r["last_visit_date"].isoformat() if r["last_visit_date"] else None,
        "clinician":          _clinician_name(r["primary_doctor"]),
        "name":               r.get("full_name") or r.get("initial_lastname") or "—",
        "phone":              r.get("phone"),
        "age_band":           r["age_band"],
    } for r in _query(sql)]
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "patients":     patients,
    }


def get_package_alerts() -> dict:
    """Cached accessor for the package-alerts list (same TTL as the rest)."""
    now = time.time()
    with _cache_lock:
        entry = _cache.get("package_alerts")
        if entry and now - entry[0] < CACHE_TTL:
            return entry[1]
    data = fetch_package_alerts()
    with _cache_lock:
        _cache["package_alerts"] = (now, data)
    return data


# Front-desk portal: new-patient welcome worklist ----------------------------
#
# The FIRST tab: patients whose first visit is coming up, so the front desk can
# message them directions / arrival info before they turn up. A worklist Plato
# doesn't track — not a schedule mirror. Reads marts.fct_new_patient_welcome
# (PII-free) and hydrates name/phone/email live at render time; write state
# (contacted / skipped) goes to marts.new_patient_welcome_events.
#
# Contact hydration fallback chain — the crux of "new bookings with no profile
# yet": a profile-less website/walk-in booking carries its own handphone/email/
# name inside the appointment payload, so we read those straight from
# stg.appointments (keyed on appointment_id) and only fall back to
# dim_patient_contact for patients who already have a Plato profile. Contact is
# never stored in the mart — same PII boundary as the other worklists, with the
# appointment payload as the profile-less exception (like lead_events).

VALID_WELCOME_STATUSES = {"contacted", "skipped", "active"}

# Default view window (hours ahead) for the welcome list; the UI can widen it to
# the whole week. The mart already caps the horizon at 30 days.
WELCOME_DEFAULT_HOURS = 48


def fetch_new_patient_welcome() -> dict:
    """Upcoming first-visit patients + a per-booking worklist.

    Rows come from marts.fct_new_patient_welcome (PII-free). Already-handled
    bookings (contacted / skipped) are dropped via
    marts.new_patient_welcome_latest. Name/phone/email are hydrated at render:
    inline from the appointment payload for profile-less bookings, else from
    marts.dim_patient_contact for linked patients.
    """
    sql = f"""
SELECT
  w.appointment_id,
  w.patient_id,
  w.appt_datetime,
  w.appt_date,
  w.clinician_id,
  w.treatment_type,
  w.booking_source,
  w.has_profile,
  -- Inline contact from the appointment payload (profile-less bookings carry it).
  JSON_VALUE(a.payload, '$.title')     AS appt_title,
  JSON_VALUE(a.payload, '$.handphone') AS appt_phone,
  JSON_VALUE(a.payload, '$.email')     AS appt_email,
  -- Profile contact for linked patients.
  c.full_name AS profile_name,
  c.phone     AS profile_phone,
  e.status    AS welcome_status
FROM `{PROJECT}.marts.fct_new_patient_welcome` w
LEFT JOIN `{PROJECT}.stg.appointments`             a USING (appointment_id)
LEFT JOIN `{PROJECT}.marts.dim_patient_contact`    c ON w.patient_id = c.patient_id
LEFT JOIN `{PROJECT}.marts.new_patient_welcome_latest` e USING (appointment_id)
ORDER BY w.appt_datetime
"""
    patients: list[dict] = []
    for r in _query(sql):
        status = r.get("welcome_status")
        # Keep contacted / skipped rows on the list (marked done) so the front
        # desk can see what's been handled; only 'active' (undo) or no event is
        # still outstanding. Rows age off naturally once the appointment passes.
        name  = r.get("profile_name")  or r.get("appt_title") or "—"
        phone = (r.get("appt_phone") or "").strip() or r.get("profile_phone")
        email = (r.get("appt_email") or "").strip() or None
        patients.append({
            "appointment_id": r["appointment_id"],
            "appt_datetime":  r["appt_datetime"].isoformat() if r["appt_datetime"] else None,
            "clinician":      _clinician_name(r["clinician_id"]),
            "treatment_type": r["treatment_type"],
            "booking_source": r["booking_source"],
            "has_profile":    bool(r["has_profile"]),
            "name":           name,
            "phone":          phone,
            "email":          email,
            # 'contacted' | 'skipped' | 'active' | None (never actioned).
            "welcome_status": status if status in ("contacted", "skipped") else None,
        })
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "patients":     patients,
    }


def get_new_patient_welcome() -> dict:
    """Cached accessor for the welcome worklist (invalidated on a write)."""
    now = time.time()
    with _cache_lock:
        entry = _cache.get("welcome")
        if entry and now - entry[0] < CACHE_TTL:
            return entry[1]
    data = fetch_new_patient_welcome()
    with _cache_lock:
        _cache["welcome"] = (now, data)
    return data


def record_welcome_contacted(appointment_id: str, status: str, *,
                             note: str | None = None,
                             updated_by: str | None = None) -> None:
    """Append one welcome-list event (append-only; latest wins).

    Parameterised DML INSERT (a query job), honouring the dashboard SA's
    table-level dataEditor grant on new_patient_welcome_events — same pattern as
    record_followup. Keyed on appointment_id (profile-less bookings have no
    patient_id).
    """
    sql = f"""
INSERT INTO `{PROJECT}.marts.new_patient_welcome_events`
  (event_id, appointment_id, status, note, updated_by, updated_at)
VALUES
  (@event_id, @appointment_id, @status, @note, @updated_by, CURRENT_TIMESTAMP())
"""
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("event_id",       "STRING", str(uuid.uuid4())),
        bigquery.ScalarQueryParameter("appointment_id", "STRING", appointment_id),
        bigquery.ScalarQueryParameter("status",         "STRING", status),
        bigquery.ScalarQueryParameter("note",           "STRING", (note or None)),
        bigquery.ScalarQueryParameter("updated_by",     "STRING", updated_by),
    ])
    _bq().query(sql, job_config=job_config).result()
    with _cache_lock:
        _cache.pop("welcome", None)


# Front-desk portal: inbound-lead pipeline -----------------------------------
#
# The "Leads" tab: inbound WhatsApp/Instagram/etc. inquiries tracked through the
# funnel (inquiry -> qualified -> booked -> won, or lost). The single source of
# truth for inbound inquiries — a contact key plus explicit stages. "won" = the
# lead became a paying patient / customer (their first visit), NOT that they
# bought a package; packages are a separate worklist. Reads/writes
# marts.lead_events (+ marts.lead_latest).

# Funnel stages and the inbound channels we tag (reuse the LINK_SLUGS channel
# vocabulary). OPEN_LEAD_STAGES = still in play (neither won nor lost).
VALID_LEAD_STAGES   = {"inquiry", "qualified", "booked", "won", "lost"}
OPEN_LEAD_STAGES    = {"inquiry", "qualified", "booked"}
VALID_LEAD_CHANNELS = {"whatsapp", "instagram", "google", "referral",
                       "walk_in", "form", "call", "other"}
# Worklist sort: open leads first, then progress order, then newest first.
_LEAD_STAGE_RANK = {"inquiry": 0, "qualified": 1, "booked": 2, "won": 3, "lost": 4}


def fetch_leads() -> dict:
    """Build the leads pipeline: a funnel summary + the per-lead list.

    Current state per lead comes from marts.lead_latest (latest event wins).
    Unlike the patient worklists, `contact` lives on the lead itself (a
    pre-patient isn't in Plato to hydrate from) — see the PII note in
    marts/46_lead_events.sql.
    """
    sql = f"""
SELECT lead_id, name, contact, channel, stage, lost_reason, note,
       updated_by, updated_at, first_seen
FROM `{PROJECT}.marts.lead_latest`
"""
    rows = _query(sql)
    summary = {"total": 0, "open": 0, "booked": 0, "won": 0, "lost": 0,
               "close_rate": 0.0, "by_channel": {}}
    leads: list[dict] = []

    for r in rows:
        stage   = r["stage"]
        channel = r.get("channel") or "other"
        summary["total"] += 1
        if stage in OPEN_LEAD_STAGES:
            bucket = "open"
        elif stage == "won":
            bucket = "won"
        else:
            bucket = "lost"
        summary[bucket] += 1
        if stage == "booked":          # a hot subset of "open": about to convert
            summary["booked"] += 1
        ch = summary["by_channel"].setdefault(
            channel, {"total": 0, "open": 0, "won": 0, "lost": 0})
        ch["total"] += 1
        ch[bucket]  += 1

        leads.append({
            "lead_id":     r["lead_id"],
            "name":        r.get("name"),
            "contact":     r.get("contact"),
            "channel":     channel,
            "stage":       stage,
            "lost_reason": r.get("lost_reason"),
            "note":        r.get("note"),
            "first_seen":  r["first_seen"].isoformat() if r.get("first_seen") else None,
            "updated_at":  r["updated_at"].isoformat() if r.get("updated_at") else None,
        })

    closed = summary["won"] + summary["lost"]
    summary["close_rate"] = round(summary["won"] / closed, 3) if closed else 0.0

    # Most-actionable first: open leads before closed, then by stage progress,
    # then newest inquiry first.
    leads.sort(key=lambda x: (
        _LEAD_STAGE_RANK.get(x["stage"], 9),
        x["first_seen"] or "",
    ), reverse=False)
    leads.sort(key=lambda x: x["first_seen"] or "", reverse=True)
    leads.sort(key=lambda x: 0 if x["stage"] in OPEN_LEAD_STAGES else 1)

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "summary":      summary,
        "leads":        leads,
    }


def get_leads() -> dict:
    """Cached accessor for the leads pipeline (same TTL as the rest). The cache
    is invalidated when a lead event is recorded."""
    now = time.time()
    with _cache_lock:
        entry = _cache.get("leads")
        if entry and now - entry[0] < CACHE_TTL:
            return entry[1]
    data = fetch_leads()
    with _cache_lock:
        _cache["leads"] = (now, data)
    return data


def record_lead(lead_id: str, stage: str, *, name: str | None = None,
                contact: str | None = None, channel: str | None = None,
                note: str | None = None, lost_reason: str | None = None,
                updated_by: str | None = None) -> None:
    """Append one lead event (append-only; latest wins).

    Same parameterised DML-INSERT pattern as record_followup: honours the
    dashboard SA's table-level dataEditor grant on lead_events (least-privilege,
    no dataset-wide write). Each write carries the lead's full current snapshot
    (contact + channel + note) so the latest row is self-sufficient for display.
    Pops the leads cache so the worklist reflects it on reload.
    """
    sql = f"""
INSERT INTO `{PROJECT}.marts.lead_events`
  (event_id, lead_id, name, contact, channel, stage, lost_reason, note, updated_by, updated_at)
VALUES
  (@event_id, @lead_id, @name, @contact, @channel, @stage, @lost_reason, @note, @updated_by, CURRENT_TIMESTAMP())
"""
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("event_id",    "STRING", str(uuid.uuid4())),
        bigquery.ScalarQueryParameter("lead_id",     "STRING", lead_id),
        bigquery.ScalarQueryParameter("name",        "STRING", (name or None)),
        bigquery.ScalarQueryParameter("contact",     "STRING", (contact or None)),
        bigquery.ScalarQueryParameter("channel",     "STRING", (channel or None)),
        bigquery.ScalarQueryParameter("stage",       "STRING", stage),
        bigquery.ScalarQueryParameter("lost_reason", "STRING", (lost_reason or None)),
        bigquery.ScalarQueryParameter("note",        "STRING", (note or None)),
        bigquery.ScalarQueryParameter("updated_by",  "STRING", updated_by),
    ])
    _bq().query(sql, job_config=job_config).result()
    with _cache_lock:
        _cache.pop("leads", None)


def record_mismatch_dismissal(invoice_id: str, action: str, *,
                              reason: str | None = None,
                              snapshot: dict | None = None,
                              updated_by: str | None = None) -> None:
    """Append one provider-attribution alert dismissal/restore event.

    Append-only; latest action per invoice_id wins (mismatch_dismissal_latest).
    Same parameterised DML-INSERT pattern as record_followup / record_lead —
    honours the dashboard SA's table-level dataEditor grant on
    mismatch_dismissal_events (least-privilege). The client passes the alert
    snapshot it already has in
    hand so the Alert-history tab can render the row even after the invoice falls
    out of the mismatch window. Pops the founder payload cache so both the live
    alert list and the history tab reflect it on the next reload.
    """
    s = snapshot or {}
    sql = f"""
INSERT INTO `{PROJECT}.marts.mismatch_dismissal_events`
  (event_id, invoice_id, action, reason, invoice_label, invoice_date, patient,
   invoice_doctor, appt_doctors, total, created_by, last_edited_by,
   updated_by, updated_at)
VALUES
  (@event_id, @invoice_id, @action, @reason, @invoice_label, @invoice_date, @patient,
   @invoice_doctor, @appt_doctors, @total, @created_by, @last_edited_by,
   @updated_by, CURRENT_TIMESTAMP())
"""
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("event_id",       "STRING",  str(uuid.uuid4())),
        bigquery.ScalarQueryParameter("invoice_id",     "STRING",  invoice_id),
        bigquery.ScalarQueryParameter("action",         "STRING",  action),
        bigquery.ScalarQueryParameter("reason",         "STRING",  (reason or None)),
        bigquery.ScalarQueryParameter("invoice_label",  "STRING",  (s.get("invoice_no") or None)),
        bigquery.ScalarQueryParameter("invoice_date",   "DATE",    (s.get("date") or None)),
        bigquery.ScalarQueryParameter("patient",        "STRING",  (s.get("patient") or None)),
        bigquery.ScalarQueryParameter("invoice_doctor", "STRING",  (s.get("invoice_doctor") or None)),
        bigquery.ScalarQueryParameter("appt_doctors",   "STRING",  (s.get("appt_doctors") or None)),
        bigquery.ScalarQueryParameter("total",          "NUMERIC",
                                      (str(s["total"]) if s.get("total") is not None else None)),
        bigquery.ScalarQueryParameter("created_by",     "STRING",  (s.get("created_by") or None)),
        bigquery.ScalarQueryParameter("last_edited_by", "STRING",  (s.get("last_edited_by") or None)),
        bigquery.ScalarQueryParameter("updated_by",     "STRING",  updated_by),
    ])
    _bq().query(sql, job_config=job_config).result()
    with _cache_lock:
        _cache.pop("payload", None)


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

    'founder' -> full access (financial dashboard + admin).
    'staff'   -> admin/frontdesk section only; never satisfies founder routes.
    All configured staff credential pairs are checked so timing doesn't leak
    whether the founder credential exists.
    """
    is_founder = _creds_match(user, password, AUTH_USER, AUTH_PASS)
    if is_founder:
        return "founder"
    is_staff = any(_creds_match(user, password, u, p) for u, p in STAFF_CREDS)
    if is_staff:
        return "staff"
    return None


def require_roles(*roles: str, only_mode: str | None = None):
    """Gate a route to the given roles.

    A credential for a role NOT in `roles` gets a 401 — this is what keeps a
    staff login out of the founder-only financial routes entirely.

    Subdomain pinning keeps the two surfaces cleanly separated — there are
    exactly two ways in, and neither leaks the other's routes:
      - founder-only routes don't exist on the frontdesk subdomain
        (APP_MODE='frontdesk'), so frontdesk.* never exposes financial data
        regardless of credentials;
      - `only_mode="frontdesk"` pins the patient-ops routes to the frontdesk
        subdomain, so the ops portal is NOT reachable on dashboard.* at all.
    Both return 404 (not 401) on the wrong subdomain: the route simply does not
    exist there.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from flask import abort
            # The links subdomain is a public redirect surface only — no
            # authenticated route exists there at all.
            if APP_MODE == "links":
                abort(404)
            # Routes pinned to one subdomain don't exist on the other.
            if only_mode is not None and APP_MODE != only_mode:
                abort(404)
            # On the frontdesk subdomain, founder-only routes don't exist.
            if APP_MODE == "frontdesk" and roles == ("founder",):
                abort(404)
            auth = request.authorization
            role = resolve_role(auth.username or "", auth.password or "") if auth else None
            if role is None or role not in roles:
                realm = "Goji Front Desk" if APP_MODE == "frontdesk" else "Goji Dashboard"
                return Response(
                    "Authentication required.",
                    401,
                    {"WWW-Authenticate": f'Basic realm="{realm}"'},
                )
            g.role = role
            g.user = (auth.username or "") if auth else ""
            return f(*args, **kwargs)
        return wrapper
    return decorator


@app.route("/")
def index() -> Response:
    """Root route — each subdomain serves its own portal at /, no extra path:

    - 'frontdesk': the Front Desk patient-ops portal (founder + staff). The
      subdomain already says "front desk", so there's no redundant /frontdesk.
    - 'dashboard' (default): the founder financial dashboard (founder-only).
    - 'links': no UI — bounce the bare root to the marketing site.
    """
    if APP_MODE == "links":
        return redirect(WHATSAPP_FALLBACK_URL, code=302)
    if APP_MODE == "frontdesk":
        auth = request.authorization
        role = resolve_role(auth.username or "", auth.password or "") if auth else None
        if role not in ("founder", "staff"):
            return Response(
                "Authentication required.",
                401,
                {"WWW-Authenticate": 'Basic realm="Goji Front Desk"'},
            )
        g.role = role
        g.user = (auth.username or "") if auth else ""
        return Response(get_frontdesk_shell_html(), mimetype="text/html")
    # dashboard mode: enforce founder-only
    auth = request.authorization
    role = resolve_role(auth.username or "", auth.password or "") if auth else None
    if role != "founder":
        return Response(
            "Authentication required.",
            401,
            {"WWW-Authenticate": 'Basic realm="Goji Dashboard"'},
        )
    g.role = role
    g.user = (auth.username or "") if auth else ""
    return Response(get_shell_html(), mimetype="text/html")


@app.route("/api/data")
@require_roles("founder")
def api_data() -> Response:
    return Response(json.dumps(get_payload()), mimetype="application/json")


@app.route("/api/range")
@require_roles("founder")
def api_range() -> Response:
    """Return a single range dict for an arbitrary [start, end] window.

    Used by the Custom date-range picker in the dashboard. Returns data in the
    same shape as one entry from DATA.ranges so the existing render functions
    work without modification, including a previous-period comparison of equal
    length so trend tickers render.
    """
    start = _parse_iso_date(request.args.get("start"))
    end   = _parse_iso_date(request.args.get("end"))
    if not start or not end or start > end or (end - start).days > 366:
        return Response(json.dumps({"error": "invalid range"}), status=400,
                        mimetype="application/json")

    prev_end   = start - timedelta(days=1)
    prev_start = prev_end - (end - start)

    log.info("Custom range query %s -> %s", start, end)
    with ThreadPoolExecutor(max_workers=20, thread_name_prefix="bq_custom") as ex:
        f_kpis      = ex.submit(fetch_kpis,          start,      end)
        f_prev_kpis = ex.submit(fetch_kpis,          prev_start, prev_end)
        f_tr        = ex.submit(fetch_trends,        start,      end)
        f_wv        = ex.submit(fetch_weekly_visits, start,      end)
        f_clin      = ex.submit(fetch_clinicians,    start,      end)
        f_disc      = ex.submit(fetch_discounts,     start,      end)
        f_mix       = ex.submit(fetch_treatment_mix, start,      end)
        f_pkgs      = ex.submit(fetch_packages,      start,      end)
        f_lc        = ex.submit(fetch_link_clicks,   start,      end)
        f_lc_prev   = ex.submit(fetch_link_clicks,   prev_start, prev_end)
        f_ga        = ex.submit(fetch_google_ads,    start,      end)
        f_ga_prev   = ex.submit(fetch_google_ads,    prev_start, prev_end)

    result = {
        "label":            "Custom",
        "start":            start.isoformat(),
        "end":              end.isoformat(),
        "prev_start":       prev_start.isoformat(),
        "prev_end":         prev_end.isoformat(),
        "kpis":             f_kpis.result(),
        "prev_kpis":        f_prev_kpis.result(),
        "trends":           f_tr.result(),
        "weekly_visits":    f_wv.result(),
        "clinicians":       f_clin.result(),
        "discounts":        f_disc.result(),
        "treatment_mix":    f_mix.result(),
        "packages":         f_pkgs.result(),
        "link_clicks":      f_lc.result(),
        "link_clicks_prev": f_lc_prev.result(),
        "google_ads":       f_ga.result(),
        "google_ads_prev":  f_ga_prev.result(),
    }
    return Response(json.dumps(result), mimetype="application/json")


@app.route("/api/mismatch/dismiss", methods=["POST"])
@require_roles("founder")
def api_mismatch_dismiss() -> Response:
    """Dismiss or restore provider-attribution alerts (persistent, server-side).

    Body: {action, reason?, items:[{invoice_id, invoice_no?, date?, patient?,
    invoice_doctor?, appt_doctors?, total?, created_by?, last_edited_by?}, ...]}.
    action is 'dismiss' (hide the live alert) or 'restore' (un-dismiss — it
    reappears if the invoice still mismatches). Each item carries the snapshot the
    front end already rendered so the Alert-history tab can show the row later.
    Appends one event per item; the latest action per invoice wins. Handles both
    a single row and "Dismiss all" (multiple items) in one request.
    """
    body   = request.get_json(silent=True) or {}
    action = (body.get("action") or "dismiss").strip().lower()
    if action not in ("dismiss", "restore"):
        return Response('{"error": "action must be dismiss or restore"}',
                        status=400, mimetype="application/json")
    stored = "dismissed" if action == "dismiss" else "restored"
    reason = body.get("reason")
    reason = str(reason).strip() if reason else None
    items  = body.get("items")
    if not isinstance(items, list) or not items:
        return Response('{"error": "items[] with at least one invoice_id is required"}',
                        status=400, mimetype="application/json")
    rows = [it for it in items
            if isinstance(it, dict) and (it.get("invoice_id") or "").strip()]
    if not rows:
        return Response('{"error": "each item needs an invoice_id"}',
                        status=400, mimetype="application/json")
    try:
        for it in rows:
            record_mismatch_dismissal((it.get("invoice_id") or "").strip(), stored,
                                      reason=reason, snapshot=it,
                                      updated_by=getattr(g, "user", None))
    except Exception as e:
        log.exception("mismatch dismissal write failed: %s", e)
        msg = str(e).lower()
        if "permission" in msg or "denied" in msg or "403" in msg or "access" in msg:
            return Response(
                json.dumps({"error": "The dashboard isn't allowed to save yet — its "
                            "service account needs write access to "
                            "marts.mismatch_dismissal_events. See DEPLOY.md."}),
                status=403, mimetype="application/json")
        return Response('{"error": "Could not save — please try again."}',
                        status=500, mimetype="application/json")
    return Response('{"ok": true}', mimetype="application/json")


@app.route("/api/pl_window")
@require_roles("founder")
def api_pl_window() -> Response:
    """Recompute the P&L revenue + payment fees for an arbitrary date window.

    Used by the P&L tab's date selector ("Last 30D" / "This month" / "Custom").
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
        _cache.pop("upcoming", None)
        _cache.pop("package_alerts", None)
    if DEV_MODE and CACHE_DIR.exists():
        for f in CACHE_DIR.glob("*.json"):
            f.unlink()
    return Response('{"ok": true}', mimetype="application/json")


# Patient-ops portal (the "Front Desk") is served at / on the frontdesk
# subdomain — see index(). The /api/frontdesk/* data routes below are pinned to
# that subdomain with only_mode="frontdesk" so they 404 on the founder
# dashboard. The legacy /api/admin/* paths are kept as aliases (same handlers)
# so any cached page keeps working through the rename.
@app.route("/admin")
def legacy_admin_redirect() -> Response:
    """Deprecated path. The ops portal used to live at /admin; it now lives at /
    on the frontdesk subdomain. Redirect old bookmarks there (and 404 on the
    dashboard subdomain, where the portal isn't served at all)."""
    from flask import abort, redirect
    if APP_MODE != "frontdesk":
        abort(404)
    return redirect("/", code=301)


@app.route("/api/frontdesk/retention")
@app.route("/api/admin/retention")  # legacy alias
@require_roles("founder", "staff", only_mode="frontdesk")
def api_frontdesk_retention() -> Response:
    """Patient retention worklist: tier summary + per-patient call list."""
    return Response(json.dumps(get_retention(), default=str),
                    mimetype="application/json")


@app.route("/api/frontdesk/followup", methods=["POST"])
@app.route("/api/admin/followup", methods=["POST"])  # legacy alias
@require_roles("founder", "staff", only_mode="frontdesk")
def api_frontdesk_followup() -> Response:
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
        msg = str(e).lower()
        if "permission" in msg or "denied" in msg or "403" in msg or "access" in msg:
            return Response(
                json.dumps({"error": "The dashboard isn't allowed to save yet — its "
                            "service account needs write access to "
                            "marts.patient_followup_events. See DEPLOY.md."}),
                status=403, mimetype="application/json")
        return Response('{"error": "Could not save — please try again."}',
                        status=500, mimetype="application/json")
    return Response('{"ok": true}', mimetype="application/json")


@app.route("/api/frontdesk/leads")
@require_roles("founder", "staff", only_mode="frontdesk")
def api_frontdesk_leads() -> Response:
    """Inbound-lead pipeline: funnel summary + the per-lead worklist."""
    return Response(json.dumps(get_leads(), default=str),
                    mimetype="application/json")


@app.route("/api/frontdesk/leads", methods=["POST"])
@require_roles("founder", "staff", only_mode="frontdesk")
def api_frontdesk_leads_save() -> Response:
    """Capture a lead or advance its stage.

    Body: {lead_id, stage, name?, contact?, channel?, note?, lost_reason?}.
    Appends one event row carrying the lead's current snapshot; the pipeline
    reflects it on the next reload. lead_id is the id the front end mints on
    capture. name is optional; contact stays the identity/dedup key.
    """
    body    = request.get_json(silent=True) or {}
    lead_id = (body.get("lead_id") or "").strip()
    stage   = (body.get("stage") or "").strip()
    channel = (body.get("channel") or "").strip().lower() or None
    if not lead_id or stage not in VALID_LEAD_STAGES:
        return Response('{"error": "lead_id and a valid stage are required"}',
                        status=400, mimetype="application/json")
    if channel is not None and channel not in VALID_LEAD_CHANNELS:
        return Response('{"error": "unknown channel"}',
                        status=400, mimetype="application/json")
    try:
        record_lead(lead_id, stage,
                    name=(body.get("name") or None),
                    contact=(body.get("contact") or None),
                    channel=channel,
                    note=(body.get("note") or None),
                    lost_reason=(body.get("lost_reason") or None),
                    updated_by=getattr(g, "user", None))
    except Exception as e:
        log.exception("lead write failed: %s", e)
        msg = str(e).lower()
        if "permission" in msg or "denied" in msg or "403" in msg or "access" in msg:
            return Response(
                json.dumps({"error": "The dashboard isn't allowed to save yet — its "
                            "service account needs write access to "
                            "marts.lead_events. See DEPLOY.md."}),
                status=403, mimetype="application/json")
        return Response('{"error": "Could not save — please try again."}',
                        status=500, mimetype="application/json")
    return Response('{"ok": true}', mimetype="application/json")


@app.route("/api/frontdesk/package_alerts")
@app.route("/api/admin/package_alerts")  # legacy alias
@require_roles("founder", "staff", only_mode="frontdesk")
def api_frontdesk_package_alerts() -> Response:
    """Patients with <=2 prepaid sessions left, most urgent (0) first."""
    return Response(json.dumps(get_package_alerts(), default=str),
                    mimetype="application/json")


@app.route("/api/frontdesk/new_patients")
@require_roles("founder", "staff", only_mode="frontdesk")
def api_frontdesk_new_patients() -> Response:
    """New-patient welcome worklist: upcoming first visits to reach out to."""
    return Response(json.dumps(get_new_patient_welcome(), default=str),
                    mimetype="application/json")


@app.route("/api/frontdesk/new_patients", methods=["POST"])
@require_roles("founder", "staff", only_mode="frontdesk")
def api_frontdesk_new_patients_save() -> Response:
    """Mark an upcoming new patient contacted / skipped (or restore to the list).

    Body: {appointment_id, status, note?}. Appends one event row; the worklist
    reflects it on the next reload.
    """
    body   = request.get_json(silent=True) or {}
    appt   = (body.get("appointment_id") or "").strip()
    status = (body.get("status") or "").strip()
    if not appt or status not in VALID_WELCOME_STATUSES:
        return Response('{"error": "appointment_id and a valid status are required"}',
                        status=400, mimetype="application/json")
    try:
        record_welcome_contacted(appt, status, note=body.get("note"),
                                 updated_by=getattr(g, "user", None))
    except Exception as e:
        log.exception("welcome write failed: %s", e)
        msg = str(e).lower()
        if "permission" in msg or "denied" in msg or "403" in msg or "access" in msg:
            return Response(
                json.dumps({"error": "The dashboard isn't allowed to save yet — its "
                            "service account needs write access to "
                            "marts.new_patient_welcome_events. See DEPLOY.md."}),
                status=403, mimetype="application/json")
        return Response('{"error": "Could not save — please try again."}',
                        status=500, mimetype="application/json")
    return Response('{"ok": true}', mimetype="application/json")


def _slug_target(slug: str, click_id: str | None = None) -> str:
    """Resolve a slug to its redirect destination. Never dead-ends: an unknown
    or not-yet-configured target falls back to the marketing site.

    For `book` slugs (which land on our own /book form — this includes retired
    `*-plato` slugs, now aliased here) we append the go-link's click_id as
    `?cid=` plus `?src=<slug>`, so the site's landing beacon can record them on
    web_session_events — that's the exact join back to this click
    (link_click_events.click_id) and the origin→booking attribution chain.
    WhatsApp targets are external, so the passthrough doesn't apply there.

    For `pay` slugs the click_id rides to Stripe as `client_reference_id`, which
    Stripe stores on the Checkout Session: the exact join from a purchase back
    to this click."""
    cfg = LINK_SLUGS.get(slug)
    if not cfg:
        return WHATSAPP_FALLBACK_URL
    if cfg["kind"] == "pay":
        url = SHOP_PAY_URLS.get(cfg["item"])
        if not url:
            return SHOP_FALLBACK_URL
        return f"{url}?client_reference_id={click_id}" if click_id else url
    if cfg["kind"] == "book":
        base = SITE_BOOKING_URL or WHATSAPP_FALLBACK_URL
        if click_id and base:
            sep = "&" if "?" in base else "?"
            return f"{base}{sep}cid={click_id}&src={slug}"
        return base
    if WHATSAPP_NUMBER:  # whatsapp
        return f"https://wa.me/{WHATSAPP_NUMBER}?text={quote(cfg.get('text', ''))}"
    return WHATSAPP_FALLBACK_URL


@app.route("/r/<slug>")
def tracked_redirect(slug: str):
    """PUBLIC (no @require_roles): trackable CTA redirect.

    Every channel's outbound CTA — website button, IG/socials bio link, GBP
    link, ad destinations, email signature, printed QR codes — points here. We
    log the click (best-effort, off the request thread) and 302 to the slug's
    destination: a wa.me deep link (WhatsApp slugs, with a channel-specific
    prefilled message) or Plato online booking (booking slugs). Unknown/
    unconfigured slugs fall back to the site so
    a published link never dead-ends. This route is intentionally
    unauthenticated; the rest of the dashboard stays founder-only.
    """
    slug = (slug or "").lower().strip()
    click_id = str(uuid.uuid4())
    # On-site CTA taps carry the booking session_id + page path (?sid=&p=) so a
    # WhatsApp tap can be tied back to the booking session it came from (the
    # golden-flow join; wa.me redirects can't use the ?cid passthrough and
    # cross-origin Referer is trimmed to the origin). Absent for off-site links.
    _record_link_click_async(click_id, slug, request.headers.get("User-Agent"),
                             request.headers.get("Referer"),
                             session_id=request.args.get("sid"),
                             page=request.args.get("p"))
    return redirect(_slug_target(slug, click_id), code=302)


# On the public links subdomain the slug sits at the root (go.gojiphysio.com/ig),
# so the published URLs stay short and on-brand. Registered ONLY in links mode so
# this catch-all can never shadow the dashboard/frontdesk routes; `/r/<slug>`
# above keeps working in every mode.
if APP_MODE == "links":
    @app.route("/<slug>")
    def links_slug(slug: str):
        return tracked_redirect(slug)


@app.route("/healthcheck")
def healthcheck() -> Response:
    # NB: not /healthz — Cloud Run's edge load balancer reserves /healthz for
    # its own internal probes and returns a Google-branded 404 before the
    # request reaches the container. /healthcheck is the public uptime ping.
    return Response("ok", mimetype="text/plain")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=DEV_MODE)
