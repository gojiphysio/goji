"""
Staff on their personal WhatsApp: short pings when a chat needs them, and
text commands: stop / start / status, and resume / pause <chat code>.

Every chat has a short code ("004") shown in pings, the status reply and the
morning summary. Chris writing in a chat pauses the agent there; "resume 004"
hands it back. Resuming sends the customer nothing: the agent just starts
paying attention again from their next message.

Staff numbers (WA_AGENT_STAFF: Chris, optionally Charles) are never customers:
app.handle_staff takes their messages before any patient lookup, model call
or metric. A message from a staff number opens Meta's 24-hour window for that
number, so pings inside it are free-form; outside it they go as the approved
`goji_staff_alert_v2` template.

Pure helpers; app.py does the sending. A ping never carries a customer's full
phone number: a first name, or the last 4 digits.
"""
from __future__ import annotations

import re

STAFF_WINDOW_S = 23 * 3600  # Meta's window is 24h; keep a margin
PARAM_MAX = 150             # the template's one parameter

HELP = ("Goji assistant: RESUME 004 hands chat #004 back to the assistant (it won't "
        "message them, it just answers their next message), PAUSE 004 silences it in that "
        "chat, STOP pauses it in every chat, START turns it back on, STATUS for a summary.")

_NUMBER = re.compile(r"\+?\d[\d\s().-]{5,}\d")
_SPACE = re.compile(r"\s+")


def label(name: str, wa_id: str, code: str = "") -> str:
    """How a customer is named to staff: first name, else the last 4 digits,
    plus the chat code when there is one ("Mei (#004)")."""
    first = (name or "").strip().split()
    if first:
        who = first[0]
    else:
        digits = "".join(ch for ch in wa_id or "" if ch.isdigit())
        who = f"the customer ending {digits[-4:]}" if digits else "a customer"
    return f"{who} (#{code})" if code else who


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


def _clip(text: str) -> str:
    return text if len(text) <= PARAM_MAX else text[:PARAM_MAX - 1].rstrip() + "…"


def template_params(who: str, note: str) -> list[str]:
    """goji_staff_alert_v2: "Staff alert: chat {{1}} on Goji's WhatsApp needs a
    reply from the team. Reason: {{2}}. ..." One line each, no phone numbers."""
    reason = redact(note).rstrip(" .") or "a customer is waiting for a reply"
    return [_clip(redact(who) or "with a customer"), _clip(reason)]


def window_open(last_inbound_at: float, now: float) -> bool:
    return bool(last_inbound_at) and now - last_inbound_at < STAFF_WINDOW_S


def parse_command(text: str) -> tuple[str, str]:
    """(command, chat code): stop | start | status | resume | pause | help.
    "resume 004", "Resume chat #4" -> ("resume", "004")."""
    words = re.sub(r"[^\w\s]", " ", (text or "").lower()).split()
    word = words[0] if words else ""
    if word in ("resume", "pause"):
        digits = next((w for w in words[1:] if w.isdigit()), "")
        return (word, f"{int(digits):03d}") if digits else ("help", "")
    return (word if word in ("stop", "start", "status") else "help"), ""


def status_text(*, kill: bool, rollout: dict, waiting: list[str],
                paused: list[str] | None = None, live: bool = True) -> str:
    stage = rollout.get("stage")
    lines = [
        "Goji assistant: " + ("STOPPED (kill switch on), text START to resume."
                              if kill else "running." if live
                              else "not live yet (it only records message times)."),
        f"Stage {stage if stage is not None else 'default (Phase 0 policy)'}, contacts: "
        f"{rollout.get('contact_scope')}, hours: {rollout.get('hours')}.",
    ]
    if waiting:
        shown = ", ".join(waiting[:5]) + (f" and {len(waiting) - 5} more" if len(waiting) > 5 else "")
        lines.append(f"Waiting for you today: {len(waiting)} ({shown}).")
    else:
        lines.append("Nothing waiting for you today.")
    if paused:
        shown = ", ".join(paused[:8]) + (f" and {len(paused) - 8} more" if len(paused) > 8 else "")
        lines.append(f"Paused for you: {shown}. Text RESUME and the number to hand one back.")
    return "\n".join(lines)
