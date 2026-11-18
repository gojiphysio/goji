"""
Handoff policy: who answers a chat, and what happens to the agent's proposal.

Pure functions over plain data, so every rule is unit-tested without WhatsApp,
Claude or Firestore. Nothing here asks the model anything.

A chat is in one of three modes:
  agent   the agent may answer (subject to `decide`)
  human   a person has the chat; the agent stays silent until hand-back
  paused  silenced by an admin until explicitly handed back

Ways into `human`: Chris writes in the chat (echo), the agent escalates, an
admin takes over. Ways back to `agent`: HUMAN_IDLE_HANDBACK_S with no human
message, or an admin hands back. `paused` only leaves by admin hand-back.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta

from . import config

SGT = timezone(timedelta(hours=8))

AGENT, HUMAN, PAUSED = "agent", "human", "paused"
SEND, DRAFT, ESCALATE, SILENT = "send", "draft", "escalate", "silent"


@dataclass
class ChatState:
    wa_id: str
    mode: str = AGENT
    mode_reason: str = ""
    mode_since: float = 0.0
    last_human_at: float = 0.0
    history: list[dict] = field(default_factory=list)  # {role, text, ts, id}
    seen_ids: list[str] = field(default_factory=list)  # webhook de-dupe
    pending_draft: dict = field(default_factory=dict)  # {text, intent, at}: scored on Chris's reply
    last_auto: dict = field(default_factory=dict)      # {intent, at}: a rescue if Chris writes next

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: dict) -> "ChatState":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class Proposal:
    reply: str
    intent: str
    confidence: float
    escalate: bool
    escalation_reason: str = ""
    staff_note: str = ""


@dataclass
class Decision:
    action: str   # send | draft | escalate | silent
    reason: str


def set_mode(state: ChatState, mode: str, reason: str, now: float) -> bool:
    """Move the chat to `mode`. Returns True if it changed."""
    if state.mode == mode:
        return False
    state.mode, state.mode_reason, state.mode_since = mode, reason, now
    return True


def apply_idle_handback(state: ChatState, now: float,
                        idle_s: int = config.HUMAN_IDLE_HANDBACK_S) -> bool:
    """A `human` chat with no human message for `idle_s` returns to the agent.
    The clock runs from the later of the last human message and the takeover,
    so an escalation Chris never answered also hands back. `paused` never
    times out. Returns True if the chat was handed back."""
    if state.mode != HUMAN:
        return False
    since = max(state.last_human_at, state.mode_since)
    if now - since >= idle_s:
        return set_mode(state, AGENT, "idle_handback", now)
    return False


def on_human_message(state: ChatState, now: float) -> bool:
    """Chris (or anyone on the business number) wrote in this chat: the agent
    steps back. Returns True if this took the chat over."""
    state.last_human_at = now
    return set_mode(state, HUMAN, "human_replied", now)


def in_clinic_hours(now: float) -> bool:
    """Mon-Sat 08:00-20:00 SGT, the clinic's published hours."""
    t = datetime.fromtimestamp(now, SGT)
    return t.weekday() < 6 and 8 <= t.hour < 20


def gate(state: ChatState, now: float, *, kill_switch: bool = config.KILL_SWITCH,
         always_human: frozenset[str] = config.ALWAYS_HUMAN,
         agent_hours: str = config.AGENT_HOURS) -> Decision | None:
    """Checks that don't need a proposal. A Decision here means: don't even
    call the model. None means the agent may think about this message."""
    if kill_switch:
        return Decision(SILENT, "kill_switch")
    if state.wa_id in always_human:
        return Decision(SILENT, "always_human")
    if state.mode == PAUSED:
        return Decision(SILENT, "paused")
    if state.mode == HUMAN:
        return Decision(SILENT, "human_has_chat")
    if agent_hours == "after_hours" and in_clinic_hours(now):
        return Decision(SILENT, "clinic_hours")
    return None


# What a reply may contain, whatever the model was told or tricked into: only
# Goji's own links, email and numbers, plus Singapore's emergency lines.
ALLOWED_HOSTS = {"gojiphysio.com", "www.gojiphysio.com", "go.gojiphysio.com",
                 "maps.app.goo.gl", "www.instagram.com", "instagram.com"}
ALLOWED_EMAILS = {"hello@gojiphysio.com"}
ALLOWED_NUMBERS = {"83770401", "995", "1767", "1777"}
_URL = re.compile(r"(?:https?://|www\.)[^\s)>\]]+", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<![\w$.])(?:\+?65[\s-]?)?(\d{4}[\s-]?\d{4})(?![\w])")


def reply_problems(reply: str) -> list[str]:
    """Links, emails or phone numbers in a reply that aren't Goji's own."""
    problems = []
    for url in _URL.findall(reply):
        parsed = urlparse(url if "://" in url else "https://" + url)
        host = (parsed.hostname or "").lower()
        if host not in ALLOWED_HOSTS:
            problems.append(f"link:{host}")
        elif host.endswith("gojiphysio.com") and host != "go.gojiphysio.com" \
                and parsed.path.startswith("/book"):
            # Booking links must be the tracked go-link from booking_link (repo rule).
            problems.append("untracked_booking_link")
    for email in _EMAIL.findall(reply):
        if email.lower() not in ALLOWED_EMAILS:
            problems.append("email")
    for num in _PHONE.findall(reply):
        if re.sub(r"\D", "", num) not in ALLOWED_NUMBERS:
            problems.append("phone")
    return problems


_ACK = re.compile(
    r"(ok+(ay)?|k+|thanks?( you)?( so much)?|thank u|thx|ty|tq|noted|alright|sure|great|cool|"
    r"got it|will do|see you|perfect|nice)?[\s!.,~]*[\U0001F300-\U0001FAFF\u2600-\u27BF\u2764\uFE0F\s]*",
    re.I)


def is_acknowledgement(text: str, history: list[dict]) -> bool:
    """A bare "ok" / "thanks" / 👍 straight after we (or Chris) replied needs no
    answer, and no model call. A first message of "thanks" still gets one.
    `history` ends with this message, as stored."""
    t = text.strip()
    prior_role = history[-2]["role"] if len(history) >= 2 else ""
    return bool(t) and bool(_ACK.fullmatch(t)) and prior_role in ("agent", "staff")


def decide(proposal: Proposal, *, intent_policy: dict[str, str] = config.INTENT_POLICY,
           min_confidence: float = config.MIN_CONFIDENCE) -> Decision:
    """What happens to a proposal that passed `gate`.

    escalate  holding reply goes out, staff are notified, chat goes to `human`
    send      reply goes out (after the pre-send hold and re-check)
    draft     nothing goes out; staff get the suggested reply
    """
    if proposal.escalate:
        return Decision(ESCALATE, proposal.escalation_reason or "model_escalated")
    rule = intent_policy.get(proposal.intent, DRAFT)
    if rule == "escalate":
        return Decision(ESCALATE, f"intent:{proposal.intent}")
    if not proposal.reply.strip():
        return Decision(DRAFT, "empty_reply")
    problems = reply_problems(proposal.reply)
    if problems:
        return Decision(DRAFT, "content:" + ",".join(sorted(set(problems))))
    if proposal.confidence < min_confidence:
        return Decision(DRAFT, f"low_confidence:{proposal.confidence:.2f}")
    if rule == "auto":
        return Decision(SEND, f"intent:{proposal.intent}")
    return Decision(DRAFT, f"intent:{proposal.intent}")


def human_replied_since(state: ChatState, since: float) -> bool:
    """The pre-send re-check: did a human write in this chat after `since`?"""
    return state.mode in (HUMAN, PAUSED) or state.last_human_at > since
