"""
Tell a person when the agent hands a chat over or drafts a reply it won't send.

Phase 0: email to hello@ over Gmail SMTP, the same path as the booking and
reminder mailers. Whether Chris is better reached another way (a WhatsApp
message to her own phone, a portal queue) is a Phase 1 decision; this module
is the one place that changes.
"""
from __future__ import annotations

import logging
import smtplib
import threading
from email.message import EmailMessage

from . import config

log = logging.getLogger("wa_agent.notify")


def compose(kind: str, *, customer: str, wa_id: str, staff_note: str,
            suggested_reply: str, reason: str, last_message: str,
            feedback: dict | None = None) -> EmailMessage:
    subject = {"escalated": "WhatsApp: needs you", "drafted": "WhatsApp: draft reply to check",
               "urgent": "URGENT WhatsApp: possible red flag",
               "demoted": "WhatsApp assistant: moved a kind of message back to drafts"}.get(kind, f"WhatsApp: {kind}")
    msg = EmailMessage()
    msg["Subject"] = f"{subject} - {customer or wa_id}"
    msg["From"] = config.GMAIL_USER
    msg["To"] = config.NOTIFY_EMAIL
    msg.set_content(
        f"Customer: {customer or 'unknown'} (+{wa_id})\n"
        f"What they want: {staff_note}\n"
        f"Why you're getting this: {reason}\n\n"
        f"Their last message:\n{last_message}\n\n"
        f"{'Agent sent this holding reply' if kind != 'drafted' else 'Suggested reply (NOT sent)'}:\n"
        f"{suggested_reply}\n\n"
        + ("Reply to them in the WhatsApp Business app. The assistant stays out of "
           "this chat until you hand it back or 24 hours pass with no reply from you.\n"
           if kind != "drafted" else
           "Nothing was sent. If the draft is right, send it from the WhatsApp "
           "Business app (that also takes the chat over from the assistant).\n")
        + (f"\nDid the assistant handle this right? One tap, no login:\n"
           f"Yes: {feedback['up']}\nNo: {feedback['down']}\n" if feedback else "")
    )
    return msg


def send(kind: str, **kw) -> None:
    """Fire-and-forget. Without a password configured it only logs."""
    msg = compose(kind, **kw)
    if not config.GMAIL_APP_PASSWORD:
        log.info("notify (no SMTP configured): %s", msg["Subject"])
        if config.STATE_BACKEND == "memory":  # local testing: show the draft
            log.info("notify body:\n%s", msg.get_content())
        return

    def _send():
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
                s.login(config.GMAIL_USER, config.GMAIL_APP_PASSWORD)
                s.send_message(msg)
        except Exception as e:
            log.warning("notify failed: %s", e)

    threading.Thread(target=_send, daemon=True).start()
