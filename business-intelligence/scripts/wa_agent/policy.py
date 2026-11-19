"""
Handoff policy: who answers a chat, and what happens to the agent's proposal.

Pure functions over plain data, so every rule is unit-tested without WhatsApp,
Claude or Firestore. Nothing here asks the model anything.

A chat is in one of four modes:
  agent    the agent may answer (subject to `decide`)
  waiting  the agent handed a topic to Chris and she hasn't replied yet: it
           keeps answering everything else, but not that topic
  human    a person has the chat; the agent stays silent until hand-back
  paused   silenced by an admin until explicitly handed back

Ways into `human`: Chris writes in the chat (echo), the agent escalates, an
admin takes over. Ways back to `agent`: HUMAN_IDLE_HANDBACK_S with no human
message, or an admin hands back. `paused` only leaves by admin hand-back.

Separately from the mode, `owner` says whose chat it is under the 14-day rule
(Chris stays primary): "agent" once the agent has taken it (a message passed
the gate, or an admin handed it back), "human" once a person wrote in it (an
echo, history import, admin takeover or pause), "" for neither. A chat that
isn't the agent's, with a message either way in the last QUIET_DAYS, is left
to Chris (`recent_human_chat`), even after the 24h idle hand-back (decision D2).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta

from . import config

SGT = timezone(timedelta(hours=8))

AGENT, HUMAN, PAUSED, WAITING = "agent", "human", "paused", "waiting"
LATE_CHANGE_H = 24  # the cancellation policy's notice period (gojiphysio.com/services/#faq)
SEND, DRAFT, ESCALATE, SILENT = "send", "draft", "escalate", "silent"


@dataclass
class ChatState:
    wa_id: str
    mode: str = AGENT
    mode_reason: str = ""
    mode_since: float = 0.0
    last_human_at: float = 0.0
    pending_for_chris: str = ""  # waiting: what was handed over (the staff note)
    pending_booking: dict = field(default_factory=dict)  # stated back, awaiting the customer's yes
    pending_move: dict = field(default_factory=dict)     # same, for moving an appointment
    closer_id: str = ""  # our reply to a bare "thanks": the next one gets silence
    booked: dict = field(default_factory=dict)  # latest booking (agent or website), for context
    patient: dict = field(default_factory=dict)  # returning-patient lookup, cached per chat
    patient_at: float = 0.0
    history: list[dict] = field(default_factory=list)  # {role, text, ts, id}
    seen_ids: list[str] = field(default_factory=list)  # webhook de-dupe
    pending_draft: dict = field(default_factory=dict)  # {text, intent, at}: scored on Chris's reply
    last_auto: dict = field(default_factory=dict)      # {intent, at}: a rescue if Chris writes next
    owner: str = ""                # 14-day rule: "agent" | "human" | ""
    last_customer_at: float = 0.0  # latest customer message (webhook or history import)
    last_staff_at: float = 0.0     # latest business-number message from the app (echo or import)
    name: str = ""                 # WhatsApp profile name, for staff pings and the summary
    outcomes: list[dict] = field(default_factory=list)  # {at, intent, outcome}: morning summary

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
    hours_to_appointment: float = -1.0  # reschedule/cancel: the booking being changed; -1 unknown
    booking: dict = field(default_factory=dict)  # details collected for direct booking
    confirm_booking: bool = False                # the customer just confirmed the pending one
    move: dict = field(default_factory=dict)     # old/new date+time for moving an appointment
    confirm_move: bool = False
    failed: bool = False  # agent._escalation: the model or a tool failed, nothing to judge


@dataclass
class Decision:
    action: str   # send | draft | escalate | silent
    reason: str
    # escalate only: the model's reply wasn't written as a handover (the intent
    # was a draft or auto before the stage made it a handover), so the code's
    # holding reply goes out instead of it.
    holding: bool = False


def set_mode(state: ChatState, mode: str, reason: str, now: float) -> bool:
    """Move the chat to `mode`. Returns True if it changed."""
    if state.mode == mode:
        return False
    state.mode, state.mode_reason, state.mode_since = mode, reason, now
    return True


def apply_idle_handback(state: ChatState, now: float,
                        idle_s: int = config.HUMAN_IDLE_HANDBACK_S) -> bool:
    """A `human` or `waiting` chat with no human message for `idle_s` returns
    to the agent.
    The clock runs from the later of the last human message and the takeover,
    so an escalation Chris never answered also hands back. `paused` never
    times out. Returns True if the chat was handed back."""
    if state.mode not in (HUMAN, WAITING):
        return False
    since = max(state.last_human_at, state.mode_since)
    if now - since >= idle_s:
        state.pending_for_chris = ""
        return set_mode(state, AGENT, "idle_handback", now)
    return False


def on_human_message(state: ChatState, now: float) -> bool:
    """Chris (or anyone on the business number) wrote in this chat: the agent
    steps back. Returns True if this took the chat over."""
    state.last_human_at = now
    state.pending_for_chris = ""
    return set_mode(state, HUMAN, "human_replied", now)


# Handovers after which the agent goes fully quiet rather than waiting: a red
# flag, or something sensitive where routine answers in the thread read badly.
SILENT_HANDOVER_INTENTS = frozenset({"urgent", "sensitive"})


def handover_mode(intent: str) -> str:
    return HUMAN if intent in SILENT_HANDOVER_INTENTS else WAITING


def in_clinic_hours(now: float) -> bool:
    """Mon-Sat 08:00-20:00 SGT, the clinic's published hours."""
    t = datetime.fromtimestamp(now, SGT)
    return t.weekday() < 6 and 8 <= t.hour < 20


def recent_human_chat(state: ChatState, prior_last_at: float, now: float,
                      quiet_days: int = config.QUIET_DAYS) -> bool:
    """The 14-day rule. A chat the agent hasn't taken (owner != "agent") whose
    latest earlier message, from either side, is under `quiet_days` old is
    Chris's: the agent stays out. `prior_last_at` is that latest message's
    time, read before the current message was recorded. 0 days = off."""
    if quiet_days <= 0 or state.owner == "agent" or prior_last_at <= 0:
        return False
    return now - prior_last_at < quiet_days * 86400


def has_record(state: ChatState) -> bool:
    """We know something about this number (a chat, an import, an owner)."""
    return bool(state.owner or state.last_customer_at or state.last_staff_at or state.history)


def coverage_gap_open(observed_since: float, history_imported: bool, now: float,
                      quiet_days: int = config.QUIET_DAYS) -> bool:
    """We started watching the number less than `quiet_days` ago and the
    coexistence history hasn't been imported: a number with no record may be
    a chat Chris had before we could see it. Off when OBSERVED_SINCE is unset."""
    if quiet_days <= 0 or not observed_since or history_imported:
        return False
    return now - observed_since < quiet_days * 86400


def out_of_scope(scope: str, state: ChatState, had_record: bool, patient: dict) -> bool:
    """WA_AGENT_CONTACT_SCOPE=new_only: the agent only takes numbers it has
    never seen and that have no patient record. A chat it already took stays
    its own (so a burst of messages from a new number all pass)."""
    if scope != "new_only" or state.owner == "agent":
        return False
    return had_record or bool((patient or {}).get("returning"))


def gate(state: ChatState, now: float, *, kill_switch: bool = config.KILL_SWITCH,
         always_human: frozenset[str] = config.ALWAYS_HUMAN,
         agent_hours: str = config.AGENT_HOURS, prior_last_at: float = 0.0,
         quiet_days: int = config.QUIET_DAYS, coverage_gap: bool = False,
         scope_out: bool = False) -> Decision | None:
    """Checks that don't need a proposal. A Decision here means: don't even
    call the model. None means the agent may think about this message.
    `coverage_gap` and `scope_out` are worked out by the caller
    (`coverage_gap_open` + `has_record`, `out_of_scope`)."""
    if kill_switch:
        return Decision(SILENT, "kill_switch")
    if state.wa_id in always_human:
        return Decision(SILENT, "always_human")
    if state.mode == PAUSED:
        return Decision(SILENT, "paused")
    if state.mode == HUMAN:
        return Decision(SILENT, "human_has_chat")
    if recent_human_chat(state, prior_last_at, now, quiet_days):
        return Decision(SILENT, "recent_human_chat")
    if coverage_gap:
        return Decision(SILENT, "coverage_gap")
    if agent_hours == "after_hours" and in_clinic_hours(now):
        return Decision(SILENT, "clinic_hours")
    if scope_out:
        return Decision(SILENT, "out_of_scope")
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


_ACK_WORD = (r"(ok+(ay)?|k+|thanks?( you)?( so much)?|thank u|thx|ty|tq|noted|alright|sure|"
             r"great|cool|got it|will do|see you( then| soon)?|perfect|nice|awesome)")
# One or more acknowledgement words ("ok thanks!", "noted, thank you"), then
# punctuation or emoji. Anything else is a real message.
_ACK = re.compile(
    rf"({_ACK_WORD}[\s!.,~]*)*[\U0001F300-\U0001FAFF\u2600-\u27BF\u2764\uFE0F\s!.,~]*",
    re.I)


def is_acknowledgement(text: str, history: list[dict]) -> bool:
    """A bare "ok" / "thanks" / 👍 straight after we (or Chris) replied needs no
    answer, and no model call. A first message of "thanks" still gets one.
    `history` ends with this message, as stored."""
    t = text.strip()
    prior_role = history[-2]["role"] if len(history) >= 2 else ""
    return bool(t) and bool(_ACK.fullmatch(t)) and prior_role in ("agent", "staff")


BREAK = "<break>"


def split_bubbles(reply: str, max_bubbles: int | None = None) -> list[str]:
    """Bubble breaks (<break> lines) the model may write. Multi-bubble replies
    are off (19 Nov 2026: service messages may be charged per message), so by
    default everything is one message; WA_AGENT_MAX_BUBBLES turns them back on."""
    limit = max(1, max_bubbles if max_bubbles is not None else config.MAX_BUBBLES)
    parts = [p.strip() for p in (reply or "").split(BREAK)]
    parts = [p for p in parts if p]
    if len(parts) > limit:
        parts = parts[:limit - 1] + ["\n\n".join(parts[limit - 1:])]
    return parts


def as_one_message(reply: str) -> str:
    """For staff emails, drafts and the transcript: bubbles as paragraphs."""
    return "\n\n".join(split_bubbles(reply, max_bubbles=1))


CLARIFY_MIN_CONFIDENCE = 0.5
_FACTISH = re.compile(r"\$\s?\d|https?://|www\.", re.I)


def is_clarifying_question(reply: str) -> bool:
    """A short reply whose only job is one question, with no prices or links
    in it (facts that could be wrong). Echoing the customer's own time back
    ("is it today at 3pm?") is fine."""
    r = (reply or "").strip()
    return (0 < len(r.split()) <= 40 and r.count("?") == 1
            and r.rstrip(" :)😊🙂").endswith("?") and not _FACTISH.search(r))


def decide(proposal: Proposal, *, intent_policy: dict[str, str] = config.INTENT_POLICY,
           min_confidence: float = config.MIN_CONFIDENCE) -> Decision:
    """What happens to a proposal that passed `gate`.

    escalate  holding reply goes out, staff are notified, chat goes to `human`
    send      reply goes out (after the pre-send hold and re-check)
    draft     nothing goes out; staff get the suggested reply
    """
    rule = intent_policy.get(proposal.intent, DRAFT)
    if rule == config.LEAVE:
        return Decision(SILENT, "stage_leave")
    if proposal.escalate and not (rule == "draft" and proposal.intent != "urgent"):
        return Decision(ESCALATE, proposal.escalation_reason or "model_escalated")
    # A draft-for-Chris intent stays a draft even if the model wanted to hand
    # over: the policy decides, and Chris checks the reply before it goes out.
    if rule == "escalate":
        # The model writes the handover reply itself only for the intents it
        # was told hand over; for anything else its reply is an answer (maybe
        # "I've cancelled it"), so the code's holding reply goes out instead.
        return Decision(ESCALATE, f"intent:{proposal.intent}",
                        holding=proposal.intent not in MODEL_HANDOVER_INTENTS)
    if proposal.intent == "reschedule" and 0 <= proposal.hours_to_appointment < LATE_CHANGE_H:
        # Inside the 24-hour policy: whether the $50 fee applies or is waived
        # is Chris's call, so she checks the reply first.
        return Decision(DRAFT, "late_change")
    if not proposal.reply.strip():
        return Decision(DRAFT, "empty_reply")
    problems = reply_problems(proposal.reply)
    if problems:
        return Decision(DRAFT, "content:" + ",".join(sorted(set(problems))))
    if proposal.confidence < min_confidence:
        if rule in ("auto", "auto_notify") and is_clarifying_question(proposal.reply) \
                and proposal.confidence >= CLARIFY_MIN_CONFIDENCE:
            # Asking is safe: a short question with no facts in it can't be wrong
            # the way an answer can, and a draft would leave the customer waiting.
            return Decision(SEND, f"clarifying_question:{proposal.confidence:.2f}")
        return Decision(DRAFT, f"low_confidence:{proposal.confidence:.2f}")
    if rule in ("auto", "auto_notify"):
        return Decision(SEND, f"intent:{proposal.intent}")
    return Decision(DRAFT, f"intent:{proposal.intent}")


# Intents the model is instructed to answer with a handover message (red flag
# guidance, a sensitive acknowledgement, "Chris will get back to you").
MODEL_HANDOVER_INTENTS = frozenset({"urgent", "sensitive", "human_requested"})


def apply_stage(d: Decision, proposal: Proposal, stage: int | None) -> Decision:
    """No drafts in a rollout stage (owner's call): what `decide` would draft
    becomes a handover with the holding reply, and in stage 0 the assistant
    leaves anything it won't answer itself to Chris, silently. A red flag
    always escalates (D1). Unset stage: `decide`'s answer unchanged."""
    if stage not in config.STAGES:
        return d
    if stage == 0:
        # A failure still escalates: a person must hear of it (AGENTS.md).
        if d.action == DRAFT or (d.action == ESCALATE and proposal.intent != "urgent"
                                 and not proposal.failed):
            return Decision(SILENT, "stage_leave")
        return d
    if d.action == DRAFT:
        return Decision(ESCALATE, f"handover:{d.reason}", holding=True)
    return d


def human_replied_since(state: ChatState, since: float) -> bool:
    """The pre-send re-check: did a human write in this chat after `since`?
    (`waiting` doesn't count: Chris hasn't written yet.)"""
    return state.mode in (HUMAN, PAUSED) or state.last_human_at > since
