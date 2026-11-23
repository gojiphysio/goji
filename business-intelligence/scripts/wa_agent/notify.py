"""
Tell a person when the agent hands a chat over or drafts a reply it won't send.

Email to hello@ over Gmail SMTP, the same path as the booking and reminder
mailers. Staff with a number in WA_AGENT_STAFF are pinged on WhatsApp first
(app._alert, staff.py); email then stays the backup for urgent and sensitive
handovers, and the only channel when no staff number is set or a ping fails.
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
            feedback: dict | None = None, sent_reply: str = "") -> EmailMessage:
    subject = {"escalated": "WhatsApp: needs you", "drafted": "WhatsApp: draft reply to check",
               "urgent": "URGENT WhatsApp: possible red flag",
               "sensitive": "WhatsApp: needs you (sensitive)",
               "demoted": "WhatsApp assistant: moved a kind of message back to drafts",
               "fyi": "WhatsApp FYI: a customer asked for you",
               "media": "WhatsApp: a customer sent a photo or document",
               "reschedule": "WhatsApp: please move an appointment"}.get(kind, f"WhatsApp: {kind}")
    msg = EmailMessage()
    msg["Subject"] = f"{subject} - {customer or wa_id}"
    msg["From"] = config.GMAIL_USER
    msg["To"] = config.NOTIFY_EMAIL
    msg.set_content(
        f"Customer: {customer or 'unknown'} (+{wa_id})\n"
        f"What they want: {staff_note}\n"
        f"Why you're getting this: {reason}\n\n"
        f"Their last message:\n{last_message}\n\n"
        + _replies(kind, suggested_reply, sent_reply)
        + ("Nothing was sent. If the draft is right, send it from the WhatsApp "
           "Business app (that also takes the chat over from the assistant).\n"
           if kind == "drafted" else
           "No action needed: the assistant asked what it's about and will pass "
           "it on. Reply yourself in the WhatsApp Business app if you'd rather "
           "(that takes the chat over).\n"
           if kind == "fyi" else
           "Open it in the WhatsApp Business app: the assistant doesn't look at "
           "photos, and only reads the text of documents.\n"
           if kind == "media" else
           "The assistant offered new times and said the team will move it and "
           "confirm. It can't change bookings: please move it in Plato and confirm "
           "with them. If they haven't picked a time yet, another email follows "
           "when they do.\n"
           if kind == "reschedule" else
           "Reply to them in the WhatsApp Business app. Until you do, the assistant "
           "keeps answering their routine questions, but not this. Once you reply it "
           "stays out of the chat until you text RESUME and the chat number.\n"
           if kind == "escalated" else
           "Reply to them in the WhatsApp Business app. The assistant stays out of "
           "this chat until you hand it back or 24 hours pass with no reply from you.\n")
        + (f"\nDid the assistant handle this right? One tap, no login:\n"
           f"Yes: {feedback['up']}\nNo: {feedback['down']}\n" if feedback else "")
    )
    return msg


def _replies(kind: str, suggested: str, sent: str) -> str:
    """The reply part of a ping. On a handover the customer got the holding
    reply (`sent`) and `suggested` is the agent's draft for Chris, with
    [brackets] for her to fill in: show both, clearly apart."""
    if sent and kind in ("escalated", "urgent", "sensitive"):
        out = f"The customer got:\n{sent}\n\n"
        if suggested.strip() and suggested.strip() != sent.strip():
            out += ("Suggested reply for you (NOT sent; fill in anything in [brackets] "
                    f"first):\n{suggested}\n\n")
        return out
    label = ("Suggested reply (NOT sent)" if kind == "drafted" else "Agent sent this reply"
             if kind in ("fyi", "reschedule", "media") else "Agent sent this holding reply")
    return f"{label}:\n{suggested}\n\n"


def compose_plain(subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.GMAIL_USER
    msg["To"] = config.NOTIFY_EMAIL
    msg.set_content(body)
    return msg


def send_plain(subject: str, body: str) -> None:
    """A plain email to NOTIFY_EMAIL (the morning summary). Fire-and-forget."""
    _deliver(compose_plain(subject, body))


def send(kind: str, **kw) -> None:
    """Fire-and-forget. Without a password configured it only logs."""
    _deliver(compose(kind, **kw))


def _deliver(msg: EmailMessage) -> None:
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
