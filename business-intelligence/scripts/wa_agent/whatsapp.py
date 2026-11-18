"""
WhatsApp Cloud API: parse webhooks, verify their signature, send messages.

Payloads are Meta's Cloud API shapes. A provider sitting in front of Meta only
changes the base URL, send path and auth header (config.WA_*), so switching
provider, or going direct to Meta later, is configuration, not code.

Three things arrive on the webhook and matter to us:
  messages              a customer wrote to the business number
  smb_message_echoes    the business number wrote to a customer FROM THE
                        WHATSAPP BUSINESS APP (coexistence). This is how we
                        know Chris replied. Messages the agent sends through
                        the API do not echo back here.
  statuses              sent / delivered / read / failed for our own sends,
                        used to time delivery

The echo shape is coded from Meta's coexistence docs and must be confirmed
against real traffic in Phase 0 Track B (see README).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass

import requests

from . import config

log = logging.getLogger("wa_agent.whatsapp")

NON_TEXT_PLACEHOLDERS = {
    "image": "[sent a photo]",
    "video": "[sent a video]",
    "audio": "[sent a voice note]",
    "document": "[sent a document]",
    "sticker": "[sent a sticker]",
    "location": "[shared a location]",
    "contacts": "[shared a contact card]",
}


@dataclass
class Inbound:
    wa_id: str
    msg_id: str
    ts: float
    text: str
    name: str = ""
    kind: str = "text"


@dataclass
class Echo:
    wa_id: str      # the customer the business wrote to
    msg_id: str
    ts: float
    text: str


@dataclass
class Status:
    msg_id: str
    status: str     # sent | delivered | read | failed
    ts: float
    wa_id: str


def verify_signature(raw_body: bytes, header: str | None,
                     app_secret: str = config.WA_APP_SECRET) -> bool:
    """X-Hub-Signature-256 is `sha256=<hex hmac of the raw body>`. Fail closed:
    no secret configured means nothing verifies."""
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


def _message_text(m: dict) -> tuple[str, str]:
    kind = m.get("type", "text")
    if kind == "text":
        return (m.get("text") or {}).get("body", ""), kind
    if kind == "interactive":
        inter = m.get("interactive") or {}
        reply = inter.get("button_reply") or inter.get("list_reply") or {}
        return reply.get("title", "[tapped a button]"), kind
    if kind == "button":
        return (m.get("button") or {}).get("text", "[tapped a button]"), kind
    caption = (m.get(kind) or {}).get("caption") if isinstance(m.get(kind), dict) else None
    text = NON_TEXT_PLACEHOLDERS.get(kind, f"[sent a {kind} message]")
    return (f"{text} {caption}" if caption else text), kind


def parse_webhook(payload: dict) -> list[Inbound | Echo | Status]:
    """Flatten one webhook body into events, in payload order. Unknown fields
    (history sync, app state sync, template updates) are ignored."""
    events: list[Inbound | Echo | Status] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            field_name = change.get("field")
            value = change.get("value") or {}
            if field_name == "messages":
                names = {c.get("wa_id"): (c.get("profile") or {}).get("name", "")
                         for c in value.get("contacts") or []}
                for m in value.get("messages") or []:
                    text, kind = _message_text(m)
                    events.append(Inbound(wa_id=m.get("from", ""), msg_id=m.get("id", ""),
                                          ts=float(m.get("timestamp") or 0), text=text,
                                          name=names.get(m.get("from"), ""), kind=kind))
                for s in value.get("statuses") or []:
                    events.append(Status(msg_id=s.get("id", ""), status=s.get("status", ""),
                                         ts=float(s.get("timestamp") or 0),
                                         wa_id=s.get("recipient_id", "")))
            elif field_name == "smb_message_echoes":
                for m in value.get("message_echoes") or []:
                    text, _ = _message_text(m)
                    events.append(Echo(wa_id=m.get("to", ""), msg_id=m.get("id", ""),
                                       ts=float(m.get("timestamp") or 0), text=text))
    return events


class WhatsAppClient:
    """Minimal sender. Errors raise; the caller decides what a failed send means."""

    def __init__(self, base: str = config.WA_API_BASE,
                 phone_number_id: str = config.WA_PHONE_NUMBER_ID,
                 token: str = config.WA_TOKEN, send_path: str = config.WA_SEND_PATH,
                 auth_header: str = config.WA_AUTH_HEADER,
                 auth_prefix: str = config.WA_AUTH_PREFIX,
                 session: requests.Session | None = None):
        self.url = base.rstrip("/") + send_path.format(phone_number_id=phone_number_id)
        self.headers = {auth_header: f"{auth_prefix}{token}",
                        "Content-Type": "application/json"}
        self.http = session or requests.Session()

    def _post(self, body: dict) -> dict:
        r = self.http.post(self.url, json=body, headers=self.headers, timeout=15)
        r.raise_for_status()
        return r.json() if r.content else {}

    def send_text(self, wa_id: str, text: str) -> str:
        """Send a free-form reply (only valid inside the 24h service window).
        Returns the WhatsApp message id."""
        resp = self._post({"messaging_product": "whatsapp", "recipient_type": "individual",
                           "to": wa_id, "type": "text",
                           "text": {"preview_url": True, "body": text}})
        return ((resp.get("messages") or [{}])[0]).get("id", "")

    def mark_read_typing(self, msg_id: str) -> None:
        """Blue ticks + "typing..." while the agent thinks. Best effort."""
        try:
            self._post({"messaging_product": "whatsapp", "status": "read",
                        "message_id": msg_id, "typing_indicator": {"type": "text"}})
        except Exception as e:  # cosmetic; never block a reply on it
            log.info("typing indicator failed: %s", e)
