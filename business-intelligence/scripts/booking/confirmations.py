"""One confirmation email per appointment, whoever booked it.

Appointments reach Plato three ways: the website form (/api/book), the
WhatsApp assistant (/internal/book) and staff typing them into Plato. Before
this module only the first two got an email (mailer.send_customer_booking_email)
and staff bookings got none unless someone clicked Plato's own send. Now every
appointment with an email gets the same email, sent once:

  - website + WhatsApp bookings: on_booking(), called right after the Plato
    write (Plato sends no webhook for our own API writes).
  - WhatsApp reschedules: on_reschedule(), same reason.
  - staff bookings and moves: Plato's appointment:upsert webhook
    (handle_webhook), and the 15-minute sweep (sweep) that catches anything the
    webhook missed. Plato doesn't store or replay webhook events.

What the email carries (decided with the clinic, 25 Nov 2026): the details,
Plato's Confirm Appointment link, the address or home-visit note, the
cancellation policy, the WhatsApp link, Plato's registration form until the
patient has signed it (the "Clinic Consent Form" on their profile), and a
calendar invite that lands in the patient's calendar with no
alert and no RSVP traffic. A deleted appointment sends nothing.

The ledger (marts.appointment_confirmation_events) is the guard against a second
email: an appointment already confirmed at the same start time is skipped, and a
new start time sends a "moved" email that updates the same calendar entry.

CONFIRMATIONS_MODE:
  off  (default) today's behaviour: the old customer email for website and
       WhatsApp bookings, nothing for staff bookings.
  test every appointment's new email goes to CONFIRMATIONS_TEST_TO instead of
       the patient, and patients keep getting the old email. Ledger rows are
       'test', which never suppress a real send.
  live the new email goes to patients and the old customer email stops.
CONFIRMATIONS_SINCE ('YYYY-MM-DD HH:MM', clinic time): appointments created
before it are never confirmed by the webhook or the sweep, so switching on can't
mail the existing diary. Unset = the webhook and sweep do nothing.
"""
from __future__ import annotations

import base64
import logging
import os
import smtplib
import ssl
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from html import escape

from . import formlink
from .config import CLINICIANS, HOME_VISIT_TYPE_CODE, SERVICES, clinician_by_calendar
from .plato import one_record

log = logging.getLogger("booking.confirmations")

PROJECT = os.environ.get("GCP_PROJECT", "goji-bi")
PLATO_DB = os.environ.get("PLATO_DB", "gojihealth")
LEDGER_TABLE = f"{PROJECT}.marts.appointment_confirmation_events"
APPOINTMENTS_VIEW = f"{PROJECT}.stg.appointments"
CONTACT_TABLE = f"{PROJECT}.marts.dim_patient_contact"
PATIENT_TABLE = f"{PROJECT}.marts.dim_patient"

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "hello@gojiphysio.com")
SMTP_PASS = os.environ.get("GMAIL_APP_PASSWORD")  # Secret Manager
FROM_NAME = os.environ.get("BOOKING_FROM_NAME", "Goji Physiotherapy")

# Tracked WhatsApp CTA ('confirm-wa' in dashboard LINK_SLUGS), never raw wa.me.
WHATSAPP_LINK = os.environ.get("CONFIRM_WA_LINK", "https://go.gojiphysio.com/confirm-wa")
WHATSAPP_NUMBER = "+65 8377 0401"
MAPS_LINK = os.environ.get("BOOKING_MAPS_LINK", "https://maps.app.goo.gl/Mm3eYLNMUwwx8USv8")
GETTING_HERE_LINK = "https://www.gojiphysio.com/getting-here/"
CLINIC_ADDRESS = "#01-13, Lentor Modern, 1 Lentor Central, Singapore 788887"
CLINIC_ADDRESS_NOTE = "(outer ring of the mall)"
POLICY = ("Please give us at least 24 hours' notice if you need to reschedule or "
          "cancel. A $50 fee applies to cancellations made within 24 hours and to "
          "missed appointments without prior notice.")

# Plato appointment type (code_Bottom) -> the words the email uses. Mirrors
# stg/03_appointments.sql; an unknown code falls back to a plain "appointment".
SERVICE_WORDS = {"hDWW": "Physiotherapy", "2kV4": "Pilates",
                 "qLbH": "Strength and conditioning", "sCla": "Home visit"}
for _svc in SERVICES.values():
    SERVICE_WORDS.setdefault(_svc.get("type_code") or "", _svc["title"])
SERVICE_WORDS.pop("", None)

# Plato's "Confirmed" appointment code (code_Right). Set by the patient's Confirm
# link, a WhatsApp Confirm tap (confirm_appointment) or staff.
CONFIRMED_CODE = "qK8x"

# Plato status text that marks an appointment as not happening (booking.py and
# the BI marts use the same set).
_DEAD_STATUSES = {"cancelled", "canceled", "no_show", "noshow", "no-show"}

# Webhook-driven Plato reads share the bulk budget with the 5-minute snapshot
# and the patient webhook, so they get their own small allowance. An
# appointment over it waits for the sweep.
READS_PER_MIN = int(os.environ.get("CONFIRMATIONS_READS_PER_MIN", "4"))
READ_MAX_WAIT_S = 5.0
BQ_WAIT_S = 10.0
# A send that failed this many times for the same start time is left alone
# (the failures are in the ledger for someone to look at).
MAX_FAILURES = 3
# At most this many emails per sweep run, so one run can't spend the Plato
# budget on registration links or hit Gmail's sending limits.
SWEEP_MAX = 20
SWEEP_MIN_INTERVAL_S = float(os.environ.get("CONFIRMATIONS_SWEEP_MIN_INTERVAL", "240"))


def mode() -> str:
    m = os.environ.get("CONFIRMATIONS_MODE", "off").strip().lower()
    return m if m in ("off", "test", "live") else "off"


def test_to() -> str:
    return os.environ.get("CONFIRMATIONS_TEST_TO", "").strip()


def since() -> str:
    """Creation cutoff as 'YYYY-MM-DD HH:MM:SS' clinic time, or '' if unset."""
    raw = os.environ.get("CONFIRMATIONS_SINCE", "").strip()
    try:
        return datetime.fromisoformat(raw).strftime("%Y-%m-%d %H:%M:%S") if raw else ""
    except ValueError:
        log.warning("CONFIRMATIONS_SINCE is not a date and time; webhook and sweep stay off")
        return ""


def enabled() -> bool:
    """The new email is being built (test or live) and has somewhere to go."""
    m = mode()
    return m == "live" or (m == "test" and bool(test_to()))


def legacy_customer_email() -> bool:
    """Whether website/WhatsApp bookings still get mailer's old confirmation."""
    return mode() != "live"


def delivered_status() -> str:
    """The ledger status that counts as 'this patient has their email'."""
    return "sent" if mode() == "live" else "test"


# --- the appointment, as the email needs it -----------------------------------

@dataclass
class Appointment:
    appointment_id: str
    start: datetime            # clinic wall clock, naive
    end: datetime
    service: str
    clinician: str
    home: bool
    name: str = ""
    email: str = ""
    phone: str = ""
    patient_id: str = ""
    address: str = ""
    created_on: str = ""       # 'YYYY-MM-DD HH:MM:SS' clinic time, '' if unknown
    confirmed: bool = False    # Plato code_Right 'qK8x': don't ask them to confirm again
    form_url: str = ""         # set by deliver when the registration form is owed

    @property
    def start_key(self) -> str:
        """What the ledger compares to spot a move."""
        return self.start.strftime("%Y-%m-%d %H:%M")

    @property
    def reference(self) -> str:
        # Same as create_booking: the visit id's last six characters.
        return "GOJI-" + self.appointment_id[-6:].upper()

    @property
    def first_name(self) -> str:
        parts = (self.name or "").split()
        return parts[0] if parts else "there"

    @property
    def is_test_patient(self) -> bool:
        return (self.name or "").strip().upper().startswith("ZZ ")


def _parse_dt(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def _truthy(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return bool(value)


def _address_from(description: str) -> str:
    """The 'Address: ...' line booking.py writes on a home visit."""
    for line in (description or "").splitlines():
        if line.strip().lower().startswith("address:"):
            return line.split(":", 1)[1].strip()
    return ""


def from_plato(appt: dict) -> Appointment | None:
    """An Appointment from a Plato appointment record, or None when it isn't a
    patient session that's going ahead (cancelled, travel leg, lunch, block)."""
    if not isinstance(appt, dict):
        return None
    aid = str(appt.get("_id") or appt.get("id") or "").strip()
    start, end = _parse_dt(appt.get("starttime")), _parse_dt(appt.get("endtime"))
    if not aid or not start or not end:
        return None
    if _truthy(appt.get("cancelled")) or _truthy(appt.get("void")):
        return None
    if str(appt.get("status") or "").strip().lower() in _DEAD_STATUSES:
        return None
    pid = str(appt.get("patient_id") or "").strip()
    email = str(appt.get("email") or "").strip()
    phone = str(appt.get("handphone") or "").strip()
    if not (pid or email or phone):
        return None  # travel legs, lunches, blocks: no patient on them
    code = str(appt.get("code_Bottom") or "").strip()
    cid = clinician_by_calendar(str(appt.get("color") or ""))
    return Appointment(
        appointment_id=aid, start=start, end=end,
        service=SERVICE_WORDS.get(code, "Appointment"),
        clinician=CLINICIANS[cid]["name"] if cid else "",
        home=code == HOME_VISIT_TYPE_CODE,
        name=" ".join(str(appt.get("title") or "").split()),
        email=email, phone=phone, patient_id=pid,
        address=_address_from(str(appt.get("description") or "")),
        created_on=str(appt.get("created_on") or "").strip(),
        confirmed=str(appt.get("code_Right") or "").strip() == CONFIRMED_CODE)


def from_booking(result: dict, draft: dict) -> Appointment | None:
    """An Appointment from create_booking's result and the booking draft."""
    aid = str(result.get("visit_id") or "").strip()
    start = _parse_dt(f"{result.get('date')} {result.get('time')}")
    if not aid or not start:
        return None
    minutes = int(result.get("duration_min") or 60)
    service = result.get("service") or "Appointment"
    if result.get("physio_focus"):
        service = f"{service} ({result['physio_focus']})"
    return Appointment(
        appointment_id=aid, start=start, end=start + timedelta(minutes=minutes),
        service=service, clinician=result.get("clinician_name") or "",
        home=bool(result.get("home")),
        name=" ".join(str(draft.get("name") or "").split()),
        email=str(draft.get("email") or "").strip(),
        phone=str(draft.get("phone") or "").strip(),
        patient_id=str(result.get("patient_id") or "").strip(),
        address=str(draft.get("address") or "").strip())


# --- links ---------------------------------------------------------------------

def confirm_url(appointment_id: str, db: str = PLATO_DB) -> str:
    """Plato's Confirm Appointment page for this appointment: the same link
    Plato's own emails carry (the database name, base64, then the id)."""
    token = base64.b64encode(db.encode()).decode()
    return f"https://clinic.platomedical.com/appointment_confirm/{token}/{appointment_id}"


# The last step of Plato's registration form: the patient signs this consent,
# stored on the profile as others.consents[]. Signed = registration done.
# Same flag as the 48-hour reminder (reminders/registration.py) and the
# nightly import (dim_patient.consent_signed_at).
CONSENT_TITLE = "Clinic Consent Form"


def consent_signed(patient: dict) -> bool:
    others = patient.get("others")
    consents = others.get("consents") if isinstance(others, dict) else None
    return any(isinstance(c, dict) and c.get("title") == CONSENT_TITLE
               and isinstance(c.get("created_on"), (int, float)) and c["created_on"] > 0
               for c in consents or [])


def registration_link(plato, bq, appt: Appointment) -> str | None:
    """Our form link (formlink.py) for a NEW patient: one with no Plato profile
    yet, none on the appointment and none matching the phone or email. They
    get Plato's pre-registration form, which creates the profile. A patient
    with a profile is never asked (clinic decision, 26 Nov 2026: gaps in an
    existing profile are fixed in person; Plato's update form for existing
    profiles needs a login with a one-time code). Never raises; any doubt =
    no form."""
    if not INTERNAL_TOKEN:
        return None
    try:
        profile, _signed = profile_and_consent(bq, appt)
    except Exception as e:
        log.warning("registration check skipped (%s): %s", appt.appointment_id, e)
        return None
    if profile:
        return None
    return formlink.url(appt.appointment_id, INTERNAL_TOKEN) or None


def form_destination(plato, appointment_id: str) -> tuple[str, str | None]:
    """Where a tap on the form link goes: ('form', Plato's pre-registration
    URL) while the appointment has no profile, ('done', None) once it has one
    (the patient submitted the form, or staff linked them), or ('gone', None)
    when the appointment no longer exists. Raises on a Plato failure."""
    appt = one_record(plato.get(f"/appointment/{appointment_id}", max_wait_s=READ_MAX_WAIT_S,
                                _retries=1))
    if not appt:
        return "gone", None
    if str(appt.get("patient_id") or "").strip():
        return "done", None
    r = plato.get(f"/appointment/{appointment_id}/prereg", max_wait_s=READ_MAX_WAIT_S,
                  _retries=1)
    url = r.get("url") if isinstance(r, dict) else None
    if isinstance(url, str) and url.startswith("https://"):
        return "form", url
    # Plato refuses prereg once the appointment is linked: read it again.
    appt = one_record(plato.get(f"/appointment/{appointment_id}",
                                max_wait_s=READ_MAX_WAIT_S, _retries=1)) or {}
    if str(appt.get("patient_id") or "").strip():
        return "done", None
    raise RuntimeError("no pre-registration link")


# --- rendering -----------------------------------------------------------------

def _clock(t: datetime) -> str:
    """'10:00am', '2:30pm'."""
    return f"{t.hour % 12 or 12}:{t.minute:02d}{'am' if t.hour < 12 else 'pm'}"


def subject(appt: Appointment, kind: str) -> str:
    verb = "Moved" if kind == "moved" else "Booked"
    return f"{verb}: {appt.service}, {appt.start.strftime('%a %-d %b')} at {_clock(appt.start)}"


def _details(appt: Appointment) -> list[tuple[str, str]]:
    rows = [("Service", appt.service),
            ("When", f"{appt.start.strftime('%A, %-d %B %Y')}, {_clock(appt.start)} "
                     f"(Singapore time)")]
    if appt.clinician:
        rows.append(("With", appt.clinician))
    rows.append(("Reference", appt.reference))
    return rows


def _intro(appt: Appointment, kind: str) -> str:
    if kind == "moved":
        return "Your appointment at Goji Physiotherapy has moved. Here are the new details."
    return "You're booked in at Goji Physiotherapy. Here are the details."


def _where_lines(appt: Appointment) -> list[str]:
    if appt.home:
        where = appt.address or "the address you gave us"
        return [f"Your physiotherapist will come to {where}.",
                "Please WhatsApp us anything that helps us find you on time, such as "
                "parking instructions or landmarks."]
    return [CLINIC_ADDRESS, CLINIC_ADDRESS_NOTE,
            f"Getting here: {GETTING_HERE_LINK}", f"Google Maps: {MAPS_LINK}"]


def render_text(appt: Appointment, kind: str, form_url: str | None) -> str:
    lines = [f"Hi {appt.first_name},", "", _intro(appt, kind), ""]
    lines += [f"{label + ':':<11}{value}" for label, value in _details(appt)]
    if appt.confirmed:
        lines += ["", "You've confirmed this appointment. Thank you!", ""]
    else:
        lines += ["", "Please confirm your appointment:", confirm_url(appt.appointment_id), ""]
    if form_url:
        lines += ["New to Goji? Please fill in your registration form before your visit:",
                  form_url, ""]
    lines += ["Home visit" if appt.home else "Where", *_where_lines(appt), ""]
    lines += ["Changes and cancellations", POLICY,
              f"To change or cancel, WhatsApp us on {WHATSAPP_NUMBER}:", WHATSAPP_LINK, ""]
    lines += ["This appointment is in the attached calendar invite.", "",
              "See you soon,", "Team Goji Physiotherapy"]
    return "\n".join(lines)


_BTN = ("display:inline-block;padding:10px 18px;border-radius:6px;font-weight:bold;"
        "text-decoration:none;font-size:14px;")


def render_html(appt: Appointment, kind: str, form_url: str | None) -> str:
    """HTML twin of render_text. Inline styles only: mail clients drop <style>."""
    rows = "".join(
        f'<tr><td style="padding:3px 18px 3px 0;color:#666;vertical-align:top;'
        f'white-space:nowrap">{escape(label)}</td><td style="padding:3px 0;'
        f'vertical-align:top">{escape(value)}</td></tr>'
        for label, value in _details(appt))
    if appt.confirmed:
        confirm_block = ('<p style="margin:20px 0 0">You\'ve confirmed this appointment. '
                         'Thank you!</p>')
    else:
        confirm_block = (f'<p style="margin:20px 0 0"><a href="'
                         f'{escape(confirm_url(appt.appointment_id))}" style="{_BTN}'
                         f'background:#1f5f4a;color:#fff">Confirm appointment</a></p>')
    form = ""
    if form_url:
        form = (f'<p style="margin:20px 0 6px">New to Goji? Please fill in your '
                f'registration form before your visit.</p><p style="margin:0">'
                f'<a href="{escape(form_url)}" style="{_BTN}background:#fff;color:#1f5f4a;'
                f'border:1px solid #1f5f4a">Registration form</a></p>')
    if appt.home:
        where_title = "Home visit"
        where = "<br>".join(escape(line) for line in _where_lines(appt))
    else:
        where_title = "Where"
        where = (f"{escape(CLINIC_ADDRESS)}<br>{escape(CLINIC_ADDRESS_NOTE)}<br>"
                 f'<a href="{escape(GETTING_HERE_LINK)}">Getting here</a> &middot; '
                 f'<a href="{escape(MAPS_LINK)}">Google Maps</a>')
    wa = escape(WHATSAPP_LINK)
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;'
        'line-height:1.5;color:#222;max-width:560px">'
        f"<p>Hi {escape(appt.first_name)},</p><p>{escape(_intro(appt, kind))}</p>"
        f'<table role="presentation" cellspacing="0" cellpadding="0" '
        f'style="border-collapse:collapse;font-size:14px">{rows}</table>'
        f"{confirm_block}{form}"
        f'<p style="margin:24px 0 4px;font-weight:bold">{where_title}</p><p style="margin:0">{where}</p>'
        f'<p style="margin:24px 0 4px;font-weight:bold">Changes and cancellations</p>'
        f'<p style="margin:0">{escape(POLICY)}<br>To change or cancel, WhatsApp us on '
        f'<a href="{wa}">{escape(WHATSAPP_NUMBER)}</a>.</p>'
        '<p style="margin:24px 0 0">This appointment is in the attached calendar invite.</p>'
        '<p>See you soon,<br>Team Goji Physiotherapy</p></div>')


# --- calendar invite -------------------------------------------------------------

def _ics_text(value: str) -> str:
    return (value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> str:
    """RFC 5545 line folding: at most 75 octets a line, continuation lines
    start with a space."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode()
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode())
            cur = b""
        cur += b
    out.append(cur.decode())
    return "\r\n ".join(out)


def build_ics(appt: Appointment, *, sequence: int, now: datetime | None = None) -> str:
    """A METHOD:REQUEST invite so mail clients put it in the calendar. The UID is
    the Plato appointment id for life, so a move (higher SEQUENCE) updates the
    same entry. No VALARM and RSVP=FALSE: the clinic wants the entry in the
    patient's calendar with no alerts and no replies."""
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fmt = "%Y%m%dT%H%M%S"
    title = f"{'Home visit: ' if appt.home else ''}{appt.service} at Goji Physiotherapy"
    location = (appt.address or "Home visit") if appt.home else f"Goji Physiotherapy, {CLINIC_ADDRESS}"
    desc = [f"Reference: {appt.reference}"]
    if appt.clinician:
        desc.insert(0, f"With {appt.clinician}")
    desc += [f"Confirm your appointment: {confirm_url(appt.appointment_id)}",
             f"Changes or cancellations: WhatsApp {WHATSAPP_NUMBER} ({WHATSAPP_LINK})",
             POLICY]
    attendee = appt.email or "patient@invalid"
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Goji Physiotherapy//Bookings//EN",
        "CALSCALE:GREGORIAN", "METHOD:REQUEST",
        "BEGIN:VTIMEZONE", "TZID:Asia/Singapore",
        "BEGIN:STANDARD", "DTSTART:19700101T000000", "TZOFFSETFROM:+0800",
        "TZOFFSETTO:+0800", "TZNAME:+08", "END:STANDARD", "END:VTIMEZONE",
        "BEGIN:VEVENT",
        f"UID:{appt.appointment_id}@gojiphysio.com",
        f"SEQUENCE:{sequence}",
        f"DTSTAMP:{stamp}",
        # Plato's times are clinic wall clock: written as-is with the clinic's
        # zone, never converted (the 8-hour trap in stg/03_appointments.sql).
        f"DTSTART;TZID=Asia/Singapore:{appt.start.strftime(fmt)}",
        f"DTEND;TZID=Asia/Singapore:{appt.end.strftime(fmt)}",
        f"SUMMARY:{_ics_text(title)}",
        f"LOCATION:{_ics_text(location)}",
        f"DESCRIPTION:{_ics_text(chr(10).join(desc))}",
        f"ORGANIZER;CN=Goji Physiotherapy:mailto:{SMTP_USER}",
        f"ATTENDEE;CN={_ics_text(appt.name or 'Patient')};ROLE=REQ-PARTICIPANT;"
        f"PARTSTAT=ACCEPTED;RSVP=FALSE:mailto:{attendee}",
        "STATUS:CONFIRMED", "TRANSP:OPAQUE",
        "END:VEVENT", "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def build_message(appt: Appointment, *, to: str, kind: str, sequence: int,
                  form_url: str | None, now: datetime | None = None) -> EmailMessage:
    msg = EmailMessage()
    subj = subject(appt, kind)
    if to.lower() != (appt.email or "").lower():
        subj = f"[TEST] {subj}"  # never mistaken for the patient's own copy
    msg["Subject"] = subj
    msg["From"] = formataddr((FROM_NAME, SMTP_USER))
    msg["To"] = to
    msg["Reply-To"] = SMTP_USER
    msg["Message-ID"] = make_msgid(domain="gojiphysio.com")
    msg.set_content(render_text(appt, kind, form_url))
    msg.add_alternative(render_html(appt, kind, form_url), subtype="html")
    ics = build_ics(appt, sequence=sequence, now=now)
    # The text/calendar part inside the alternative is what makes Gmail,
    # Outlook and Apple Mail treat it as an invite; the attachment is for
    # clients that only look at attachments.
    msg.add_alternative(ics, subtype="calendar", params={"method": "REQUEST"})
    msg.add_attachment(ics.encode(), maintype="application", subtype="ics",
                       filename="goji-appointment.ics")
    return msg


def _send(msg: EmailMessage) -> None:
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)


# --- ledger + lookups (BigQuery) --------------------------------------------------

def _params(**values):
    from google.cloud import bigquery
    return bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter(k, "INT64" if isinstance(v, int) else "STRING", v)
        for k, v in values.items()])


def _rows(bq, sql: str, **params) -> list[dict]:
    return [dict(r) for r in bq.query(sql, job_config=_params(**params)).result(timeout=BQ_WAIT_S)]


def last_delivered(bq, appointment_id: str) -> tuple[str, int] | None:
    """(start_key, sequence) of the last email this appointment got, or None."""
    rows = _rows(bq, f"""
        SELECT start_key, sequence FROM `{LEDGER_TABLE}`
        WHERE appointment_id = @aid AND status = @status
        ORDER BY sent_at DESC LIMIT 1""", aid=appointment_id, status=delivered_status())
    return (rows[0]["start_key"], int(rows[0]["sequence"] or 0)) if rows else None


def failures(bq, appointment_id: str, start_key: str) -> int:
    rows = _rows(bq, f"""
        SELECT COUNT(*) AS n FROM `{LEDGER_TABLE}`
        WHERE appointment_id = @aid AND start_key = @start AND status = 'failed'""",
                 aid=appointment_id, start=start_key)
    return int(rows[0]["n"]) if rows else 0


def hydrate(bq, appt: Appointment) -> None:
    """Fill a linked appointment's name, email and phone from the patient's
    profile (staff often leave them off the appointment itself)."""
    if not appt.patient_id or (appt.email and appt.name and appt.phone):
        return
    rows = _rows(bq, f"SELECT full_name, email, phone FROM `{CONTACT_TABLE}` "
                     "WHERE patient_id = @pid", pid=appt.patient_id)
    if rows:
        appt.email = appt.email or (rows[0].get("email") or "").strip()
        appt.phone = appt.phone or (rows[0].get("phone") or "").strip()
        appt.name = (rows[0].get("full_name") or "").strip() or appt.name


def profile_and_consent(bq, appt: Appointment) -> tuple[str, bool]:
    """(the patient's profile id or '', whether it has a signed consent as of
    last night). The profile is the appointment's own, else one matching the
    phone or email (a returning patient booking on the website); several
    matches prefer one that has signed. Raises on a failed query."""
    digits = "".join(ch for ch in appt.phone if ch.isdigit())[-8:]
    rows = _rows(bq, f"""
        SELECT m.patient_id, d.consent_signed_at IS NOT NULL AS signed
        FROM `{CONTACT_TABLE}` m
        LEFT JOIN `{PATIENT_TABLE}` d USING (patient_id)
        WHERE (@pid != '' AND m.patient_id = @pid)
           OR (@pid = '' AND ((@digits != '' AND RIGHT(REGEXP_REPLACE(
                 COALESCE(m.phone, ''), r'\\D', ''), 8) = @digits)
              OR (@email != '' AND LOWER(m.email) = @email)))
        ORDER BY signed DESC, m.patient_id
        LIMIT 1""", pid=appt.patient_id, digits=digits, email=appt.email.lower())
    if rows:
        return rows[0]["patient_id"], bool(rows[0]["signed"])
    return appt.patient_id, False


def record(bq, appt: Appointment, *, status: str, kind: str, sequence: int,
           source: str, channel: str = "email", note: str | None = None) -> None:
    """One ledger row. Never raises; never writes an address or a name."""
    try:
        bq.query(f"""
            INSERT INTO `{LEDGER_TABLE}` (event_id, appointment_id, start_key, sequence,
              kind, status, source, channel, note, sent_at)
            VALUES (@eid, @aid, @start, @seq, @kind, @status, @source, @channel, @note,
                    CURRENT_TIMESTAMP())""",
                 job_config=_params(eid=str(uuid.uuid4()), aid=appt.appointment_id,
                                    start=appt.start_key, seq=sequence, kind=kind,
                                    status=status, source=source, channel=channel,
                                    note=(note or "")[:300])).result(timeout=BQ_WAIT_S)
    except Exception as e:
        log.error("confirmation ledger write failed (%s, %s): %s",
                  appt.appointment_id, status, e)


# --- sending ---------------------------------------------------------------------

_send_lock = threading.Lock()


def deliver(plato, bq, appt: Appointment, *, kind: str, sequence: int, source: str,
            now: datetime | None = None, whatsapp: bool = False) -> str:
    """Send this appointment's email and, with `whatsapp` (a front-desk
    booking: no other path tells the assistant), ask the WhatsApp assistant to
    confirm it there too. One ledger row either way. Returns the status."""
    if mode() == "live":
        to = appt.email
        if appt.is_test_patient:
            to = test_to()  # the ZZ test patient only ever mails the test inbox
    else:
        to = test_to()
    emailed, form, err = None, None, None
    if to:
        form = registration_link(plato, bq, appt) if kind == "booked" else None
        appt.form_url = form or ""
        try:
            if not SMTP_PASS:
                raise RuntimeError("SMTP not configured (no GMAIL_APP_PASSWORD)")
            _send(build_message(appt, to=to, kind=kind, sequence=sequence, form_url=form,
                                now=now))
            emailed = True
        except Exception as e:
            log.warning("confirmation email failed (%s): %s", appt.appointment_id, e)
            emailed, err = False, "email failed: " + str(e).replace(to, "<to>")
    if whatsapp and kind == "booked" and not to:
        # No email went out, so the form check hasn't run: the WhatsApp
        # confirmation still needs to know whether to carry the form button.
        appt.form_url = registration_link(plato, bq, appt) or ""
    whatsapped = bool(whatsapp) and notify_whatsapp(appt)
    if emailed or whatsapped:
        status = delivered_status()
    else:
        status = "failed" if emailed is False else "skipped_no_email"
    channel = ("both" if emailed and whatsapped else "email" if emailed
               else "whatsapp" if whatsapped else "none")
    notes = [n for n in (err, "registration form" if appt.form_url else None) if n]
    record(bq, appt, status=status, kind=kind, sequence=sequence, source=source,
           channel=channel, note="; ".join(notes) or None)
    log.info("confirmation %s (%s, %s, %s, %s)", status, appt.appointment_id, kind, source,
             channel)
    return status


WA_AGENT_URL = os.environ.get("WA_AGENT_URL", "").strip()
INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN", "").strip()
WA_CALLBACK_TIMEOUT_S = 5.0


def notify_whatsapp(appt: Appointment) -> bool:
    """Tell the WhatsApp assistant about a front-desk booking, with the
    go-ahead to send the approved confirmation template (its kill switch,
    go-live and Chris's paused chats still apply there). Live mode only: in
    test mode nothing reaches a patient. Same callback and body as
    app._notify_wa_agent. True when the assistant took it."""
    if mode() != "live" or not (WA_AGENT_URL and INTERNAL_TOKEN and appt.phone):
        return False
    import requests
    body = {"phone": appt.phone, "reference": appt.reference, "service": appt.service,
            "date": appt.start.date().isoformat(), "time": appt.start.strftime("%H:%M"),
            "clinician_name": appt.clinician, "source": "staff", "home": appt.home,
            "first_name": appt.first_name if appt.name else "", "send_template": True,
            # The registration-form button, when the form is still owed.
            "form_token": formlink.token(appt.appointment_id, INTERNAL_TOKEN)
            if appt.form_url else ""}
    try:
        r = requests.post(WA_AGENT_URL.rstrip("/") + "/internal/booking-confirmed", json=body,
                          timeout=WA_CALLBACK_TIMEOUT_S,
                          headers={"X-Internal-Token": INTERNAL_TOKEN})
        return r.status_code < 300
    except Exception as e:
        log.warning("whatsapp confirmation callback failed (%s): %s", appt.appointment_id, e)
        return False


def on_booking(plato, bq, result: dict, draft: dict, *, source: str) -> str | None:
    """A booking goji-booking just wrote to Plato. Best effort: never raises."""
    if not enabled() or result.get("dry_run"):
        return None
    try:
        appt = from_booking(result, draft)
        if appt is None:
            log.warning("confirmation: booking result has no visit id (%s)", result.get("reference"))
            return None
        with _send_lock:
            status = deliver(plato, bq, appt, kind="booked", sequence=0, source=source)
        # The WhatsApp callback (app._notify_wa_agent) carries the form button
        # when the email found the form owed.
        if appt.form_url:
            result["form_token"] = formlink.token(appt.appointment_id, INTERNAL_TOKEN)
        return status
    except Exception as e:
        log.warning("confirmation for booking %s failed: %s", result.get("reference"), e)
        return None


def on_plato_appointment(plato, bq, record_: dict, *, source: str,
                         now: datetime | None = None) -> str | None:
    """An appointment as Plato holds it (webhook, sweep, reschedule): send the
    first confirmation, a "moved" one after a time change, or nothing. The
    ledger is read under the send lock, so the webhook and the sweep can't
    both send for the same change."""
    appt = from_plato(record_)
    if appt is None:
        return None
    cutoff = since()
    if not cutoff or not appt.created_on or appt.created_on < cutoff:
        return None
    clinic_now = now or datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)
    if appt.start <= clinic_now:
        return None
    with _send_lock:
        last = last_delivered(bq, appt.appointment_id)
        if last is None:
            kind, seq = "booked", 0
        elif last[0] == appt.start_key:
            return None  # already has its email
        else:
            kind, seq = "moved", last[1] + 1
        if failures(bq, appt.appointment_id, appt.start_key) >= MAX_FAILURES:
            return None
        hydrate(bq, appt)
        # A front-desk booking (the webhook or the sweep found it) is the one
        # path where nothing else tells the WhatsApp assistant. Moves by staff
        # get the email only.
        whatsapp = (kind == "booked" and source in ("staff", "sweep") and mode() == "live"
                    and bool(WA_AGENT_URL and INTERNAL_TOKEN))
        if not appt.email and not (whatsapp and appt.phone):
            return None  # nobody to write to; nothing to ledger
        return deliver(plato, bq, appt, kind=kind, sequence=seq, source=source,
                       whatsapp=whatsapp)


def on_reschedule(plato, bq, result: dict) -> str | None:
    """The WhatsApp assistant moved an appointment (an API write, so no webhook).
    Reads it back from Plato and sends the "moved" email. Never raises."""
    if not enabled() or result.get("dry_run") or not result.get("appointment_id"):
        return None
    try:
        rec = one_record(plato.get(f"/appointment/{result['appointment_id']}",
                                   max_wait_s=READ_MAX_WAIT_S, _retries=0))
        return on_plato_appointment(plato, bq, rec or {}, source="whatsapp")
    except Exception as e:
        log.warning("confirmation for reschedule %s failed: %s", result.get("reference"), e)
        return None


# --- staff bookings: webhook + sweep ---------------------------------------------

MAX_APPOINTMENTS_PER_DELIVERY = 20


def webhook_appointment_ids(payload: object, db: str = PLATO_DB) -> list[str]:
    """appointment:upsert ids from a Plato webhook delivery."""
    ids: list[str] = []
    events = payload.get("events") if isinstance(payload, dict) else None
    for e in events if isinstance(events, list) else []:
        if not isinstance(e, dict) or e.get("db") != db or e.get("event") != "appointment:upsert":
            continue
        aid = e.get("object_id")
        if isinstance(aid, str) and aid.replace("-", "").isalnum() and len(aid) <= 64 \
                and aid not in ids:
            ids.append(aid)
    return ids[:MAX_APPOINTMENTS_PER_DELIVERY]


_reads: deque[float] = deque()
_reads_lock = threading.Lock()


def _take_read(now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    with _reads_lock:
        while _reads and now - _reads[0] >= 60:
            _reads.popleft()
        if len(_reads) >= READS_PER_MIN:
            return False
        _reads.append(now)
        return True


def handle_webhook(plato, bq, ids: list[str]) -> int:
    """Read each upserted appointment from Plato and confirm it if it needs it.
    Over the read cap, it waits for the sweep. Returns emails sent."""
    if not enabled() or not since():
        return 0
    sent = 0
    for aid in ids:
        if not _take_read():
            log.info("confirmations: appointment %s over the read cap, left to the sweep", aid)
            continue
        try:
            # Priority share, not bulk: the first staff booking after go-live
            # (26 Nov 2026) failed here because the availability refresh held
            # the bulk share. READS_PER_MIN keeps these from crowding the
            # website's own reads.
            rec = one_record(plato.get(f"/appointment/{aid}",
                                       max_wait_s=READ_MAX_WAIT_S, _retries=0))
        except Exception as e:
            log.warning("confirmations: appointment read failed: %s", e)
            continue
        if rec is not None and on_plato_appointment(plato, bq, rec, source="staff") \
                in ("sent", "test"):
            sent += 1
    return sent


# Appointments created since the cutoff, still ahead, with an email somewhere,
# whose last email (if any) was for another start time. stg.appointments holds
# the newest version of each appointment from the 15-minute ingestion; the
# freshness guard drops ones deleted in Plato (same guard as the reminder view).
_SWEEP_SQL = """
WITH fresh AS (
  SELECT TIMESTAMP_SUB(MAX(_loaded_at), INTERVAL 30 MINUTE) AS min_loaded_at
  FROM `{appts}`
), last_sent AS (
  SELECT appointment_id,
         ARRAY_AGG(STRUCT(start_key, sequence) ORDER BY sent_at DESC LIMIT 1)[OFFSET(0)] AS l
  FROM `{ledger}` WHERE status = @status GROUP BY appointment_id
)
SELECT a.appointment_id, TO_JSON_STRING(a.payload) AS payload
FROM `{appts}` a
CROSS JOIN fresh f
LEFT JOIN last_sent s USING (appointment_id)
LEFT JOIN `{contacts}` c ON c.patient_id = a.patient_id AND a.patient_id != ''
WHERE a._loaded_at >= f.min_loaded_at
  AND a.created_on >= TIMESTAMP(@since)
  AND a.start_at > TIMESTAMP(@now)
  AND (COALESCE(JSON_VALUE(a.payload, '$.email'), '') != '' OR COALESCE(c.email, '') != ''
       OR COALESCE(JSON_VALUE(a.payload, '$.handphone'), '') != '' OR COALESCE(c.phone, '') != '')
  AND (s.appointment_id IS NULL OR s.l.start_key != FORMAT_TIMESTAMP('%Y-%m-%d %H:%M', a.start_at, 'UTC'))
ORDER BY a.start_at
LIMIT @limit
"""

_last_sweep = 0.0
_sweep_lock = threading.Lock()


def sweep(plato, bq, now: datetime | None = None) -> dict:
    """Confirm whatever the webhook missed. Self-throttled; safe to call often."""
    global _last_sweep
    if not enabled() or not since():
        return {"ok": True, "skipped": "off"}
    with _sweep_lock:
        if time.monotonic() - _last_sweep < SWEEP_MIN_INTERVAL_S:
            return {"ok": True, "skipped": "throttled"}
        _last_sweep = time.monotonic()
    import json
    clinic_now = now or datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)
    rows = _rows(bq, _SWEEP_SQL.format(appts=APPOINTMENTS_VIEW, ledger=LEDGER_TABLE,
                                       contacts=CONTACT_TABLE),
                 status=delivered_status(), since=since(),
                 now=clinic_now.strftime("%Y-%m-%d %H:%M:%S"), limit=SWEEP_MAX)
    counts: dict[str, int] = {}
    for r in rows:
        try:
            rec = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
            status = on_plato_appointment(plato, bq, rec, source="sweep", now=now)
        except Exception as e:
            log.warning("confirmations sweep: %s failed: %s", r.get("appointment_id"), e)
            status = "error"
        counts[status or "none"] = counts.get(status or "none", 0) + 1
    return {"ok": True, "candidates": len(rows), **counts}
