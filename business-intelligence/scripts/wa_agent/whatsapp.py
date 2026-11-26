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
  history               coexistence onboarding: up to 180 days of earlier
                        chats, in chunks. Only timestamps are kept (who wrote
                        last, and when) for the go-live cut-off; never the text.

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
    media_id: str = ""     # image / document: fetched with WhatsAppClient.download_media
    mime: str = ""
    filename: str = ""
    caption: str = ""
    reply_to: str = ""     # the message id they swipe-replied to (context.id), or reacted to
    emoji: str = ""        # a reaction's emoji; "" when they removed one
    payload: str = ""      # a template quick-reply's payload, e.g. reminder_confirm:<appointment id>


@dataclass
class Echo:
    wa_id: str      # the customer the business wrote to
    msg_id: str
    ts: float
    text: str


@dataclass
class HistoryChunk:
    """One `history` webhook chunk, reduced to timestamps per customer:
    {wa_id: (latest customer message ts, latest business message ts)}, 0 for
    none. `progress` 100 means the sync is complete; `declined` is set when the
    business turned history sharing off (error 2593109)."""
    threads: dict
    progress: int = 0
    declined: bool = False
    error_code: int = 0


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
    if kind == "reaction":
        emoji = (m.get("reaction") or {}).get("emoji", "")
        return (f"[reacted {emoji}]" if emoji else "[removed a reaction]"), kind
    caption = (m.get(kind) or {}).get("caption") if isinstance(m.get(kind), dict) else None
    text = NON_TEXT_PLACEHOLDERS.get(kind, f"[sent a {kind} message]")
    return (f"{text} {caption}" if caption else text), kind


def _digits(x) -> str:
    return "".join(ch for ch in str(x or "") if ch.isdigit())


def parse_history(value: dict) -> HistoryChunk:
    """Meta's coexistence `history` webhook value (developers.facebook.com/docs/
    whatsapp/embedded-signup/custom-flows/onboarding-business-app-users):

      value.metadata.display_phone_number     the business number
      value.history[]: {metadata: {phase, chunk_order, progress},
                        threads: [{id: <customer wa_id>, context: {wa_id},
                                   messages: [{from, to?, id, timestamp, type,
                                               history_context: {status}}]}]}
      declined: value.history[]: {errors: [{code: 2593109, ...}]}

    A message is the business's when it has `to` (Meta: present only on SMB
    echoes) or `from` is the business number. The customer is the thread id
    (or context.wa_id), else the other party of the message. Coded
    defensively from the docs: any field may be missing, and real payloads
    must be checked when the clinic's number is onboarded (README)."""
    business = _digits((value.get("metadata") or {}).get("display_phone_number"))
    threads: dict[str, list[float]] = {}
    progress, declined, code = 0, False, 0
    for h in value.get("history") or []:
        if not isinstance(h, dict):
            continue
        for err in h.get("errors") or []:
            declined, code = True, int((err or {}).get("code") or 0)
        try:
            progress = max(progress, int((h.get("metadata") or {}).get("progress") or 0))
        except (TypeError, ValueError):
            pass
        for t in h.get("threads") or []:
            if not isinstance(t, dict):
                continue
            thread_id = _digits(t.get("id") or (t.get("context") or {}).get("wa_id"))
            for m in t.get("messages") or []:
                if not isinstance(m, dict):
                    continue
                try:
                    ts = float(m.get("timestamp") or 0)
                except (TypeError, ValueError):
                    ts = 0.0
                if ts <= 0:
                    continue
                sender = _digits(m.get("from"))
                from_business = bool(m.get("to")) or (bool(business) and sender == business)
                customer = thread_id or (_digits(m.get("to")) if from_business else sender)
                if not customer or customer == business:
                    continue
                last = threads.setdefault(customer, [0.0, 0.0])
                i = 1 if from_business else 0
                last[i] = max(last[i], ts)
    return HistoryChunk(threads={k: (v[0], v[1]) for k, v in threads.items()},
                        progress=progress, declined=declined, error_code=code)


def parse_webhook(payload: dict) -> list[Inbound | Echo | Status | HistoryChunk]:
    """Flatten one webhook body into events, in payload order. Unknown fields
    (app state sync, template updates) are ignored."""
    events: list[Inbound | Echo | Status | HistoryChunk] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            field_name = change.get("field")
            value = change.get("value") or {}
            if field_name == "messages":
                names = {c.get("wa_id"): (c.get("profile") or {}).get("name", "")
                         for c in value.get("contacts") or []}
                for m in value.get("messages") or []:
                    text, kind = _message_text(m)
                    media = m.get(kind) if isinstance(m.get(kind), dict) else {}
                    react = (m.get("reaction") or {}) if kind == "reaction" else {}
                    events.append(Inbound(wa_id=m.get("from", ""), msg_id=m.get("id", ""),
                                          ts=float(m.get("timestamp") or 0), text=text,
                                          name=names.get(m.get("from"), ""), kind=kind,
                                          media_id=media.get("id", "") if kind != "text" else "",
                                          mime=media.get("mime_type", ""),
                                          filename=media.get("filename", ""),
                                          caption=media.get("caption", ""),
                                          reply_to=react.get("message_id") or
                                          (m.get("context") or {}).get("id", ""),
                                          emoji=react.get("emoji", ""),
                                          payload=(m.get("button") or {}).get("payload", "")
                                          if kind == "button" else ""))
                for s in value.get("statuses") or []:
                    events.append(Status(msg_id=s.get("id", ""), status=s.get("status", ""),
                                         ts=float(s.get("timestamp") or 0),
                                         wa_id=s.get("recipient_id", "")))
            elif field_name == "smb_message_echoes":
                for m in value.get("message_echoes") or []:
                    if m.get("type") in ("reaction", "revoke"):
                        # A 👍 or a deleted message from the Business app isn't
                        # taking the chat over (a revoke paused chat #027, 25 Nov 2026).
                        continue
                    text, _ = _message_text(m)
                    events.append(Echo(wa_id=m.get("to", ""), msg_id=m.get("id", ""),
                                       ts=float(m.get("timestamp") or 0), text=text))
            elif field_name == "history":
                events.append(parse_history(value))
    return events


class WhatsAppClient:
    """Minimal sender. Errors raise; the caller decides what a failed send means."""

    def __init__(self, base: str = config.WA_API_BASE,
                 phone_number_id: str = config.WA_PHONE_NUMBER_ID,
                 token: str = config.WA_TOKEN, send_path: str = config.WA_SEND_PATH,
                 auth_header: str = config.WA_AUTH_HEADER,
                 auth_prefix: str = config.WA_AUTH_PREFIX,
                 session: requests.Session | None = None):
        self.base = base.rstrip("/")
        self.url = self.base + send_path.format(phone_number_id=phone_number_id)
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

    def send_template(self, wa_id: str, name: str, params: list[str],
                      language: str = "en", url_buttons: dict[int, str] | None = None) -> str:
        """Send an approved template (the only way to message someone outside
        the 24-hour window). Body parameters in order; `url_buttons` maps a URL
        button's index to the text filling its {{1}}. Returns the message id."""
        components = [{"type": "body", "parameters": [
            {"type": "text", "text": p} for p in params]}]
        for index, text in sorted((url_buttons or {}).items()):
            components.append({"type": "button", "sub_type": "url", "index": str(index),
                               "parameters": [{"type": "text", "text": text}]})
        resp = self._post({"messaging_product": "whatsapp", "to": wa_id, "type": "template",
                           "template": {"name": name, "language": {"code": language},
                                        "components": components}})
        return ((resp.get("messages") or [{}])[0]).get("id", "")

    def download_media(self, media_id: str) -> tuple[bytes, str]:
        """(bytes, mime type) of a customer's photo or document. Cloud API:
        look up the media's short-lived URL, then fetch it with the same token.
        A provider with another media API needs its own version of this."""
        meta = self.http.get(f"{self.base}/{media_id}", headers=self.headers, timeout=15)
        meta.raise_for_status()
        info = meta.json()
        if int(info.get("file_size") or 0) > 10 * 1024 * 1024:
            raise ValueError("media too large")
        r = self.http.get(info["url"], headers=self.headers, timeout=30)
        r.raise_for_status()
        return r.content, info.get("mime_type", "")

    def mark_read_typing(self, msg_id: str) -> None:
        """Blue ticks + "typing..." while the agent thinks. Best effort."""
        try:
            self._post({"messaging_product": "whatsapp", "status": "read",
                        "message_id": msg_id, "typing_indicator": {"type": "text"}})
        except Exception as e:  # cosmetic; never block a reply on it
            log.info("typing indicator failed: %s", e)
