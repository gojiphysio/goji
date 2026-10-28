"""
Booking-notification emails — best-effort, never break a booking.

Two messages, both sent via Gmail SMTP as hello@gojiphysio.com (Google
Workspace) using an app password from Secret Manager:
  - send_admin_booking_email:    internal heads-up to the clinic (hello@).
  - send_customer_booking_email: confirmation to the person who booked.

The customer also gets Plato's own confirmation (connect:true). We send our own
too so the confirmation is guaranteed and on-brand, independent of Plato's
template. If SMTP isn't configured or a send fails, we log and move on — the
booking has already succeeded.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from html import escape
from datetime import date, datetime
from email.message import EmailMessage
from email.utils import formataddr

log = logging.getLogger("booking.mailer")

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "hello@gojiphysio.com")
SMTP_PASS = os.environ.get("GMAIL_APP_PASSWORD")  # Secret Manager
ADMIN_TO = os.environ.get("BOOKING_ADMIN_EMAIL", "hello@gojiphysio.com")
FROM_NAME = os.environ.get("BOOKING_FROM_NAME", "Goji Physiotherapy")
# Tracked WhatsApp CTA (goes through the go.gojiphysio.com redirector).
WHATSAPP_LINK = os.environ.get("BOOKING_WA_LINK", "https://go.gojiphysio.com/web-wa")
# Clinic Google Maps listing, included in the confirmation for easy directions.
MAPS_LINK = os.environ.get("BOOKING_MAPS_LINK", "https://maps.app.goo.gl/fUnkD6QwYD8o5qnx9")


def _send(msg: EmailMessage, what: str, ref: str | None) -> None:
    """Send one message over Gmail SMTP; swallow + log any failure."""
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)
    log.info("%s email sent (ref %s)", what, ref)


def _row(label: str, value) -> str:
    """One aligned 'Label:   value' line for the plain-text booking emails."""
    return f"{label + ':':<19}{value}"


def _clinician_pairs(result: dict) -> list[tuple[str, str]]:
    """Two clear rows: what the customer selected vs. who they were matched to.
    Both are shown even when identical (an explicit clinician was requested)."""
    return [
        ("Your selection", result.get("clinician_requested")
         or result.get("clinician_name")),
        ("Clinician matched", result["clinician_name"]),
    ]


def _clinician_lines(result: dict) -> list[str]:
    return [_row(label, value) for label, value in _clinician_pairs(result)]


def _html_body(greeting: str, intro: str, details: list[tuple[str, str]],
               wa_intro: str, signoff: list[str]) -> str:
    """HTML twin of the plain-text confirmation. The details sit in a table so the
    values line up in any client (space-padding only aligns in a monospace font)."""
    rows = "".join(
        f'<tr><td style="padding:2px 16px 2px 0;vertical-align:top;white-space:nowrap">'
        f'{escape(label)}</td><td style="padding:2px 0;vertical-align:top">'
        f'{escape(str(value))}</td></tr>'
        for label, value in details)
    wa = escape(WHATSAPP_LINK)
    maps = escape(MAPS_LINK)
    sign = "<br>".join(escape(line) for line in signoff)
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;'
        'line-height:1.5;color:#222">'
        f"<p>{escape(greeting)}</p><p>{escape(intro)}</p>"
        f'<table role="presentation" cellspacing="0" cellpadding="0" '
        f'style="border-collapse:collapse;font-size:14px">{rows}</table>'
        f'<p>{escape(wa_intro)}<br><a href="{wa}">{wa}</a></p>'
        f"<p>See you soon,<br>{sign}<br>"
        f'Find us on Google Maps: <a href="{maps}">{maps}</a></p></div>')


def _fmt_when(date_str: str, time_str: str) -> str:
    """'2026-07-15' + '09:00' -> 'Wednesday, 15 July 2026 at 9:00 am'."""
    try:
        d = date.fromisoformat(date_str)
        t = datetime.strptime(time_str, "%H:%M")
    except (ValueError, TypeError):
        return f"{date_str} {time_str}"
    hour12 = t.hour % 12 or 12
    ampm = "am" if t.hour < 12 else "pm"
    day = d.strftime("%A, %-d %B %Y")
    return f"{day} at {hour12}:{t.minute:02d} {ampm}"


def send_admin_booking_email(result: dict, draft: dict) -> None:
    if not SMTP_PASS:
        log.info("SMTP not configured (no GMAIL_APP_PASSWORD); skipping admin email")
        return
    try:
        where = "Home visit" if result.get("home") else "In-clinic"
        msg = EmailMessage()
        msg["Subject"] = (f"New website booking — {result['service']} "
                          f"({result['date']} {result['time']})")
        msg["From"] = SMTP_USER
        msg["To"] = ADMIN_TO
        # CC the matched clinician so the assigned physio sees their own booking.
        cc = result.get("clinician_email")
        if cc:
            msg["Cc"] = cc
        lines = [
            "A new booking came in via the website:",
            "",
            _row("Service", result['service']),
        ]
        if result.get("physio_focus"):
            lines.append(_row("Type", result['physio_focus']))
        lines += [
            _row("When", f"{result['date']} {result['time']} (SGT)"),
            _row("Where", where),
            *_clinician_lines(result),
            _row("Name", draft.get('name')),
            _row("Phone", draft.get('phone')),
            _row("Email", draft.get('email')),
        ]
        if result.get("home"):
            lines.append(_row("Address", draft.get('address')))
        if (draft.get("notes") or "").strip():
            lines.append(_row("Condition", draft.get('notes').strip()))
        lines += [_row("Reference", result['reference']), "",
                  "The customer has been sent Plato's confirmation. Changes and "
                  "cancellations are handled over WhatsApp."]
        msg.set_content("\n".join(lines))
        _send(msg, "admin booking", result.get("reference"))
    except Exception as e:
        log.warning("admin booking email failed: %s", e)


def send_customer_booking_email(result: dict, draft: dict) -> None:
    """Confirmation to the person who booked. Best-effort; HTML (aligned table) with a plain-text fallback."""
    to = (draft.get("email") or "").strip()
    if not SMTP_PASS:
        log.info("SMTP not configured (no GMAIL_APP_PASSWORD); skipping customer email")
        return
    if not to:
        log.warning("no customer email on booking %s; skipping", result.get("reference"))
        return
    try:
        name = (draft.get("name") or "there").split()[0]
        where = "Home visit" if result.get("home") else "In-clinic at Goji Physiotherapy, Lentor Modern"
        when = _fmt_when(result.get("date", ""), result.get("time", ""))
        msg = EmailMessage()
        msg["Subject"] = f"Your Goji Physiotherapy booking - {when}"
        msg["From"] = formataddr((FROM_NAME, SMTP_USER))
        msg["To"] = to
        msg["Reply-To"] = SMTP_USER
        greeting = f"Hi {name},"
        intro = ("Thanks for booking with Goji Physiotherapy. We've received your "
                 "request and here are the details:")
        wa_intro = ("Need to change or cancel? Just message us on WhatsApp and we'll "
                    "take care of it - that's where we handle all changes and "
                    "cancellations:")
        signoff = ["The Goji Physiotherapy team",
                   "1 Lentor Central, #01-13, Lentor Modern, Singapore 788887"]
        details = [("Service", result['service'])]
        if result.get("physio_focus"):
            details.append(("Type", result['physio_focus']))
        details += [
            ("When", f"{when} (Singapore time)"),
            ("Where", where),
            *_clinician_pairs(result),
        ]
        if result.get("home") and draft.get("address"):
            details.append(("Address", draft.get('address')))
        if (draft.get("notes") or "").strip():
            details.append(("Remarks", draft.get('notes').strip()))
        details.append(("Reference", result['reference']))
        lines = [
            greeting, "", intro, "",
            *(_row(label, value) for label, value in details),
            "",
            wa_intro,
            f"  {WHATSAPP_LINK}",
            "",
            "See you soon,",
            *signoff,
            f"Find us on Google Maps: {MAPS_LINK}",
        ]
        msg.set_content("\n".join(lines))
        msg.add_alternative(
            _html_body(greeting, intro, details, wa_intro, signoff), subtype="html")
        _send(msg, "customer booking", result.get("reference"))
    except Exception as e:
        log.warning("customer booking email failed: %s", e)
