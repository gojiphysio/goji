"""
The morning summary: one short email to NOTIFY_EMAIL each day (~7:30 SGT,
POST /internal/morning-summary from a scheduler), plus a short version on
WhatsApp to staff whose 24h window is open. Both put what needs Chris first,
one chat per line, in words rather than intent names.

Built from chat state only (ChatState.outcomes, mode, last_staff_at), never
from BigQuery, which has no names or text. Pure functions over ChatState so
the wording is tested without a store.
"""
from __future__ import annotations

from datetime import datetime

from .policy import HUMAN, SGT, WAITING, WATCHLIST, ChatState
from .staff import label, redact

# Chris sent the team's answer through the assistant (app._staff_answer). A
# full answer counts as the team replying; a partial one leaves the chat waiting.
TEAM_ANSWER, TEAM_PARTIAL = "team's answer passed on", "team's answer passed on, part still open"
# Cancelled and getting-worse chats were in no section, so they dropped out of
# the summary (26 Nov 2026): they are the assistant's.
ANSWERED = ("answered", "link sent", "booked", "moved", "cancelled", "booked, flagged",
            "flagged, times offered", TEAM_ANSWER, TEAM_PARTIAL)
LEFT = ("handed over", "left", "drafted")
FAILED = ("failed",)
OFF_TOPIC = ("off-topic", "off-topic, no reply", "watch-listed")  # digest only, never a ping
DAY_S = 86400
WA_LIST_MAX = 8  # chats per group in the WhatsApp version; the email lists them all

# What a chat was about, in words (the intents are config.INTENT_POLICY's keys).
TOPIC = {"greeting": "said hello", "faq": "general question", "pricing": "prices",
         "location_hours": "hours and location", "service_fit": "which service fits",
         "availability": "availability", "booking": "booking",
         "existing_appointment": "their appointment", "reschedule": "moving an appointment",
         "cancel": "cancelling", "billing": "billing", "clinical": "clinical question",
         "complaint": "complaint", "urgent": "possible red flag",
         "priority": "symptoms getting worse", "sensitive": "sensitive topic",
         "human_requested": "asked for a person", "other": "something else",
         "person_check": "asked who's replying", "media_received": "sent a photo or file",
         "off_topic": "off-topic", "staff_answer": "your answer"}
# What happened, where the topic alone doesn't say it.
_DONE = {"link sent": "booking link sent", "booked": "booked", "moved": "appointment moved",
         "cancelled": "appointment cancelled", "booked, flagged": "flagged to you, booked",
         "flagged, times offered": "flagged to you, times offered",
         TEAM_ANSWER: "your answer passed on",
         TEAM_PARTIAL: "your answer passed on, part still open"}


def _who(state: ChatState) -> str:
    return label(state.name or (state.patient or {}).get("first_name", ""), state.wa_id,
                 state.code)


def _in_window(state: ChatState, since: float, kinds: tuple[str, ...]) -> list[dict]:
    return [o for o in state.outcomes if o.get("at", 0) >= since and o.get("outcome") in kinds]


def _waiting(state: ChatState) -> bool:
    return state.mode == WAITING or (state.mode == HUMAN
                                     and state.mode_reason.startswith("escalated"))


def left_for_chris(state: ChatState, since: float) -> bool:
    """Handed over or left since `since` (or still waiting on her) and she
    hasn't written in the chat since."""
    left = _in_window(state, since, LEFT)
    latest = max((o["at"] for o in left), default=0.0)
    if _waiting(state):
        latest = max(latest, state.mode_since)
    replied = max([state.last_staff_at] + [o.get("at", 0) for o in state.outcomes
                                           if o.get("outcome") == TEAM_ANSWER])
    return bool(latest) and replied < latest


def waiting_for_chris(chats: list[ChatState], since: float) -> list[str]:
    """Labels of chats left for Chris since `since` (staff `status`)."""
    return [_who(c) for c in chats if left_for_chris(c, since)]


def _what(outcomes: list[dict]) -> str:
    """"prices, booked" for one chat's outcomes, in order, each said once."""
    out: list[str] = []
    for o in outcomes:
        topic = TOPIC.get(o.get("intent") or "", (o.get("intent") or "message").replace("_", " "))
        outcome = o.get("outcome", "")
        if outcome == "link sent" and o.get("intent") not in ("booking", "", None):
            phrase = f"{topic}, booking link sent"  # what they asked, then the link
        elif outcome in _DONE:
            phrase = _DONE[outcome]
        elif outcome == "failed":
            phrase = f"{topic} failed"
        elif outcome in ("answered",) + LEFT + OFF_TOPIC:
            phrase = topic
        else:
            phrase = f"{topic} ({outcome})"
        if phrase not in out:
            out.append(phrase)
    return ", ".join(out)


def _cap(text: str) -> str:
    """A list line starts with the customer: "Customer ending 4567 (#004)"."""
    if text.startswith("the customer "):
        text = text[len("the "):]
    return text[:1].upper() + text[1:]


def _bullets(items: list[str], mark: str = "-", limit: int = 0) -> str:
    shown = items[:limit] if limit else items
    more = len(items) - len(shown)
    return "\n".join([f"{mark} {_cap(i)}" for i in shown]
                     + ([f"{mark} and {more} more (see your email)"] if more else []))


# STATUS groups (owner, 25 Nov 2026). Past Meta's 24h window Chris can't write
# free-form, so an older unanswered chat isn't "waiting"; a chat the agent was in
# stays "ready to hand back" for 2 days of quiet.
UNANSWERED_S = DAY_S
HAND_BACK_S = 2 * DAY_S


def _latest(c: ChatState) -> float:
    return max(c.last_customer_at, c.last_staff_at, c.mode_since)


def _customer_wrote_last(c: ChatState) -> bool:
    said = [h for h in c.history if h.get("role") in ("customer", "agent", "staff")]
    return bool(said) and said[-1].get("role") == "customer"


def status_groups(paused: list[ChatState], now: float) -> dict:
    """Paused chats sorted by what Chris can do with them, newest first:
    unanswered (the customer wrote last, inside 24h; label + age), hand_back
    (the agent had been in the chat, active in the last 2 days: RESUME them)
    and rest (her own conversations: the agent never spoke, or gone quiet)."""
    out: dict[str, list[str]] = {"unanswered": [], "hand_back": [], "rest": []}
    for c in sorted(paused, key=_latest, reverse=True):
        if _customer_wrote_last(c) and now - c.last_customer_at < UNANSWERED_S:
            hours = max(1, round((now - c.last_customer_at) / 3600))
            out["unanswered"].append(f"{_who(c)} {hours}h ago")
        elif (any(h.get("role") == "agent" for h in c.history)
              and now - _latest(c) < HAND_BACK_S):
            out["hand_back"].append(_who(c))
        else:
            out["rest"].append(_who(c))
    return out


def paused_labels(paused: list[ChatState]) -> list[str]:
    """Chats the agent stays out of until someone resumes them, the one the
    customer wrote in most recently first (that's the one Chris is looking for)."""
    return [_who(c) for c in sorted(paused, key=lambda c: max(c.last_customer_at, c.mode_since),
                                    reverse=True)]


def build(chats: list[ChatState], now: float, window_s: int = DAY_S,
          paused: list[ChatState] | None = None) -> dict:
    """{subject, body, line, answered, left, failed, paused, ...} for the last
    `window_s`, plus every chat still paused (whenever it was paused).

    Both versions put what needs Chris first, one chat per line, then what
    the assistant handled, then what needs nothing. The WhatsApp version was
    one run-on sentence and the email named intents ("location_hours (link
    sent)"): owner, 26 Nov 2026, "word salad"."""
    since = now - window_s
    answered, left, failed, junk = [], [], [], []
    left_who, left_wa = [], []
    for c in sorted(chats, key=lambda s: s.wa_id):
        who = _who(c)
        off = _in_window(c, since, OFF_TOPIC)
        if off:
            junk.append(who)
        got = _in_window(c, since, ANSWERED)
        if got:
            answered.append(f"{who}: {_what(got)}")
        if left_for_chris(c, since):
            items = _in_window(c, since, LEFT)
            line = f"{who}: {_what(items)}" if items else who
            short = who
            if c.mode == WAITING and c.pending_for_chris:
                line += f". Waiting on: {redact(c.pending_for_chris)[:200]}"
                short += f": {redact(c.pending_for_chris)[:80]}"
            left.append(line)
            left_who.append(who)
            left_wa.append(short)
        bad = _in_window(c, since, FAILED)
        if bad:
            failed.append(f"{who}: {_what(bad)}")
    paused = paused or []
    # Paused chats in the same groups as STATUS (owner, 25 Nov 2026): a flat list
    # of 26 was too long to act on. A chat already under "Left for you" isn't
    # repeated as waiting.
    held = [c for c in paused if c.mode_reason != WATCHLIST]
    groups = status_groups(held, now)
    unanswered = [u for u in groups["unanswered"]
                  if not any(u.startswith(w + " ") for w in left_who)]
    hand_back, rest = groups["hand_back"], groups["rest"]
    # Only newly watched chats: older ones stay quiet without filling the email.
    watched = paused_labels([c for c in paused
                             if c.mode_reason == WATCHLIST and c.mode_since >= since])
    day = datetime.fromtimestamp(now, SGT)
    need = len(left) + len(unanswered) + len(failed)
    # The old subject stays first, for any mail filter on it.
    subject = (f"WhatsApp assistant: morning summary {day:%a %d %b}, "
               + (f"{need} chat{'s' if need != 1 else ''} need{'s' if need == 1 else ''} you"
                  if need else "nothing needs you"))
    if not (answered or left or failed or held or junk or watched):
        body = "A quiet 24 hours: the assistant didn't handle any chats.\n"
    else:
        sections = []
        if need:
            part = [f"NEEDS YOU ({need})", "Open these in the WhatsApp Business app."]
            if left:
                part += ["", f"Left for you ({len(left)}):", _bullets(left)]
            if unanswered:
                part += ["", f"Waiting on a reply ({len(unanswered)}), the customer wrote last:",
                         _bullets(unanswered)]
            if failed:
                part += ["", f"Something went wrong ({len(failed)}):", _bullets(failed)]
            sections.append("\n".join(part))
        else:
            sections.append("NOTHING NEEDS YOU")
        if hand_back:
            sections.append("\n".join([
                f"READY TO HAND BACK ({len(hand_back)})",
                "Text RESUME and the number to the Goji number (e.g. RESUME 004). The "
                "assistant won't message them; it answers their next message.",
                _bullets(hand_back)]))
        if answered:
            sections.append(f"HANDLED BY THE ASSISTANT ({len(answered)})\n" + _bullets(answered))
        quiet = []
        if junk:
            quiet += [f"Off-topic, answered without pinging you ({len(junk)}):", _bullets(junk)]
        if watched:
            quiet += ([""] if quiet else []) + [
                f"Stopped answering ({len(watched)}): off-topic several times in a row, so "
                "these are on the watch list. If one is a real customer, text RESUME and "
                "its number.", _bullets(watched)]
        if rest:
            quiet += ([""] if quiet else []) + [
                f"You're handling {len(rest)} more yourself. They come back to the assistant "
                "when you text RESUME and the number, or by themselves if they write 2 weeks "
                "after your last message.", _bullets(rest)]
        if quiet:
            sections.append("NO ACTION NEEDED\n" + "\n".join(quiet))
        body = (f"The WhatsApp assistant's last 24 hours, to {day:%H:%M %a %d %b} SGT.\n\n"
                + "\n\n".join(sections) + "\n")
    line = _wa_line(answered, left_wa, unanswered, failed, hand_back, rest, junk)
    return {"subject": subject, "body": body, "line": line,
            "answered": len(answered), "left": len(left), "failed": len(failed),
            "paused": len(held), "unanswered": len(unanswered), "hand_back": len(hand_back),
            "off_topic": len(junk), "watched": len(watched)}


def _wa_line(answered, left, unanswered, failed, hand_back, rest, junk) -> str:
    """The WhatsApp version: bold headings, one chat per line, longest lists
    cut at WA_LIST_MAX. `left` is the short form: the chat and what it's
    waiting on; the detail is in the email."""
    counts = [f"{len(answered)} handled by the assistant"]
    if junk:
        counts.append(f"{len(junk)} off-topic")
    out = ["☀️ *Goji assistant, last 24h*", " · ".join(counts)]
    groups = [("Left for you", left), ("Waiting on a reply", unanswered),
              ("Something went wrong", failed)]
    if any(items for _, items in groups):
        for title, items in groups:
            if items:
                out += ["", f"*{title} ({len(items)})*", _bullets(items, "•", WA_LIST_MAX)]
    else:
        out += ["", "Nothing needs you."]
    if hand_back:
        out += ["", f"*Ready to hand back ({len(hand_back)})*, text RESUME and the number:",
                _bullets(hand_back, "•", WA_LIST_MAX)]
    if rest:
        out += ["", f"You're handling {len(rest)} more yourself (STATUS ALL lists them)."]
    out.append("Details in your email.")
    return "\n".join(out)
