"""
Doctor referrals sent to the clinic number as photos.

Referring doctors (WA_AGENT_REFERRERS, e.g. Dr Ong) send a photo of the
referral when they have a patient for Goji. The agent never answers them (Chris
does); app.handle_referrer reads each photo with Claude, pulls out the
patient's name and phone number, and WhatsApps it to Chris
(WA_AGENT_REFERRAL_TO) so she can send the patient the referral template.

This is the one ping that carries a full name and number: the owner asked for
it (25 Nov 2026), and it goes only to the clinic's own staff numbers. The text
is never logged or written to BigQuery; de-duplication keys are hashes.

Pure helpers plus `extract` (one model call); app.py does the sending.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re

from . import config

IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
PDF = "application/pdf"
MAX_BYTES = 5 * 1024 * 1024  # the Messages API's per-image limit

PROMPT = """This is a photo (or scan) a doctor sent a physiotherapy clinic. It is \
usually a referral letter, a memo, or a screenshot with a patient's details.

Extract every patient being referred: their full name exactly as written and \
their phone number (Singapore mobile "HP" or any contact number for the \
patient). Also give the referring doctor's name if it's shown.

Answer with JSON only, no prose:
{"patients": [{"name": "...", "phone": "..."}], "doctor": "..."}

Use "" for anything not shown. Don't guess or invent digits. If the image \
isn't about a patient (an insurance card, a logo, a blank page), return \
{"patients": [], "doctor": ""}."""


def media_block(data: bytes, mime: str) -> dict | None:
    """The Messages API content block for a photo or PDF, or None if the
    file can't be read by the model."""
    mime = (mime or "").split(";")[0].strip().lower()
    if not data or len(data) > MAX_BYTES:
        return None
    b64 = base64.b64encode(data).decode()
    if mime in IMAGE_TYPES:
        return {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}}
    if mime == PDF:
        return {"type": "document", "source": {"type": "base64", "media_type": PDF, "data": b64}}
    return None


def extract(client, data: bytes, mime: str, model: str = config.MODEL) -> dict:
    """{"patients": [{"name", "phone"}], "doctor"} read from one photo.
    Raises ValueError if the file can't be read; model errors propagate."""
    block = media_block(data, mime)
    if block is None:
        raise ValueError(f"unreadable media ({mime}, {len(data or b'')} bytes)")
    resp = client.beta.messages.create(
        model=model, max_tokens=500,
        messages=[{"role": "user", "content": [block, {"type": "text", "text": PROMPT}]}])
    text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
    return parse(text)


def parse(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        raw = json.loads(m.group()) if m else {}
    except ValueError:
        raw = {}
    patients = []
    for p in raw.get("patients") or []:
        if not isinstance(p, dict):
            continue
        name = " ".join(str(p.get("name") or "").split())
        phone = normalise_phone(p.get("phone"))
        if name or phone:
            patients.append({"name": name, "phone": phone})
    return {"patients": patients, "doctor": " ".join(str(raw.get("doctor") or "").split())}


def normalise_phone(raw) -> str:
    """E.164 digits ("6591234567") for a Singapore number written any way
    ("9123 4567", "+65-9123-4567"); other digits as written; "" for none."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) == 8 and digits[0] in "3689":
        return "65" + digits
    if len(digits) == 10 and digits.startswith("65") and digits[2] in "3689":
        return digits
    return digits if len(digits) >= 7 else ""


def display_phone(e164: str) -> str:
    """"6591234567" -> "9123 4567"; anything else unchanged."""
    if len(e164) == 10 and e164.startswith("65"):
        return f"{e164[2:6]} {e164[6:]}"
    return e164


def key(phone: str = "", name: str = "") -> str:
    """De-duplication key for one patient: a hash, never the number itself."""
    basis = phone or " ".join((name or "").lower().split())
    return hashlib.sha256(f"referral:{basis}".encode()).hexdigest()[:32]


def forward_text(referrer: str, patient: dict, doctor: str = "", caption: str = "") -> str:
    """What Chris gets on WhatsApp for one referred patient."""
    lines = [f"New referral from {referrer}:",
             f"Name: {patient.get('name') or '(not shown)'}",
             f"HP: {display_phone(patient.get('phone', '')) or '(not shown)'}"]
    if doctor:
        lines.append(f"Doctor: {doctor}")
    if caption:
        lines.append(f"Note: {caption}")
    return "\n".join(lines)


def unreadable_text(referrer: str, caption: str = "") -> str:
    note = f' ("{caption}")' if caption else ""
    return (f"{referrer} sent a photo{note} but I couldn't find a patient's name and "
            f"number in it. Please check the chat.")


def extra_photo_text(referrer: str, caption: str) -> str:
    return f'{referrer} also sent a photo: "{caption}"'
