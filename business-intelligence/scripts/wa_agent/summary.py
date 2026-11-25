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

# Chris sent the team's answer through the assistant (app._staff_answer). A
# full answer counts as the team replying; a partial one leaves the chat waiting.
TEAM_ANSWER, TEAM_PARTIAL = "team's answer passed on", "team's answer passed on, part still open"
ANSWERED = ("answered", "link sent", "booked", "moved", TEAM_ANSWER, TEAM_PARTIAL)
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
    replied = max([state.last_staff_at] + [o.get("at", 0) for o in state.outcomes
                                           if o.get("outcome") == TEAM_ANSWER])
    return bool(latest) and replied < latest


def waiting_for_chris(chats: list[ChatState], since: float) -> list[str]:
    """Labels of chats left for Chris since `since` (staff `status`)."""
    return [_who(c) for c in chats if left_for_chris(c, since)]


def _line(state: ChatState, outcomes: list[dict]) -> str:
    parts = [f"{o.get('intent') or 'message'} ({o['outcome']})" for o in outcomes]
    return f"- {_who(state)}: {', '.join(parts)}"


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
    # Paused chats in the same groups as STATUS (owner, 25 Nov 2026): a flat list
    # of 26 was too long to act on. A chat already under "Left for you" isn't
    # repeated as waiting.
    held = [c for c in paused if c.mode_reason != WATCHLIST]
    groups = status_groups(held, now)
    unanswered = [u for u in groups["unanswered"]
                  if not any(u[:u.index(")") + 1] in l for l in left)]
    hand_back, rest = groups["hand_back"], groups["rest"]
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
        if unanswered:
            sections.append(f"Waiting on a reply ({len(unanswered)}): paused chats where the "
                            "customer wrote last, in the last 24 hours.\n"
                            + "\n".join(f"- {u}" for u in unanswered))
        if failed:
            sections.append(f"Failures ({len(failed)}), please check these chats:\n"
                            + "\n".join(failed))
        if hand_back:
            sections.append(f"Ready to hand back ({len(hand_back)}): the assistant was in these "
                            "chats until you stepped in. Text RESUME and the number (e.g. "
                            "RESUME 004) to the Goji number from your phone; the assistant "
                            "won't message them, it just answers their next message.\n"
                            + "\n".join(f"- {h}" for h in hand_back))
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
        if rest:
            sections.append(f"You're handling {len(rest)} more yourself: the assistant stays "
                            "out of these until you text RESUME and the number. A chat you "
                            "wrote in comes back by itself if they write 2 weeks after your "
                            "last message.\n" + "\n".join(f"- {r}" for r in rest))
        body = ("The WhatsApp assistant's last 24 hours (to "
                f"{day:%H:%M %a %d %b} SGT).\n\n" + "\n\n".join(sections) + "\n\n"
                "Only the chats under \"Left for you\", \"Waiting on a reply\" and "
                "\"Failures\" need you. Open them in the WhatsApp Business app.\n")
    line = (f"Goji assistant, last 24h: {len(answered)} chat(s) answered, "
            f"{len(left)} left for you, {len(failed)} failure(s)."
            + (f" {len(junk)} off-topic, no action needed." if junk else "")
            + (f" Waiting on a reply: {', '.join(unanswered)}." if unanswered else "")
            + (f" Ready to hand back, text RESUME and the number: {', '.join(hand_back)}."
               if hand_back else "")
            + (f" You're handling {len(rest)} more yourself (STATUS ALL lists them)."
               if rest else "")
            + " Details in your email.")
    return {"subject": subject, "body": body, "line": line,
            "answered": len(answered), "left": len(left), "failed": len(failed),
            "paused": len(held), "unanswered": len(unanswered), "hand_back": len(hand_back),
            "off_topic": len(junk), "watched": len(watched)}
