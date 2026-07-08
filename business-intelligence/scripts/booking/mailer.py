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
        lines = [
            "A new booking came in via the website:",
            "",
            f"Service:   {result['service']}",
            f"When:      {result['date']} {result['time']} (SGT)",
            f"Where:     {where}",
            f"Clinician: {result['clinician_name']}",
            f"Name:      {draft.get('name')}",
            f"Phone:     {draft.get('phone')}",
            f"Email:     {draft.get('email')}",
        ]
        if result.get("home"):
            lines.append(f"Address:   {draft.get('address')}")
        if (draft.get("notes") or "").strip():
            lines.append(f"Condition: {draft.get('notes').strip()}")
        lines += [f"Reference: {result['reference']}", "",
                  "The customer has been sent Plato's confirmation. Changes and "
                  "cancellations are handled over WhatsApp."]
        msg.set_content("\n".join(lines))
        _send(msg, "admin booking", result.get("reference"))
    except Exception as e:
        log.warning("admin booking email failed: %s", e)


def send_customer_booking_email(result: dict, draft: dict) -> None:
    """Confirmation to the person who booked. Best-effort; on-brand plain text."""
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
        lines = [
            f"Hi {name},",
            "",
            "Thanks for booking with Goji Physiotherapy. We've received your "
            "request and here are the details:",
            "",
            f"Service:   {result['service']}",
            f"When:      {when} (Singapore time)",
            f"Where:     {where}",
            f"Clinician: {result['clinician_name']}",
        ]
        if result.get("home") and draft.get("address"):
            lines.append(f"Address:   {draft.get('address')}")
        if (draft.get("notes") or "").strip():
            lines.append(f"You told us: {draft.get('notes').strip()}")
        lines += [
            f"Reference: {result['reference']}",
            "",
            "Need to change or cancel? Just message us on WhatsApp and we'll take "
            f"care of it - that's where we handle all changes and cancellations:",
            f"  {WHATSAPP_LINK}",
            "",
            "See you soon,",
            "The Goji Physiotherapy team",
            "Lentor Modern, #01-13, Lentor Central, Singapore 788887",
            f"Find us on Google Maps: {MAPS_LINK}",
        ]
        msg.set_content("\n".join(lines))
        _send(msg, "customer booking", result.get("reference"))
    except Exception as e:
        log.warning("customer booking email failed: %s", e)
