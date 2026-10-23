"""
48-hour appointment reminder emails — body rendering + Gmail SMTP.

Same transport as booking/mailer.py: Gmail SMTP as hello@gojiphysio.com (Google
Workspace) with an app password from Secret Manager. Plain text, on-brand.

This module is deliberately split into PURE rendering functions (render_*,
_fmt_*) and the one impure _send(). The renderers take primitives and return
strings, so the whole email body is unit-testable with no network and no BQ —
see test_reminders.py.

Content is the clinic's existing Plato reminder template, with two changes
agreed when this was automated:
  - Greeting is the patient's FIRST NAME ("Dear Sarah,") rather than Plato's
    "%title% %name%". The clinic chose this; don't "restore" the salutation.
    (Plato's patient record does carry a `title` field, but we deliberately
    don't ingest it — an appointment's own $.title is the appointment title,
    not a salutation, so it is not a substitute.) First name also matches how
    booking confirmations already greet people.
  - The clinic-directions block and the home-visit paragraph are chosen per
    appointment rather than both being sent to everyone.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from datetime import date, datetime
from email.message import EmailMessage
from email.utils import formataddr

log = logging.getLogger("reminders.mailer")

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "hello@gojiphysio.com")
SMTP_PASS = os.environ.get("GMAIL_APP_PASSWORD")  # Secret Manager
FROM_NAME = os.environ.get("REMINDER_FROM_NAME", "Goji Physiotherapy")
SUBJECT    = os.environ.get("REMINDER_SUBJECT", "Goji Appointment Reminder")
# Where the "couldn't reach these people" digest goes.
ADMIN_TO   = os.environ.get("REMINDER_ADMIN_EMAIL", "hello@gojiphysio.com")
# TEST MODE. When set, every patient reminder is rendered exactly as the patient
# would receive it but delivered HERE instead — a real end-to-end send (real
# names, times, grouping, SMTP) that reaches no patient. Unset in normal
# operation; when set it overrides the recipient unconditionally, so there is no
# path where a patient is mailed while this has a value.
OVERRIDE_TO = os.environ.get("REMINDER_OVERRIDE_TO", "").strip()

# Tracked WhatsApp CTA. Repo rule: every outbound customer CTA routes through the
# go.gojiphysio.com redirector so the click is logged and attributable — never a
# raw wa.me link. 'reminder-wa' is registered in LINK_SLUGS (dashboard/app.py),
# which is what makes reminder-driven WhatsApp traffic separable from web/IG/GBP.
WHATSAPP_LINK = os.environ.get("REMINDER_WA_LINK", "https://go.gojiphysio.com/reminder-wa")
WHATSAPP_NUMBER = os.environ.get("REMINDER_WA_NUMBER", "+6583770401")
CLINIC_ADDRESS = ("#01-13, Lentor Modern, Singapore 788887 "
                  "(Outer ring of the mall)")
GETTING_HERE_LINK = os.environ.get("REMINDER_GETTING_HERE_LINK",
                                   "https://www.gojiphysio.com/getting-here/")
MAPS_LINK = os.environ.get("REMINDER_MAPS_LINK",
                           "https://maps.app.goo.gl/H57dBGDMGrTcB5xk7")


# --- pure helpers ----------------------------------------------------------

def _fmt_time(time_str: str) -> str:
    """'09:00' -> '9:00 am'. Returns the input unchanged if unparseable."""
    try:
        t = datetime.strptime(time_str, "%H:%M")
    except (ValueError, TypeError):
        return time_str
    hour12 = t.hour % 12 or 12
    ampm = "am" if t.hour < 12 else "pm"
    return f"{hour12}:{t.minute:02d} {ampm}"


def _fmt_day(date_str: str) -> str:
    """'2026-09-12' -> 'Wednesday, 12 September 2026'."""
    try:
        d = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return date_str
    return d.strftime("%A, %-d %B %Y")


def fmt_when(date_str: str, times: list[str]) -> str:
    """Render the %datetime% slot for one or more same-day appointments.

    One appointment  -> 'Wednesday, 12 September 2026 at 9:00 am'
    Two              -> 'Wednesday, 12 September 2026 at 9:00 am and 2:00 pm'
    Three or more    -> '... at 9:00 am, 2:00 pm and 6:30 pm'

    A patient with several sessions on the same day gets ONE email listing them
    all, not one email per slot — see the grouping note in main.py.
    """
    day = _fmt_day(date_str)
    pretty = [_fmt_time(t) for t in times]
    if not pretty:
        return day
    if len(pretty) == 1:
        joined = pretty[0]
    else:
        joined = f"{', '.join(pretty[:-1])} and {pretty[-1]}"
    return f"{day} at {joined}"


def first_name(full_name: str | None) -> str:
    """'Sarah Tan' -> 'Sarah'. Falls back to 'there' so we never send 'Dear ,'.

    Same convention as booking/mailer.py's customer confirmation.
    """
    parts = (full_name or "").strip().split()
    return parts[0] if parts else "there"


def render_reminder_body(name: str | None, date_str: str, times: list[str],
                         *, has_clinic: bool, has_home_visit: bool) -> str:
    """The full plain-text reminder body.

    has_clinic / has_home_visit select the location block. Normally exactly one
    is true. Both can be true in the rare case a patient has an in-clinic session
    AND a home visit on the same day — then they get both blocks, which is the
    safe failure mode (the old Plato template always sent both anyway).
    """
    lines = [
        f"Dear {first_name(name)},",
        "",
        # Plural when the patient has more than one session that day.
        ("This is a gentle reminder for your upcoming "
         f"{'appointments' if len(times) > 1 else 'appointment'} with Goji "
         f"Physiotherapy on {fmt_when(date_str, times)}."),
        "",
        "Should you need to reschedule or cancel, please let us know at least "
        "24 hours in advance. A $50 fee will apply for cancellations made "
        "within 24 hours or missed appointments without prior notice.",
        "",
    ]
    if has_clinic:
        lines += [
            "You can find our location, parking information and directions below:",
            f"\U0001F4CD Address: {CLINIC_ADDRESS}",
            f"\U0001F9ED Locating Us: {GETTING_HERE_LINK}",
            f"\U0001F5FA️ Google Maps: {MAPS_LINK}",
            "",
        ]
    if has_home_visit:
        lines += [
            "For your home visit, your physiotherapist will meet you at the "
            "address confirmed during your booking. Please kindly provide "
            "additional directions that would help us reach you with ease and "
            "on time (e.g.: parking instructions, landmarks).",
            "",
        ]
    lines += [
        "For urgent enquiries, feel free to WhatsApp us directly at "
        f"{WHATSAPP_NUMBER}:",
        f"  {WHATSAPP_LINK}",
        "",
        "See you soon,",
        "Team Goji Physiotherapy",
    ]
    return "\n".join(lines)


def render_digest_body(sent: list[dict], skipped: list[dict],
                       failed: list[dict], target_date: str,
                       *, dry_run: bool) -> str:
    """The daily operations digest to hello@.

    Its real job is the `skipped` list: patients with no email on file, who the
    front desk still needs to reach on WhatsApp. Without this the gap would be
    invisible outside Cloud Run logs.
    """
    if dry_run:
        head = "DRY RUN — no patient emails were sent."
    elif OVERRIDE_TO:
        head = (f"TEST MODE — {OVERRIDE_TO} received every reminder. "
                "No patient was emailed.")
    else:
        head = ""
    verb = "Would have sent" if dry_run else "Sent"
    lines = [head, ""] if head else []
    lines += [
        f"Appointment reminders for {_fmt_day(target_date)}",
        "",
        f"{verb}: {len(sent)} reminder(s)",
    ]
    if skipped:
        lines += [
            "",
            f"Couldn't reach — no email on file ({len(skipped)}). "
            "Please WhatsApp these:",
        ]
        for r in sorted(skipped, key=lambda r: r.get("time") or ""):
            phone = r.get("phone") or "no phone either"
            lines.append(f"  {_fmt_time(r.get('time') or ''):>9}  "
                         f"{r.get('name') or '—'}  {phone}")
    if failed:
        lines += ["", f"Failed to send ({len(failed)}) — will retry next run:"]
        for r in failed:
            lines.append(f"  {r.get('name') or '—'}: {r.get('error') or 'unknown error'}")
    if sent:
        lines += ["", f"{verb} to:"]
        for r in sorted(sent, key=lambda r: r.get("time") or ""):
            lines.append(f"  {_fmt_time(r.get('time') or ''):>9}  {r.get('name') or '—'}")
    lines += ["", "— the appointment-reminders job"]
    return "\n".join(lines)


# --- transport -------------------------------------------------------------

def _send(msg: EmailMessage, what: str, ref: str | None) -> None:
    """Send one message over Gmail SMTP. Raises on failure — callers decide."""
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)
    log.info("%s email sent (ref %s)", what, ref)


def send_reminder(to: str, name: str | None, date_str: str, times: list[str],
                  *, has_clinic: bool, has_home_visit: bool,
                  ref: str | None = None) -> None:
    """Send one patient reminder. Raises on failure so the caller can ledger it.

    With REMINDER_OVERRIDE_TO set, the body is byte-identical to the patient's
    but the message goes to the override address, with the intended recipient in
    the subject so the clinic can check each one landed on the right person.
    """
    msg = EmailMessage()
    if OVERRIDE_TO:
        # Belt and braces: the recipient is replaced here, at the point of send,
        # so no caller can route around it.
        msg["Subject"] = f"[TEST -> {to}] {SUBJECT}"
        msg["To"] = OVERRIDE_TO
    else:
        msg["Subject"] = SUBJECT
        msg["To"] = to
    msg["From"] = formataddr((FROM_NAME, SMTP_USER))
    msg["Reply-To"] = SMTP_USER
    msg.set_content(render_reminder_body(
        name, date_str, times,
        has_clinic=has_clinic, has_home_visit=has_home_visit))
    _send(msg, "appointment reminder", ref)


def send_digest(sent: list[dict], skipped: list[dict], failed: list[dict],
                target_date: str, *, dry_run: bool) -> None:
    """Send the ops digest to the clinic. Best-effort — never fails the run."""
    try:
        msg = EmailMessage()
        prefix = "[DRY RUN] " if dry_run else ("[TEST] " if OVERRIDE_TO else "")
        msg["Subject"] = (f"{prefix}Appointment reminders — {_fmt_day(target_date)} "
                          f"({len(sent)} sent, {len(skipped)} unreachable)")
        msg["From"] = formataddr((FROM_NAME, SMTP_USER))
        msg["To"] = ADMIN_TO
        msg.set_content(render_digest_body(
            sent, skipped, failed, target_date, dry_run=dry_run))
        _send(msg, "reminder digest", target_date)
    except Exception as e:
        log.warning("reminder digest email failed: %s", e)
