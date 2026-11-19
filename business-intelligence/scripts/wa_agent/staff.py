"""
Staff on their personal WhatsApp: short pings when a chat needs them, and
three text commands (stop / start / status).

Staff numbers (WA_AGENT_STAFF: Chris, optionally Charles) are never customers:
app.handle_staff takes their messages before any patient lookup, model call
or metric. A message from a staff number opens Meta's 24-hour window for that
number, so pings inside it are free-form; outside it they go as the approved
`goji_staff_alert` template.

Pure helpers; app.py does the sending. A ping never carries a customer's full
phone number: a first name, or the last 4 digits.
"""
from __future__ import annotations

import re

STAFF_WINDOW_S = 23 * 3600  # Meta's window is 24h; keep a margin
PARAM_MAX = 150             # the template's one parameter

HELP = ("Goji assistant: text STOP to pause it in every chat, START to turn it back "
        "on, or STATUS for a quick summary.")

_NUMBER = re.compile(r"\+?\d[\d\s().-]{5,}\d")
_SPACE = re.compile(r"\s+")


def label(name: str, wa_id: str) -> str:
    """How a customer is named to staff: first name, else the last 4 digits."""
    first = (name or "").strip().split()
    if first:
        return first[0]
    digits = "".join(ch for ch in wa_id or "" if ch.isdigit())
    return f"the customer ending {digits[-4:]}" if digits else "a customer"


def redact(text: str) -> str:
    """Phone-number-like runs of 7+ digits become [number]; whitespace is
    collapsed to single spaces (template parameters reject newlines and tabs)."""
    out = _NUMBER.sub(lambda m: "[number]" if sum(c.isdigit() for c in m.group()) >= 7
                      else m.group(), text or "")
    return _SPACE.sub(" ", out).strip()


def ping_text(who: str, note: str) -> str:
    """The free-form ping, inside the staff member's 24h window."""
    note = redact(note).rstrip(" .") or "a chat needs a reply"
    head = f"Goji assistant: {who} needs you" if who else "Goji assistant needs you"
    return f"{head}: {note}. Open the chat in the Business app."


def template_param(who: str, note: str) -> str:
    """{{1}} of goji_staff_alert: short reason, one line, no phone numbers."""
    note = redact(note).rstrip(" .") or "a chat needs a reply"
    text = redact(f"{who}: {note}" if who else note)
    return text if len(text) <= PARAM_MAX else text[:PARAM_MAX - 1].rstrip() + "…"


def window_open(last_inbound_at: float, now: float) -> bool:
    return bool(last_inbound_at) and now - last_inbound_at < STAFF_WINDOW_S


def parse_command(text: str) -> str:
    """stop | start | status | help."""
    words = re.sub(r"[^\w\s]", " ", (text or "").lower()).split()
    word = words[0] if words else ""
    return word if word in ("stop", "start", "status") else "help"


def status_text(*, kill: bool, rollout: dict, waiting: list[str]) -> str:
    stage = rollout.get("stage")
    lines = [
        "Goji assistant: " + ("STOPPED (kill switch on), text START to resume."
                              if kill else "running."),
        f"Stage {stage if stage is not None else 'default (Phase 0 policy)'}, contacts: "
        f"{rollout.get('contact_scope')}, hours: {rollout.get('hours')}.",
    ]
    if waiting:
        shown = ", ".join(waiting[:5]) + (f" and {len(waiting) - 5} more" if len(waiting) > 5 else "")
        lines.append(f"Waiting for you today: {len(waiting)} ({shown}).")
    else:
        lines.append("Nothing waiting for you today.")
    return "\n".join(lines)
