"""
The morning summary: one short email to NOTIFY_EMAIL each day (~7:30 SGT,
POST /internal/morning-summary from a scheduler), plus a one-line version on
WhatsApp to staff whose 24h window is open.

Built from chat state only (ChatState.outcomes, mode, last_staff_at), never
from BigQuery, which has no names or text. Pure functions over ChatState so
the wording is tested without a store.
"""
from __future__ import annotations

from datetime import datetime

from .policy import HUMAN, SGT, WAITING, WATCHLIST, ChatState
from .staff import label

ANSWERED = ("answered", "link sent", "booked", "moved")
LEFT = ("handed over", "left", "drafted")
FAILED = ("failed",)
OFF_TOPIC = ("off-topic", "off-topic, no reply", "watch-listed")  # digest only, never a ping
DAY_S = 86400


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
    return bool(latest) and state.last_staff_at < latest


def waiting_for_chris(chats: list[ChatState], since: float) -> list[str]:
    """Labels of chats left for Chris since `since` (staff `status`)."""
    return [_who(c) for c in chats if left_for_chris(c, since)]


def _line(state: ChatState, outcomes: list[dict]) -> str:
    parts = [f"{o.get('intent') or 'message'} ({o['outcome']})" for o in outcomes]
    return f"- {_who(state)}: {', '.join(parts)}"


def paused_labels(paused: list[ChatState]) -> list[str]:
    """Chats the agent stays out of until someone resumes them, oldest first."""
    return [_who(c) for c in sorted(paused, key=lambda c: c.mode_since)]


def build(chats: list[ChatState], now: float, window_s: int = DAY_S,
          paused: list[ChatState] | None = None) -> dict:
    """{subject, body, line, answered, left, failed, paused} for the last
    `window_s`, plus every chat still paused (whenever it was paused)."""
    since = now - window_s
    answered, left, failed, junk = [], [], [], []
    for c in sorted(chats, key=lambda s: s.wa_id):
        off = _in_window(c, since, OFF_TOPIC)
        if off:
            junk.append(_line(c, off))
        got = _in_window(c, since, ANSWERED)
        if got:
            answered.append(_line(c, got))
        if left_for_chris(c, since):
            items = _in_window(c, since, LEFT)
            line = _line(c, items) if items else f"- {_who(c)}: waiting for you"
            if c.mode == WAITING and c.pending_for_chris:
                line += f". Waiting on: {c.pending_for_chris[:200]}"
            left.append(line)
        bad = _in_window(c, since, FAILED)
        if bad:
            failed.append(_line(c, bad))
    paused = paused or []
    held = paused_labels([c for c in paused if c.mode_reason != WATCHLIST])
    # Only newly watched chats: older ones stay quiet without filling the email.
    watched = paused_labels([c for c in paused
                             if c.mode_reason == WATCHLIST and c.mode_since >= since])
    day = datetime.fromtimestamp(now, SGT)
    subject = f"WhatsApp assistant: morning summary {day:%a %d %b}"
    if not (answered or left or failed or held or junk or watched):
        body = "A quiet 24 hours: the assistant didn't handle any chats.\n"
    else:
        sections = []
        if left:
            sections.append(f"Left for you ({len(left)}):\n" + "\n".join(left))
        if failed:
            sections.append(f"Failures ({len(failed)}), please check these chats:\n"
                            + "\n".join(failed))
        if answered:
            sections.append(f"Answered by the assistant ({len(answered)}):\n"
                            + "\n".join(answered))
        if junk:
            sections.append(f"Off-topic, answered without pinging you ({len(junk)}): wrong "
                            "numbers, unrelated questions, attempts to misuse the chat.\n"
                            + "\n".join(junk))
        if watched:
            sections.append(f"Stopped answering ({len(watched)}): off-topic several times in a "
                            "row, so these numbers are on the watch list and get no replies. "
                            "If one is a real customer, text RESUME and its number.\n"
                            + "\n".join(f"- {w}" for w in watched))
        if held:
            sections.append(f"Paused for you ({len(held)}): the assistant stays out of these "
                            "until you hand them back. Text RESUME and the number (e.g. "
                            "RESUME 004) to the Goji number from your phone; the assistant "
                            "won't message them, it just answers their next message.\n"
                            + "\n".join(f"- {h}" for h in held))
        body = ("The WhatsApp assistant's last 24 hours (to "
                f"{day:%H:%M %a %d %b} SGT).\n\n" + "\n\n".join(sections) + "\n\n"
                "Only the chats under \"Left for you\" and \"Failures\" need you. "
                "Open them in the WhatsApp Business app.\n")
    line = (f"Goji assistant, last 24h: {len(answered)} chat(s) answered, "
            f"{len(left)} left for you, {len(failed)} failure(s)."
            + (f" {len(junk)} off-topic, no action needed." if junk else "")
            + (f" Paused for you: {', '.join(held[:6])}{' and more' if len(held) > 6 else ''}"
               ". Text RESUME and the number to hand one back." if held else "")
            + " Details in your email.")
    return {"subject": subject, "body": body, "line": line,
            "answered": len(answered), "left": len(left), "failed": len(failed),
            "paused": len(held), "off_topic": len(junk), "watched": len(watched)}
