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
hands it back. If the customer's last message is unanswered (and under a day
old), the agent answers it then; otherwise resuming sends the customer nothing
and the agent answers their next message.

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
        "RESUME 004 hands chat #004 back to the assistant (if their last message hasn't "
        "been answered it replies now, otherwise it answers their next one; a chat you "
        "wrote in comes back "
        "by itself if they write 2 weeks after your last message), PAUSE 004 silences it in "
        "that chat for good, STOP pauses it in every chat, START turns it back on, STATUS "
        "for a summary, STATUS ALL to list every chat you're handling yourself.")

# The first message a staff number gets from the assistant: the walkthrough
# (Charles, 19 Nov 2026: bake the go-live briefing into it). Free-form needs an
# open window, so it is the reply to their first message to the Goji number
# (on go-live day: text "hi"), whatever that message says.
WELCOME = (
    "Hi! I'm Goji's WhatsApp assistant. Here's how we'll work together:\n\n"
    "1. I answer customers on the Goji number: questions, prices, availability, bookings "
    "and moving appointments.\n"
    "2. When a chat needs you, I message you here: who it is (e.g. Mei #004), what they "
    "want, what they said, what I told them and a draft reply with anything only you "
    "know in [brackets].\n"
    "3. Once you have the answer, swipe-reply to my ping with it (or text ANSWER 004 and "
    "the answer). I'll write it up, send it to the customer, show you what I sent and "
    "look after the chat again.\n"
    "4. As soon as you write in a chat yourself, I go quiet there until you hand it back. "
    "If the customer writes again 2 weeks or more after your last message, I pick it up.\n"
    "5. To hand a chat back without a message, text RESUME and its number, e.g. RESUME "
    "004. If their last message hasn't been answered, I reply to it now; if it has, I "
    "won't message them and I'll answer their next one.\n"
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


# The header of each kind of ping: what happened, at a glance on a lock screen.
_PING_HEAD = {
    "urgent": "🚨 *URGENT: {who}, possible red flag*",
    "sensitive": "🔔 *{who} needs you (sensitive)*",
    "priority": "⚠️ *{who}: symptoms getting worse*",
    "media": "📎 *{who} sent something I couldn't use*",
    "reaction": "💬 *{who}: a reaction to check*",
    "fyi": "ℹ️ *{who}: for you to do*",
    "demoted": "⚙️ *Assistant setting changed*",
}
# What to do with it, one line. The default is a handover waiting on her.
_PING_FOOT = {
    "urgent": "I've already sent them the reply above. Swipe-reply with anything to add, "
              "or call or reply in the Business app.",
    "priority": "I'm still in the chat and will book the time they pick. Reply in the "
                "Business app to step in.",
    "media": "Open the chat in the Business app to see it. I'm still answering them.",
    "reaction": "Open the chat in the Business app if it needs a word.",
    "fyi": "Nothing to send them.",
    "demoted": "",
}
_HANDOVER_FOOT = ("Swipe-reply with the answer and I'll send it, or reply yourself in the "
                  "Business app.")
QUOTE_MAX = 220   # a customer message or a reply, in a ping
DRAFT_MAX = 450   # the draft is the part she may send, so it gets more room


def _quote(text: str, limit: int) -> str:
    text = redact(text)
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def ping_text(kind: str, who: str, note: str, *, last_message: str = "",
              sent_reply: str = "", draft: str = "") -> str:
    """The free-form ping, inside the staff member's 24h window: a bold header
    that says what happened, the one-line summary, then what the customer
    said, what they were told and the draft for her, each on its own line,
    and what to do. It was one run-on sentence with all of that missing, and
    read as word salad on a phone (owner, 26 Nov 2026). WhatsApp renders
    *bold*; quotes are redacted and clipped."""
    who = redact(who) or "a customer"
    who = who[0].upper() + who[1:]  # it starts the header: "The customer ending 4567"
    head = _PING_HEAD.get(kind, "🔔 *{who} needs you*").format(who=who)
    note = redact(note).rstrip(" .")
    lines = [head] + ([note[0].upper() + note[1:] + "."] if note else [])
    quoted = []
    if last_message.strip() and kind != "reaction":  # a reaction's text is the emoji
        quoted.append(f"*They said:* “{_quote(last_message, QUOTE_MAX)}”")
    if sent_reply.strip():
        quoted.append(f"*I told them:* “{_quote(sent_reply, QUOTE_MAX)}”")
    if draft.strip() and draft.strip() != sent_reply.strip():
        quoted.append(f"*Draft for you:* “{_quote(draft, DRAFT_MAX)}”")
    if quoted:
        lines += [""] + quoted
    foot = _PING_FOOT.get(kind, _HANDOVER_FOOT)
    if foot:
        lines += ["", foot]
    return "\n".join(lines)


def _clip(text: str) -> str:
    return text if len(text) <= PARAM_MAX else text[:PARAM_MAX - 1].rstrip() + "…"


# The template's reason is one line, so the kind goes in front of the note.
_TEMPLATE_KIND = {"urgent": "Possible red flag", "sensitive": "Sensitive",
                  "priority": "Symptoms getting worse",
                  "media": "Sent something the assistant couldn't use",
                  "reaction": "Reacted", "demoted": "Assistant setting changed"}


def template_params(who: str, note: str, kind: str = "") -> list[str]:
    """goji_staff_alert_v2: "Staff alert: chat {{1}} on Goji's WhatsApp needs a
    reply from the team. Reason: {{2}}. ..." One line each, no phone numbers."""
    reason = redact(note).rstrip(" .")
    if kind in _TEMPLATE_KIND:
        reason = f"{_TEMPLATE_KIND[kind]}: {reason}" if reason else _TEMPLATE_KIND[kind]
    reason = reason or "a customer is waiting for a reply"
    return [_clip(redact(who) or "with a customer"), _clip(reason)]


def window_open(last_inbound_at: float, now: float) -> bool:
    return bool(last_inbound_at) and now - last_inbound_at < STAFF_WINDOW_S


def parse_command(text: str) -> tuple[str, str]:
    """(command, chat code): stop | start | status | resume | pause | help.
    "resume 004", "Resume chat #4" -> ("resume", "004"); "status all" ->
    ("status", "all")."""
    words = re.sub(r"[^\w\s]", " ", (text or "").lower()).split()
    word = words[0] if words else ""
    if word in ("resume", "pause"):
        digits = next((w for w in words[1:] if w.isdigit()), "")
        return (word, f"{int(digits):03d}") if digits else ("help", "")
    if word == "status":
        return "status", "all" if "all" in words[1:] else ""
    return (word if word in ("stop", "start") else "help"), ""


_ANSWER = re.compile(r"^\s*answer\s*(?:chat\s*)?#?\s*(\d+)\b[\s:,.\-]*(.*)$", re.I | re.S)
_ONE_WORD = re.compile(r"^\s*(stop|start|status(?:\s+all)?|help|resume|pause)\s*[.!]*\s*$", re.I)


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
                unanswered: list[str] | None = None, hand_back: list[str] | None = None,
                others: list[str] | None = None, show_all: bool = False,
                live: bool = True) -> str:
    """STATUS: chats waiting on a reply, chats to hand back to the agent, and a
    count of the ones Chris is handling herself (STATUS ALL lists those). A flat
    list of every paused chat ran to 26 and hid the newest (25 Nov 2026)."""
    stage = rollout.get("stage")
    lines = [
        "Goji assistant: " + ("STOPPED (kill switch on), text START to resume."
                              if kill else "running." if live
                              else "not live yet (it only records message times)."),
        f"Stage {stage if stage is not None else 'default (Phase 0 policy)'}, contacts: "
        f"{rollout.get('contact_scope')}, hours: {rollout.get('hours')}.",
    ]
    unanswered, hand_back, others = unanswered or [], hand_back or [], others or []
    # A handed-over chat can also be a paused one; show it once, with its age.
    replies = [w for w in waiting if not any(u.startswith(w) for u in unanswered)] + unanswered
    if replies:
        lines.append(f"Waiting on a reply ({len(replies)}): {', '.join(replies)}.")
    else:
        lines.append("Nothing waiting on a reply.")
    if hand_back:
        lines.append(f"Ready to hand back, text RESUME and the number ({len(hand_back)}): "
                     f"{', '.join(hand_back)}.")
    if others and show_all:
        lines.append(f"You're handling these yourself ({len(others)}): {', '.join(others)}.")
    elif others:
        lines.append(f"You're handling {len(others)} more yourself. Text STATUS ALL to "
                     f"list them.")
    return "\n".join(lines)
