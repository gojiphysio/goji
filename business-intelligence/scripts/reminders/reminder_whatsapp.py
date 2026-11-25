"""
48-hour appointment reminders over WhatsApp: template parameters + Cloud API send.

The WhatsApp channel goes first for anyone with a usable mobile number; email
(reminder_mailer.py) is the fallback. main.py decides the channel; this module
only knows how to turn one appointment into one template message and send it.

Same split as reminder_mailer.py: PURE functions (normalise_phone,
template_params, build_payload, render_preview) that take primitives and are
unit-tested with no network, and one impure send_template() that takes an
injectable HTTP session so tests can fake it.

One message per APPOINTMENT, not per patient. A template fills in one date,
time, service and clinician, so a patient with two sessions that day gets two
messages, in time order. (Email still groups them into one.)

The template (`goji_appointment_reminder`, en, UTILITY) as submitted to Meta:

    Hi {{1}}, a reminder of your {{2}} appointment on {{3}} with {{4}} at Goji
    Women's and Family Physiotherapy.

    If you need to reschedule, please let us know at least 24 hours before.
    [Confirm] [Reschedule]   <- quick-reply buttons, in that order

Its wording lives in Meta, not here. TEMPLATE_BODY below is a copy used only to
render the dry-run preview in the digest; if the approved wording changes, update
it so the preview stays honest.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date

import requests

from reminder_mailer import first_name

log = logging.getLogger("reminders.whatsapp")

# Meta's Cloud API. Same names, defaults and meaning as wa_agent/config.py, so
# one set of transport values serves both the assistant and this job. A
# provider (360dialog-style) changes the base URL, the send path and the auth
# header; the payload stays Cloud API shaped. E.g. 360dialog:
#   WA_API_BASE=https://waba-v2.360dialog.io WA_SEND_PATH=/messages
#   WA_AUTH_HEADER=D360-API-KEY WA_AUTH_PREFIX=   (set, but empty)
# `or`: the deploy passes an empty value when the repo variable is unset.
WA_API_BASE = os.environ.get("WA_API_BASE") or "https://graph.facebook.com/v23.0"
WA_PHONE_NUMBER_ID = os.environ.get("WA_PHONE_NUMBER_ID", "")
# Meta: /{phone_number_id}/messages. 360dialog-style providers: /messages.
WA_SEND_PATH = os.environ.get("WA_SEND_PATH", "/{phone_number_id}/messages")
WA_AUTH_HEADER = os.environ.get("WA_AUTH_HEADER", "Authorization")
# Unset means "Bearer "; set-but-empty means the raw key (360dialog).
WA_AUTH_PREFIX = os.environ.get("WA_AUTH_PREFIX", "Bearer ")
WA_TOKEN = os.environ.get("WA_TOKEN", "")  # Secret Manager wa-token
TEMPLATE = os.environ.get("WA_REMINDER_TEMPLATE", "goji_appointment_reminder")
LANGUAGE = os.environ.get("WA_REMINDER_LANGUAGE", "en")

TEMPLATE_BODY = (
    "Hi {{1}}, a reminder of your {{2}} appointment on {{3}} with {{4}} at Goji "
    "Women's and Family Physiotherapy.\n\n"
    "If you need to reschedule, please let us know at least 24 hours before."
)

# Quick-reply buttons in the order they were approved. The payload comes back in
# the webhook (messages[].button.payload) when the patient taps, so the assistant
# can tell which appointment a tap is for without guessing from the chat.
BUTTON_PAYLOADS = ("reminder_confirm", "reminder_reschedule")

# stg.appointments.treatment_type -> the {{2}} slot, which reads mid-sentence:
# "a reminder of your physiotherapy appointment". 'Untyped' (~45% of bookings:
# consults and untagged sessions) and 'Unknown' map to "upcoming" rather than
# guessing a service the patient didn't book.
SERVICE_WORDS = {
    "Physiotherapy": "physiotherapy",
    "Pilates": "Pilates",
    "S&C": "strength and conditioning",
    "Home Visit": "home visit",
}
SERVICE_FALLBACK = "upcoming"

# Plato doctor code (fct_appointment_reminders.clinician_id) -> first name for
# {{4}}. Mirrors booking/config.py CLINICIANS and the calendar-colour CASE in
# stg/03_appointments.sql; test_reminders.py fails if booking/config.py gains a
# doctor code that's missing here. An unmapped calendar reads "with our team".
CLINICIAN_FIRST_NAMES = {
    "PCL": "Cheryl",
    "PKN": "Kristy",
    "PCN": "Claire",
    "ICT": "Camille",
}
CLINICIAN_FALLBACK = "our team"


class WhatsAppSendError(Exception):
    """The Cloud API refused the message (non-2xx, error body, or no id)."""


# --- pure helpers ----------------------------------------------------------

def normalise_phone(raw: str | None) -> str | None:
    """A free-text phone number -> WhatsApp `to` digits, or None if unusable.

    '9123 4567' / '+65 9123-4567' / '6591234567' -> '6591234567'
    '+44 7700 900123' / '0044 7700 900123'       -> '447700900123'
    '6123 4567' (SG landline), '12345', ''        -> None

    Singapore: 8 digits starting 8 or 9 is a mobile; anything else 8 digits long
    (6xxx landlines, 3xxx VoIP) can't take WhatsApp. A number written with '+' or
    '00' is already international and kept, as are 11-15 bare digits not starting
    65 (e.g. a Malaysian 60...). Anything ambiguous returns None and the patient
    falls back to email: a wrong guess would WhatsApp a stranger.
    """
    s = (raw or "").strip()
    if not s:
        return None
    international = s.startswith("+") or s.startswith("00")
    digits = re.sub(r"\D", "", s)
    if s.startswith("00"):
        digits = digits[2:]
    if digits.startswith("65"):
        # Singapore with country code: must be a mobile.
        local = digits[2:]
        if len(local) == 8 and local[0] in "89":
            return digits
        return None
    if international:
        return digits if 8 <= len(digits) <= 15 else None
    if len(digits) == 8:
        return "65" + digits if digits[0] in "89" else None
    if 11 <= len(digits) <= 15:
        return digits
    return None


def fmt_slot(date_str: str, time_str: str | None) -> str:
    """The {{3}} slot: ('2026-11-26', '10:00') -> 'Thu 26 Nov, 10:00am'.

    time_str is the view's appt_time_sgt: clinic wall clock, already read back
    out of the naive-SGT-stored-as-UTC start_at by formatting at 'UTC'. It is
    used as-is. Never convert it to Asia/Singapore, which would add 8 hours.
    """
    try:
        d = date.fromisoformat(date_str)
        day = f"{d:%a} {d.day} {d:%b}"
    except (ValueError, TypeError):
        day = str(date_str)
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", (time_str or "").strip())
    if not m:
        return day
    hour, minute = int(m.group(1)), m.group(2)
    return f"{day}, {hour % 12 or 12}:{minute}{'am' if hour < 12 else 'pm'}"


def service_word(treatment_type: str | None) -> str:
    return SERVICE_WORDS.get(treatment_type or "", SERVICE_FALLBACK)


def clinician_first_name(clinician_id: str | None) -> str:
    return CLINICIAN_FIRST_NAMES.get(clinician_id or "", CLINICIAN_FALLBACK)


def template_params(row: dict, date_str: str) -> list[str]:
    """One appointment row -> the four body parameters, in template order."""
    return [
        first_name(row.get("name")),
        service_word(row.get("treatment_type")),
        fmt_slot(date_str, row.get("time")),
        clinician_first_name(row.get("clinician_id")),
    ]


def render_preview(params: list[str]) -> str:
    """The message text as the patient would read it (dry-run digest only)."""
    text = TEMPLATE_BODY
    for i, p in enumerate(params, start=1):
        text = text.replace("{{%d}}" % i, p)
    return text


def build_payload(to: str, params: list[str], appointment_id: str) -> dict:
    """The Cloud API request body for one reminder.

    Quick-reply buttons need no parameters to send, but each one may carry a
    payload, returned to the webhook on tap. Indexes are the button positions in
    the approved template (0 = Confirm, 1 = Reschedule).
    """
    components: list[dict] = [{
        "type": "body",
        "parameters": [{"type": "text", "text": p} for p in params],
    }]
    for i, prefix in enumerate(BUTTON_PAYLOADS):
        components.append({
            "type": "button",
            "sub_type": "quick_reply",
            "index": str(i),
            "parameters": [{"type": "payload", "payload": f"{prefix}:{appointment_id}"}],
        })
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": TEMPLATE,
            "language": {"code": LANGUAGE},
            "components": components,
        },
    }


# TEST MODE, the WhatsApp twin of REMINDER_OVERRIDE_TO: every WhatsApp reminder
# goes to this number instead of the patient. Applied in send_template, at the
# point of send, so no caller can route around it. main.py refuses to run with
# this set unless REMINDER_OVERRIDE_TO is set too, so a WhatsApp test can't
# email patients.
OVERRIDE_TO_RAW = os.environ.get("WA_REMINDER_OVERRIDE_TO", "").strip()
OVERRIDE_TO = normalise_phone(OVERRIDE_TO_RAW) or ""


# --- transport -------------------------------------------------------------

def needs_phone_number_id() -> bool:
    """Meta's path carries the number id; a provider's /messages doesn't (the
    key identifies the number), so WA_PHONE_NUMBER_ID is optional there."""
    return "{phone_number_id}" in WA_SEND_PATH


def send_url() -> str:
    """WA_API_BASE + WA_SEND_PATH, built exactly as wa_agent/whatsapp.py does."""
    return WA_API_BASE.rstrip("/") + WA_SEND_PATH.format(phone_number_id=WA_PHONE_NUMBER_ID)


def _error_text(resp) -> str:
    """'HTTP 400: (#132001) Template name does not exist in the translation'."""
    try:
        err = (resp.json() or {}).get("error") or {}
    except ValueError:
        err = {}
    if err:
        detail = (err.get("error_data") or {}).get("details") or ""
        msg = f"(#{err.get('code', '?')}) {err.get('message', '')}".strip()
        if detail and detail not in msg:
            msg += f": {detail}"
    else:
        msg = (getattr(resp, "text", "") or "")[:200]
    return f"HTTP {resp.status_code}: {msg}"


def send_template(to: str, params: list[str], appointment_id: str, *,
                  session=None) -> str:
    """Send one reminder template. Returns the WhatsApp message id (wamid).

    Raises WhatsAppSendError on a network error, a non-2xx status, an error body,
    or a 2xx with no message id, so the caller can fall back to email.

    A 2xx means Meta ACCEPTED the message, not that it was delivered. A number
    that isn't on WhatsApp fails later, on the status webhook (error 131026), and
    this job never sees it.
    """
    if OVERRIDE_TO:
        to = OVERRIDE_TO
    url = send_url()
    headers = {WA_AUTH_HEADER: f"{WA_AUTH_PREFIX}{WA_TOKEN}",
               "Content-Type": "application/json"}
    http = session or requests
    try:
        resp = http.post(url, json=build_payload(to, params, appointment_id),
                         headers=headers, timeout=15)
    except requests.RequestException as e:
        raise WhatsAppSendError(f"network error: {e.__class__.__name__}") from e
    if not 200 <= resp.status_code < 300:
        raise WhatsAppSendError(_error_text(resp))
    try:
        body = resp.json() or {}
    except ValueError:
        raise WhatsAppSendError(f"HTTP {resp.status_code}: response was not JSON")
    if body.get("error"):
        raise WhatsAppSendError(_error_text(resp))
    msg_id = ((body.get("messages") or [{}])[0] or {}).get("id")
    if not msg_id:
        raise WhatsAppSendError(f"HTTP {resp.status_code}: no message id in response")
    log.info("whatsapp reminder accepted (appointment %s)", appointment_id)
    return msg_id
