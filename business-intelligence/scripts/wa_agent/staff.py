"""
Staff on their personal WhatsApp: short pings when a chat needs them, and
text commands: stop / start / status, resume / pause <chat code>, and
answer <chat code> <the team's answer>.

The team's answer (owner, 24 Nov 2026): Chris swipe-replies to a ping with
the answer, or texts "answer 004 ...". The agent writes it up in its own
voice, sends it, hands the chat back to itself and shows her what it sent
(app._staff_answer). Any chat, any mode: it is her explicit instruction.

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

HELP = ("Goji assistant: swipe-reply to one of my pings with the team's answer (or text "
        "ANSWER 004 and the answer) and I'll pass it on and look after the chat again. "
        "RESUME 004 hands chat #004 back to the assistant (it won't "
        "message them, it just answers their next message; a chat you wrote in comes back "
        "by itself if they write 2 weeks after your last message), PAUSE 004 silences it in "
        "that chat for good, STOP pauses it in every chat, START turns it back on, STATUS "
        "for a summary.")

# The first message a staff number gets from the assistant: the walkthrough
# (Charles, 19 Nov 2026: bake the go-live briefing into it). Free-form needs an
# open window, so it is the reply to their first message to the Goji number
# (on go-live day: text "hi"), whatever that message says.
WELCOME = (
    "Hi! I'm Goji's WhatsApp assistant. Here's how we'll work together:\n\n"
    "1. I answer customers on the Goji number: questions, prices, availability, bookings "
    "and moving appointments.\n"
    "2. When a chat needs you, I message you here, e.g. \"Mei (#004) needs you: ...\". "
    "I've already told them the team will get back to them. The email has my suggested "
    "reply: fill in anything in [brackets], then send it from the WhatsApp Business app.\n"
    "3. Once you have the answer, swipe-reply to my ping with it (or text ANSWER 004 and "
    "the answer). I'll write it up, send it to the customer, show you what I sent and "
    "look after the chat again.\n"
    "4. As soon as you write in a chat yourself, I go quiet there until you hand it back. "
    "If the customer writes again 2 weeks or more after your last message, I pick it up.\n"
    "5. To hand a chat back without a message, text RESUME and its number, e.g. RESUME "
    "004. I won't message the customer; I'll just answer their next message.\n"
    "6. PAUSE 004 keeps me out of one chat for good. STOP pauses me in every chat, START "
    "turns me back on.\n"
    "7. Every morning at 7:30 there's an email summary, including the chats waiting for "
    "you to resume and any spam numbers I've stopped answering. STATUS here shows the "
    "same any time.\n\n"
    "Text STATUS now to try it."
)

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


_ANSWER = re.compile(r"^\s*answer\s*(?:chat\s*)?#?\s*(\d+)\b[\s:,.\-]*(.*)$", re.I | re.S)
_ONE_WORD = re.compile(r"^\s*(stop|start|status|help|resume|pause)\s*[.!]*\s*$", re.I)


def parse_answer(text: str) -> tuple[str, str] | None:
    """"ANSWER 004 yes, Sat 10am is fine" -> ("004", "yes, Sat 10am is fine"),
    keeping the answer exactly as written. None if it isn't an answer command;
    ("004", "") for an answer with no text."""
    m = _ANSWER.match(text or "")
    return (f"{int(m.group(1)):03d}", m.group(2).strip()) if m else None


def bare_command(text: str) -> str:
    """A swipe-reply to a ping that is just a command word ("resume", "stop")
    is that command, not an answer to pass on: the word, lowercased, or ""."""
    m = _ONE_WORD.match(text or "")
    return m.group(1).lower() if m else ""


def answer_sent_text(who: str, reply: str, still_open: str = "") -> str:
    head = f"Sent to {who}:\n\n{reply}\n\n"
    if still_open:
        return head + (f"They're still waiting on: {redact(still_open)}. I'll keep answering "
                       f"everything else; swipe-reply again when you have it.")
    return head + "I'm looking after the chat again."


def answer_refused_text(who: str, why: str) -> str:
    return (f"I didn't send anything to {who}: {why.rstrip('. ')}. Please reply in the "
            f"Business app, or send the answer again.")


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
