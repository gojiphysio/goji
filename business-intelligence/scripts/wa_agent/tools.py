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
                       "in one call, starting with today's remaining times (from 2 hours from "
                       "now; their weekday is \"Today\"). Use this for 'when can I come in?' style questions. For a "
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
    {
        "name": "find_booking",
        "description": "Only when this chat's number has no patient record: look up the "
                       "customer's next appointment by their full name AND the phone number "
                       "the booking was made under. Both must match the same patient record. "
                       "Returns only the next appointment's date, time and clinician.",
        "input_schema": {"type": "object", "properties": {
            "full_name": {"type": "string"},
            "phone": {"type": "string", "description": "the number the booking was made under"}},
            "required": ["full_name", "phone"]},
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


def _booking_get(path: str, params: dict, http=requests, *, same_day: bool = False) -> dict:
    """`same_day` asks goji-booking for today's slots too (Plato's online rule
    hides them from the website). Only the assistant may see those, so it needs
    the internal token; without one (local runs) it falls back to the public view."""
    params = {k: v for k, v in params.items() if v not in (None, "", False)}
    if params.get("home") is True:
        params["home"] = "1"
    headers = {}
    if same_day and config.INTERNAL_TOKEN:
        params["same_day"] = "1"
        headers["X-Internal-Token"] = config.INTERNAL_TOKEN
    r = http.get(f"{config.BOOKING_API_BASE}{path}", params=params, timeout=20,
                 **({"headers": headers} if headers else {}))
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
                         "home": inp.get("home")}, http, same_day=True)
    return {"service": svc, "month": inp["month"], "available_dates": data.get("available", [])}


def get_times(inp: dict, *, http=requests, **_) -> dict:
    svc = _check_service(inp)
    try:
        date.fromisoformat(inp.get("date", ""))
    except ValueError:
        raise ToolError("date must be YYYY-MM-DD")
    data = _booking_get("/api/availability",
                        {"service": svc, "date": inp["date"], "focus": inp.get("focus"),
                         "home": inp.get("home")}, http, same_day=True)
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
                            {**common, "month": month.strftime("%Y-%m")}, http, same_day=True)
        dates += [d for d in data.get("available", []) if d >= start.isoformat()]
        if len(dates) >= NEXT_SLOTS_MAX_DAYS:
            break
        month = (month + timedelta(days=32)).replace(day=1)
    slots = []
    for d in sorted(dates)[:NEXT_SLOTS_MAX_DAYS]:
        day = _booking_get("/api/availability", {**common, "date": d}, http, same_day=True)
        names = {c["id"]: c["name"] for c in day.get("clinicians", [])}
        by_time: dict[str, list[str]] = {}
        for cid, times in (day.get("by_clinician") or {}).items():
            for t in times:
                by_time.setdefault(t, []).append(names.get(cid, cid))
        for t in sorted(by_time)[:NEXT_SLOTS_PER_DAY]:
            # Today's slots are labelled "Today" so the reply says so.
            slots.append({"date": d, "weekday": ("Today" if d == today.isoformat()
                                                 else date.fromisoformat(d).strftime("%a")),
                          "time": t, "clinicians": by_time[t]})
    return {"service": svc, "slots": slots,
            "note": "" if slots else "no open slots in the next two months"}


def booking_link(inp: dict, *, wa_id: str = "", **_) -> dict:
    svc = _check_service(inp)
    params = {"service": svc}
    if inp.get("focus"):
        params["focus"] = inp["focus"]
    if wa_id:
        # The chat's salted hash (events.chat_key), so a booking made from this
        # link can be credited to the conversation. Not reversible, so left out
        # when a deployed run has no secret salt (events.safe_chat_key).
        from .events import safe_chat_key
        ref = safe_chat_key(wa_id)
        if ref:
            params["ref"] = ref
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


# Returning-patient recognition: who this number is, run in code at the start of
# a conversation (never a model tool, never another number). First name, next
# appointment and last visit date only: no clinical notes, no other patients'
# details. Several patients can share a number (a parent and children), so the
# count goes with it and the name is only a hint.
_PATIENT_SQL = """
WITH patients AS (
  SELECT patient_id, SPLIT(TRIM(full_name), ' ')[SAFE_OFFSET(0)] AS first_name
  FROM `{project}.marts.dim_patient_contact`
  WHERE RIGHT(REGEXP_REPLACE(COALESCE(phone, ''), r'\\D', ''), 8) = @last8
),
appts AS (
  SELECT a.appt_date, FORMAT_TIMESTAMP('%H:%M', a.start_at, 'UTC') AS time_sgt,
         a.clinician_id, a.treatment_type
  FROM `{project}.stg.appointments` a
  JOIN patients p USING (patient_id)
  WHERE COALESCE(SAFE_CAST(JSON_VALUE(a.payload, '$.cancelled') AS INT64), 0) = 0
    AND COALESCE(SAFE_CAST(JSON_VALUE(a.payload, '$.void') AS INT64), 0) = 0
    AND LOWER(COALESCE(JSON_VALUE(a.payload, '$.status'), '')) NOT IN
        ('cancelled', 'canceled', 'no_show', 'noshow', 'no-show')
)
SELECT
  (SELECT COUNT(DISTINCT patient_id) FROM patients) AS n_patients,
  (SELECT ARRAY_AGG(DISTINCT patient_id) FROM patients) AS patient_ids,
  (SELECT ARRAY_AGG(STRUCT(c.patient_id AS id, c.full_name AS name, c.email AS email))
     FROM `{project}.marts.dim_patient_contact` c JOIN patients p USING (patient_id)) AS records,
  (SELECT LOGICAL_OR('Late change waiver used' IN UNNEST(d.tags))
     FROM `{project}.marts.dim_patient` d JOIN patients p USING (patient_id)) AS waiver_used,
  (SELECT ANY_VALUE(first_name) FROM patients) AS first_name,
  (SELECT AS STRUCT appt_date, time_sgt, clinician_id, treatment_type FROM appts
    WHERE appt_date >= CURRENT_DATE('Asia/Singapore')
    ORDER BY appt_date, time_sgt LIMIT 1) AS next_appt,
  (SELECT MAX(appt_date) FROM appts WHERE appt_date < CURRENT_DATE('Asia/Singapore')) AS last_visit
"""


def patient_context(wa_id: str, *, bq=None) -> dict:
    """{} when lookup is off or fails; {"returning": False} for an unknown
    number; else first name, how many patients share the number, the next
    appointment and the last visit date."""
    digits = re.sub(r"\D", "", wa_id)
    if config.TEST_PATIENTS and config.STATE_BACKEND == "memory":
        fake = config.TEST_PATIENTS.get(digits)  # local tone testing only
        if fake is not None:
            return fake
    if not config.PATIENT_LOOKUP or len(digits) < 8:
        return {}
    try:
        if bq is None:
            from google.cloud import bigquery
            bq = bigquery.Client(project=config.PROJECT)
        from google.cloud import bigquery as _bq
        job = bq.query(_PATIENT_SQL.format(project=config.PROJECT),
                       job_config=_bq.QueryJobConfig(query_parameters=[
                           _bq.ScalarQueryParameter("last8", "STRING", digits[-8:])]))
        row = next(iter(job.result()), None)
    except Exception as e:
        log.warning("patient lookup failed: %s", e)
        return {}
    if not row or not row["n_patients"]:
        return {"returning": False}
    nxt = row["next_appt"]
    return {"returning": True, "first_name": row["first_name"] or "",
            "patients_on_number": row["n_patients"],
            # internal: for tagging in Plato, never shown to the model
            "patient_ids": list(row["patient_ids"] or []),
            # email: internal, for the booking only (Plato's confirmation goes
            # to it); the model is told only whether one is on file
            "records": [{"id": r["id"], "name": r["name"] or "", "email": r["email"] or ""}
                        for r in (row["records"] or [])],
            "waiver_used": bool(row["waiver_used"]),
            "next_appointment": ({"date": nxt["appt_date"].isoformat(), "time": nxt["time_sgt"],
                                  "with": CLINICIAN_NAMES.get(nxt["clinician_id"], "the team"),
                                  "type": nxt["treatment_type"]} if nxt else None),
            "last_visit": row["last_visit"].isoformat() if row["last_visit"] else None}


def record_for_booking(patient: dict, full_name: str, for_whom: str) -> str:
    """Which existing Plato record a WhatsApp booking belongs to, or "" (create
    a new one). A record on this number only counts if the patient's name
    matches it; the one exception is booking for oneself with exactly one
    record on the number. Never the texter's record for someone else."""
    records = (patient or {}).get("records") or []
    named = [r for r in records if _name_matches(full_name, r.get("name", ""))]
    if len(named) == 1:
        return named[0]["id"]
    self_booking = (for_whom or "self").strip().lower() in ("", "self")
    if self_booking and len(records) == 1 and not named:
        first = (full_name or "").split()
        if first and first[0].lower() in records[0].get("name", "").lower():
            return records[0]["id"]
    return ""


def contact_email(patient: dict, patient_id: str, texter: str = "") -> str:
    """The email a booking's confirmation goes to when the customer gave none,
    or "": the booked patient's own on file, else the texter's (owner, 25 Nov
    2026: the person chatting is the contact, as with the phone number).
    `texter` is the name they go by (booked_by or the WhatsApp profile name);
    when it fits no record, the first email on the number. Never shown to the
    model: it only goes to Plato with the booking."""
    records = [r for r in (patient or {}).get("records") or []
               if (r.get("email") or "").strip()]
    own = [r for r in records if patient_id and r.get("id") == patient_id]
    words = set(re.findall(r"[a-z]+", (texter or "").lower()))
    theirs = [r for r in records if words & set(re.findall(r"[a-z]+", r["name"].lower()))]
    pick = (own or theirs or records or [{}])[0]
    return (pick.get("email") or "").strip()


# Full names on the chat's own number, so the agent books a returning patient
# without asking for a name it already has (owner, 25 Nov 2026: a returning
# couple was asked for both full names). A family number rarely has more.
NAMES_SHOWN = 4


def describe_patient(p: dict) -> str:
    """The patient context as one line for the model."""
    if not p:
        return ""
    if not p.get("returning"):
        return "no patient record for this number (likely a new enquiry)"
    names = [r["name"].strip() for r in p.get("records") or [] if (r.get("name") or "").strip()]
    bits = ["a patient record is linked to this number (the texter may be this patient "
            "or someone booking for them)"]
    bits.append(f"full name{'s' if len(names) > 1 else ''} on file: "
                f"{', '.join(names[:NAMES_SHOWN])} (use one only for someone the customer "
                "has named or who is writing; never mention the others)" if names
                else f"record first name {p.get('first_name') or 'unknown'}")
    if (p.get("patients_on_number") or 1) > 1:
        bits.append(f"{p['patients_on_number']} patients share this number (e.g. a parent "
                    "and children), so don't assume which one is writing")
    n = p.get("next_appointment")
    bits.append(f"next appointment {n['date']} {n['time']} with {n['with']}" if n
                else "no upcoming appointment")
    if p.get("last_visit"):
        bits.append(f"last visit {p['last_visit']}")
    records = p.get("records") or []
    if any((r.get("email") or "").strip() for r in records):
        bits.append("an email is on file for this number (bookings use it, also for family "
                    "members: don't ask for one)")
    elif records:
        bits.append("no email on file (ask for one when booking)")
    if p.get("waiver_used"):
        bits.append("first-time late-change waiver already used (tagged in Plato)")
    return "; ".join(bits)


# Second-chance lookup for a chat whose own number has no record (Charles,
# 19 Nov 2026: ask for details before handing over). Name AND booking number
# must both match one patient, so a number alone, or a name alone, reveals
# nothing; only the next appointment comes back. Capped per chat per process.
_FIND_SQL = """
WITH p AS (
  SELECT patient_id, LOWER(TRIM(full_name)) AS name
  FROM `{project}.marts.dim_patient_contact`
  WHERE RIGHT(REGEXP_REPLACE(COALESCE(phone, ''), r'\\D', ''), 8) = @last8
)
SELECT a.appt_date, FORMAT_TIMESTAMP('%H:%M', a.start_at, 'UTC') AS time_sgt, a.clinician_id,
       p.name
FROM `{project}.stg.appointments` a JOIN p USING (patient_id)
WHERE a.appt_date >= CURRENT_DATE('Asia/Singapore')
  AND COALESCE(SAFE_CAST(JSON_VALUE(a.payload, '$.cancelled') AS INT64), 0) = 0
  AND COALESCE(SAFE_CAST(JSON_VALUE(a.payload, '$.void') AS INT64), 0) = 0
  AND LOWER(COALESCE(JSON_VALUE(a.payload, '$.status'), '')) NOT IN
      ('cancelled', 'canceled', 'no_show', 'noshow', 'no-show')
ORDER BY a.appt_date, time_sgt
"""
FIND_MAX_TRIES = 3
_find_tries: dict[str, int] = {}


def _name_matches(given: str, record: str) -> bool:
    """Every word the customer gave appears in the record's name (order free),
    and they gave at least two words: 'Sarah Tan' matches 'Tan Sarah Mei Ling'."""
    g = [w for w in re.findall(r"[a-z]+", given.lower()) if len(w) > 1]
    r = set(re.findall(r"[a-z]+", record.lower()))
    return len(g) >= 2 and all(w in r for w in g)


def find_booking(inp: dict, *, wa_id: str, bq=None, **_) -> dict:
    if not config.PATIENT_LOOKUP:
        return {"enabled": False}
    _find_tries[wa_id] = _find_tries.get(wa_id, 0) + 1
    if _find_tries[wa_id] > FIND_MAX_TRIES:
        raise ToolError("too many lookups in this chat; hand over to the team")
    digits = re.sub(r"\D", "", inp.get("phone", ""))
    name = (inp.get("full_name") or "").strip()
    if len(digits) < 8 or not name:
        raise ToolError("need the full name and the phone number the booking was made under")
    if bq is None:
        from google.cloud import bigquery
        bq = bigquery.Client(project=config.PROJECT)
    from google.cloud import bigquery as _bq
    rows = list(bq.query(_FIND_SQL.format(project=config.PROJECT),
                         job_config=_bq.QueryJobConfig(query_parameters=[
                             _bq.ScalarQueryParameter("last8", "STRING", digits[-8:])])).result())
    hits = [r for r in rows if _name_matches(name, r["name"] or "")]
    if not hits:
        return {"matched": False}
    r = hits[0]
    return {"matched": True, "next_appointment": {
        "date": r["appt_date"].isoformat(), "time": r["time_sgt"],
        "with": CLINICIAN_NAMES.get(r["clinician_id"], "the team")}}


HANDLERS = {
    "next_slots": next_slots,
    "find_available_dates": find_available_dates,
    "get_times": get_times,
    "booking_link": booking_link,
    "read_page": read_page,
    "my_appointments": my_appointments,
    "find_booking": find_booking,
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
