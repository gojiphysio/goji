"""
The agent's tools. All read-only: none of them books, cancels or changes
anything, so a manipulated model can't do more than say something wrong
(which policy.py and the eval guard against).

- Availability comes from goji-booking's public API, which serves its
  5-minute Plato snapshot. Never call Plato from here: the clinic's API key
  allows 20 requests/min shared with the website and ingestion jobs.
- Booking links go through the trackable redirector (wa-book slug).
- Patient lookup is keyed on the chat's own WhatsApp number, never on a number
  the model supplies, so a customer can only ever see their own appointments.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

from . import config, kb

log = logging.getLogger("wa_agent.tools")

# Mirror of booking/config.py SERVICES and PHYSIO_FOCUS_LABELS (test_tools.py
# fails if they drift).
SERVICES = {
    "physiotherapy": "Physiotherapy (55 min; pelvic floor, prenatal, postnatal, MSK, paediatric, scoliosis)",
    "mummy-baby": "Mummy & Baby Assessment (85 min)",
    "clinical-pilates": "Clinical Pilates (physio-led)",
    "private-pilates": "Private Pilates (instructor-led)",
    "strength-conditioning": "Strength & Conditioning",
}
FOCUSES = ("general", "womens-health", "paediatrics", "scoliosis", "others")
SGT_TZ = timezone(timedelta(hours=8))
CLINICIAN_NAMES = {"PCL": "Cheryl", "PKN": "Kristy", "PCN": "Claire", "ICT": "Camille"}

_FOCUS_PROP = {"type": "string", "enum": list(FOCUSES),
               "description": "Physiotherapy only: which kind. Omit for other services."}
_HOME_PROP = {"type": "boolean",
              "description": "True for a home visit (physiotherapy and mummy-baby only)."}

TOOL_DEFS = [
    {
        "name": "next_slots",
        "description": "The next open appointment times for a service, across the coming days, "
                       "in one call. Use this for 'when can I come in?' style questions. For a "
                       "specific day the customer named, use get_times.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "enum": list(SERVICES)},
                "focus": _FOCUS_PROP,
                "home": _HOME_PROP,
                "from_date": {"type": "string",
                              "description": "YYYY-MM-DD, earliest day to look. Default today."},
            },
            "required": ["service"],
        },
    },
    {
        "name": "find_available_dates",
        "description": "Dates in a month that have at least one free slot for a service. "
                       "Use before offering times, to suggest the nearest open days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "enum": list(SERVICES)},
                "month": {"type": "string", "description": "YYYY-MM"},
                "focus": _FOCUS_PROP,
                "home": _HOME_PROP,
            },
            "required": ["service", "month"],
        },
    },
    {
        "name": "get_times",
        "description": "Free start times on one date for a service, with which clinician is free. "
                       "Times are clinic local time (SGT).",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "enum": list(SERVICES)},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "focus": _FOCUS_PROP,
                "home": _HOME_PROP,
            },
            "required": ["service", "date"],
        },
    },
    {
        "name": "booking_link",
        "description": "The link the customer uses to book a service themselves on the website. "
                       "Always give this rather than any other booking URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "enum": list(SERVICES)},
                "focus": _FOCUS_PROP,
            },
            "required": ["service"],
        },
    },
    {
        "name": "read_page",
        "description": "Full text of a page named in the knowledge base: services/<id> (with "
                       "its FAQs), team/<id>, conditions/<id> or blog/<id>. Use it for anything "
                       "the short summaries don't cover; never answer from general knowledge.",
        "input_schema": {
            "type": "object",
            "properties": {"page_id": {"type": "string"}},
            "required": ["page_id"],
        },
    },
    {
        "name": "my_appointments",
        "description": "This customer's upcoming appointments, matched on the WhatsApp number "
                       "they are messaging from. Several patients can share one number "
                       "(e.g. a parent booking for children).",
        "input_schema": {"type": "object", "properties": {}},
    },
]


class ToolError(Exception):
    """Shown to the model as an is_error tool result."""


def _check_service(inp: dict) -> str:
    svc = inp.get("service")
    if svc not in SERVICES:
        raise ToolError(f"unknown service {svc!r}; use one of {list(SERVICES)}")
    focus = inp.get("focus")
    if focus is not None and focus not in FOCUSES:
        raise ToolError(f"unknown focus {focus!r}; use one of {list(FOCUSES)}")
    return svc


def _booking_get(path: str, params: dict, http=requests) -> dict:
    params = {k: v for k, v in params.items() if v not in (None, "", False)}
    if params.get("home") is True:
        params["home"] = "1"
    r = http.get(f"{config.BOOKING_API_BASE}{path}", params=params, timeout=20)
    if r.status_code == 503:
        raise ToolError("availability is loading; try once more, or offer the booking link")
    r.raise_for_status()
    return r.json()


def find_available_dates(inp: dict, *, http=requests, **_) -> dict:
    svc = _check_service(inp)
    if not re.fullmatch(r"\d{4}-\d{2}", inp.get("month", "")):
        raise ToolError("month must be YYYY-MM")
    data = _booking_get("/api/availability-summary",
                        {"service": svc, "month": inp["month"], "focus": inp.get("focus"),
                         "home": inp.get("home")}, http)
    return {"service": svc, "month": inp["month"], "available_dates": data.get("available", [])}


def get_times(inp: dict, *, http=requests, **_) -> dict:
    svc = _check_service(inp)
    try:
        date.fromisoformat(inp.get("date", ""))
    except ValueError:
        raise ToolError("date must be YYYY-MM-DD")
    data = _booking_get("/api/availability",
                        {"service": svc, "date": inp["date"], "focus": inp.get("focus"),
                         "home": inp.get("home")}, http)
    names = {c["id"]: c["name"] for c in data.get("clinicians", [])}
    return {"service": svc, "date": inp["date"], "times": data.get("times", []),
            "by_clinician": {names.get(cid, cid): slots
                             for cid, slots in (data.get("by_clinician") or {}).items()}}


NEXT_SLOTS_MAX_DAYS = 3      # days whose times we fetch
NEXT_SLOTS_PER_DAY = 3       # times offered per day, so options spread across days


def next_slots(inp: dict, *, http=requests, today: date | None = None, **_) -> dict:
    """Open dates from the month summary (this month and next), then times for
    the first few of them. At most 2 summary calls + 3 day calls, all served
    from goji-booking's snapshot."""
    svc = _check_service(inp)
    today = today or datetime.now(SGT_TZ).date()
    start = today
    if inp.get("from_date"):
        try:
            start = max(today, date.fromisoformat(inp["from_date"]))
        except ValueError:
            raise ToolError("from_date must be YYYY-MM-DD")
    common = {"service": svc, "focus": inp.get("focus"), "home": inp.get("home")}
    dates: list[str] = []
    month = start.replace(day=1)
    for _ in range(2):
        data = _booking_get("/api/availability-summary",
                            {**common, "month": month.strftime("%Y-%m")}, http)
        dates += [d for d in data.get("available", []) if d >= start.isoformat()]
        if len(dates) >= NEXT_SLOTS_MAX_DAYS:
            break
        month = (month + timedelta(days=32)).replace(day=1)
    slots = []
    for d in sorted(dates)[:NEXT_SLOTS_MAX_DAYS]:
        day = _booking_get("/api/availability", {**common, "date": d}, http)
        names = {c["id"]: c["name"] for c in day.get("clinicians", [])}
        by_time: dict[str, list[str]] = {}
        for cid, times in (day.get("by_clinician") or {}).items():
            for t in times:
                by_time.setdefault(t, []).append(names.get(cid, cid))
        for t in sorted(by_time)[:NEXT_SLOTS_PER_DAY]:
            slots.append({"date": d, "weekday": date.fromisoformat(d).strftime("%a"),
                          "time": t, "clinicians": by_time[t]})
    return {"service": svc, "slots": slots,
            "note": "" if slots else "no open slots in the next two months"}


def booking_link(inp: dict, **_) -> dict:
    svc = _check_service(inp)
    params = {"service": svc}
    if inp.get("focus"):
        params["focus"] = inp["focus"]
    return {"url": f"{config.BOOKING_LINK_BASE}?{urlencode(params)}"}


def read_page(inp: dict, **_) -> dict:
    pages = kb.load()["pages"]
    page_id = (inp.get("page_id") or "").strip().strip("/")
    if page_id not in pages:
        raise ToolError(f"no page {page_id!r}; use an id from the knowledge base index")
    return {"page_id": page_id, "text": pages[page_id]}


_LOOKUP_SQL = """
WITH patients AS (
  SELECT patient_id, SPLIT(TRIM(full_name), ' ')[SAFE_OFFSET(0)] AS first_name
  FROM `{project}.marts.dim_patient_contact`
  WHERE RIGHT(REGEXP_REPLACE(COALESCE(phone, ''), r'\\D', ''), 8) = @last8
)
SELECT p.first_name, a.appt_date,
       FORMAT_TIMESTAMP('%H:%M', a.start_at, 'UTC') AS time_sgt,  -- wall clock, see fct_appointment_reminders
       a.clinician_id, a.treatment_type
FROM `{project}.stg.appointments` a
JOIN patients p USING (patient_id)
WHERE a.appt_date >= CURRENT_DATE('Asia/Singapore')
  AND COALESCE(SAFE_CAST(JSON_VALUE(a.payload, '$.cancelled') AS INT64), 0) = 0
  AND COALESCE(SAFE_CAST(JSON_VALUE(a.payload, '$.void') AS INT64), 0) = 0
  AND LOWER(COALESCE(JSON_VALUE(a.payload, '$.status'), '')) NOT IN
      ('cancelled', 'canceled', 'no_show', 'noshow', 'no-show')
ORDER BY a.appt_date, time_sgt
LIMIT 6
"""


def my_appointments(inp: dict, *, wa_id: str, bq=None, **_) -> dict:
    if not config.PATIENT_LOOKUP:
        return {"enabled": False,
                "note": "Appointment lookup is off. Say a team member will confirm their booking."}
    digits = re.sub(r"\D", "", wa_id)
    if len(digits) < 8:
        return {"matched": False}
    if bq is None:
        from google.cloud import bigquery
        bq = bigquery.Client(project=config.PROJECT)
    from google.cloud import bigquery as _bq
    job = bq.query(_LOOKUP_SQL.format(project=config.PROJECT),
                   job_config=_bq.QueryJobConfig(query_parameters=[
                       _bq.ScalarQueryParameter("last8", "STRING", digits[-8:])]))
    rows = list(job.result())
    return {"matched": bool(rows),
            "appointments": [{"patient_first_name": r["first_name"],
                              "date": r["appt_date"].isoformat(), "time": r["time_sgt"],
                              "with": CLINICIAN_NAMES.get(r["clinician_id"], "the team"),
                              "type": r["treatment_type"]} for r in rows]}


HANDLERS = {
    "next_slots": next_slots,
    "find_available_dates": find_available_dates,
    "get_times": get_times,
    "booking_link": booking_link,
    "read_page": read_page,
    "my_appointments": my_appointments,
}


def run_tool(name: str, inp: dict, *, wa_id: str, **deps) -> tuple[dict | str, bool]:
    """Returns (result, is_error). Never raises: a failing tool becomes an
    error result the model can work around (usually by offering the link)."""
    handler = HANDLERS.get(name)
    if handler is None:
        return f"unknown tool {name}", True
    try:
        return handler(inp or {}, wa_id=wa_id, **deps), False
    except ToolError as e:
        return str(e), True
    except Exception as e:
        log.warning("tool %s failed: %s", name, e, exc_info=True)
        return f"{name} is unavailable right now", True
