"""
Admin booking-notification email — best-effort, never breaks a booking.

The customer's confirmation is sent by Plato (connect:true, its own template).
This is the internal heads-up to the clinic. Sent via Gmail SMTP as
hello@gojiphysio.com (Google Workspace) using an app password from Secret
Manager; if SMTP isn't configured or fails, we log and move on — the booking has
already succeeded.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

log = logging.getLogger("booking.mailer")

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "hello@gojiphysio.com")
SMTP_PASS = os.environ.get("GMAIL_APP_PASSWORD")  # Secret Manager
ADMIN_TO = os.environ.get("BOOKING_ADMIN_EMAIL", "hello@gojiphysio.com")


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
        lines += [f"Reference: {result['reference']}", "",
                  "The customer has been sent Plato's confirmation. Changes and "
                  "cancellations are handled over WhatsApp."]
        msg.set_content("\n".join(lines))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        log.info("admin booking email sent (ref %s)", result.get("reference"))
    except Exception as e:
        log.warning("admin booking email failed: %s", e)
