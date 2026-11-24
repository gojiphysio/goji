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
message, or an admin hands back. `paused` leaves by hand-back, or, for a pause
that came from a person writing in the chat, by `apply_pause_expiry`.

Chris writing in a chat (an echo) pauses it: the agent is fully silent there
until she resumes it ("resume 004" on WhatsApp, or the admin hand-back), or
until HUMAN_PAUSE_S (14 days) pass after the last person's message, when the
customer's next message goes to the agent (owner, 24 Nov 2026). The 24h idle
hand-back only applies to handovers the agent made that no person answered
(Chris, 19 Nov 2026). A deliberate pause (PAUSE 004, the admin pause, the
watch list) never lapses.

The go-live cut-off: at go-live, a chat with a message either way in the
GOLIVE_LOOKBACK_DAYS (30) before go-live is Chris's (`pre_golive_chat`); its
next message pauses it. `owner` = "agent" once the agent has taken a chat (a
message passed the gate, or a hand-back), which exempts it from the cut-off.
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
HUMAN_REPLIED = "human_replied"  # mode_reason: a person wrote in the chat (on_human_message)


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
    owner: str = ""                # "agent" once the agent has taken the chat, else ""
    code: str = ""                 # short id staff use: "004" (resume 004)
    held: bool = False             # a pause record exists in the holds store (state.py)
    last_customer_at: float = 0.0  # latest customer message (webhook or history import)
    last_staff_at: float = 0.0     # latest business-number message from the app (echo or import)
    name: str = ""                 # WhatsApp profile name, for staff pings and the summary
    outcomes: list[dict] = field(default_factory=list)  # {at, intent, outcome}: morning summary
    off_topic_strikes: int = 0     # off-topic messages in a row (note_off_topic)

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
    holding_reply: str = ""  # the model's own handover message, sent when the code hands over


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
    state.owner = ""
    if state.mode == PAUSED and state.mode_reason == "pre_golive_chat":
        state.mode_reason = HUMAN_REPLIED  # she has stepped in: the 14-day clock applies
    # Fully silent until she resumes it, or HUMAN_PAUSE_S after her last
    # message (apply_pause_expiry); no 24h idle hand-back (Chris, 19 Nov 2026).
    return set_mode(state, PAUSED, HUMAN_REPLIED, now)


def apply_pause_expiry(state: ChatState, now: float,
                       pause_s: int = config.HUMAN_PAUSE_S) -> bool:
    """A chat paused because a person wrote in it goes back to the agent
    `pause_s` after that person's last message (owner, 24 Nov 2026: 2 weeks).
    Called on the customer's next message, so the customer is sent nothing
    until they write. The clock runs from the latest person's message, so a
    conversation Chris is still having never lapses mid-way. Deliberate pauses
    (PAUSE 004, admin pause, watch list) and pre-go-live chats she hasn't
    written in don't lapse. Returns True if the chat was handed back."""
    if state.mode != PAUSED or state.mode_reason != HUMAN_REPLIED:
        return False
    if now - max(state.last_human_at, state.mode_since) < pause_s:
        return False
    state.owner = "agent"
    state.off_topic_strikes = 0
    state.pending_for_chris, state.pending_draft, state.last_auto = "", {}, {}
    return set_mode(state, AGENT, "pause_expired", now)


# Handovers after which the agent goes fully quiet rather than waiting: a red
# flag, or something sensitive where routine answers in the thread read badly.
SILENT_HANDOVER_INTENTS = frozenset({"urgent", "sensitive"})


def handover_mode(intent: str) -> str:
    return HUMAN if intent in SILENT_HANDOVER_INTENTS else WAITING


def in_clinic_hours(now: float) -> bool:
    """Mon-Sat 08:00-20:00 SGT, the clinic's published hours."""
    t = datetime.fromtimestamp(now, SGT)
    return t.weekday() < 6 and 8 <= t.hour < 20


def pre_golive_chat(state: ChatState, prior_last_at: float, go_live: float,
                    lookback_days: int = config.GOLIVE_LOOKBACK_DAYS) -> bool:
    """The go-live cut-off: the latest message before this one (either side)
    fell in the `lookback_days` before go-live, so Chris was handling this chat
    when the agent went live. Not for a chat the agent has taken."""
    if not go_live or state.owner == "agent" or prior_last_at <= 0:
        return False
    return go_live - lookback_days * 86400 <= prior_last_at < go_live


def has_record(state: ChatState) -> bool:
    """We know something about this number (a chat, an import, an owner)."""
    return bool(state.owner or state.last_customer_at or state.last_staff_at or state.history)


def out_of_scope(scope: str, state: ChatState, had_record: bool, patient: dict) -> bool:
    """WA_AGENT_CONTACT_SCOPE=new_only: the agent only takes numbers it has
    never seen and that have no patient record. A chat it already took stays
    its own (so a burst of messages from a new number all pass)."""
    if scope != "new_only" or state.owner == "agent":
        return False
    return had_record or bool((patient or {}).get("returning"))


def gate(state: ChatState, now: float, *, kill_switch: bool = config.KILL_SWITCH,
         always_human: frozenset[str] = config.ALWAYS_HUMAN,
         agent_hours: str = config.AGENT_HOURS, not_live: bool = False,
         pre_golive: bool = False, scope_out: bool = False) -> Decision | None:
    """Checks that don't need a proposal. A Decision here means: don't even
    call the model. None means the agent may think about this message.
    `not_live` (a deployed run before go-live), `pre_golive`
    (`pre_golive_chat`) and `scope_out` (`out_of_scope`) come from the caller."""
    if kill_switch:
        return Decision(SILENT, "kill_switch")
    if state.wa_id in always_human:
        return Decision(SILENT, "always_human")
    if state.mode == PAUSED:
        return Decision(SILENT, WATCHLIST if state.mode_reason == WATCHLIST else "paused")
    if state.mode == HUMAN:
        return Decision(SILENT, "human_has_chat")
    if not_live:
        return Decision(SILENT, "not_live")
    if pre_golive:
        return Decision(SILENT, "pre_golive_chat")
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
# A [placeholder] the model left for Chris to fill in: never sent to a customer.
_PLACEHOLDER = re.compile(r"\[[^\[\]\n]{1,80}\]")


def reply_problems(reply: str) -> list[str]:
    """Links, emails or phone numbers in a reply that aren't Goji's own, and
    [placeholders] left for Chris."""
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
        elif host.endswith("gojiphysio.com") and host != "go.gojiphysio.com":
            # A page link must be a page that exists: a guessed URL is a 404.
            from .kb import site_paths
            known = site_paths()
            path = (parsed.path or "/").rstrip(".,!?") or "/"
            if known is not None and (path if path.endswith("/") else path + "/") not in known:
                problems.append("unknown_page")
    for email in _EMAIL.findall(reply):
        if email.lower() not in ALLOWED_EMAILS:
            problems.append("email")
    for num in _PHONE.findall(reply):
        if re.sub(r"\D", "", num) not in ALLOWED_NUMBERS:
            problems.append("phone")
    if _PLACEHOLDER.search(reply):
        problems.append("placeholder")
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


def split_bubbles(reply: str, max_bubbles: int | None = None,
                  min_words: int | None = None) -> list[str]:
    """Bubble breaks (<break> lines) the model may write. Each message past
    Meta's free 1,000 a month is billed, so a reply goes out as at most
    MAX_BUBBLES (2) messages, and as one when it's under SPLIT_MIN_WORDS:
    a short answer never splits, whatever the model wrote (24 Nov 2026)."""
    limit = max(1, max_bubbles if max_bubbles is not None else config.MAX_BUBBLES)
    floor = config.SPLIT_MIN_WORDS if min_words is None else min_words
    parts = [p.strip() for p in (reply or "").split(BREAK)]
    parts = [p for p in parts if p]
    if len(" ".join(parts).split()) < floor:
        limit = 1
    elif len(parts) == 1 and limit >= 2:
        parts = _split_after_opening(parts[0])
    if len(parts) > limit:
        parts = parts[:limit - 1] + ["\n\n".join(parts[limit - 1:])]
    return parts


OPENING_MAX_WORDS = 30  # a greeting or personal line, not the substance
REST_MIN_WORDS = 20


def _split_after_opening(text: str) -> list[str]:
    """A long reply the model didn't mark: the opening paragraph (greeting or
    personal line) goes first, the substance second, as Chris writes. Only at
    a blank line, so a list stays with the line that introduces it."""
    first, sep, rest = text.partition("\n\n")
    if sep and len(first.split()) <= OPENING_MAX_WORDS and len(rest.split()) >= REST_MIN_WORDS:
        return [first.strip(), rest.strip()]
    return [text]


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


OFF_TOPIC = "off_topic"
WATCHLIST = "watchlist"


def note_off_topic(state: ChatState, intent: str, now: float,
                   limit: int = config.OFF_TOPIC_LIMIT) -> bool:
    """Counts off-topic messages in a row; any other message resets the count.
    At `limit` the chat is paused on the watch list: the agent answered the
    first `limit`, and stays silent from the next one until staff resume it.
    Returns True if this message put the chat on the watch list."""
    if intent != OFF_TOPIC:
        state.off_topic_strikes = 0
        return False
    state.off_topic_strikes += 1
    return state.off_topic_strikes >= limit and set_mode(state, PAUSED, WATCHLIST, now)


def hours_until(appointment: dict | None, now: float) -> float:
    """Hours from `now` to a {date: YYYY-MM-DD, time: HH:MM} SGT appointment;
    -1 if there isn't one or it can't be read."""
    try:
        at = datetime.strptime(f"{appointment['date']} {appointment['time']}",
                               "%Y-%m-%d %H:%M").replace(tzinfo=SGT)
    except (TypeError, KeyError, ValueError):
        return -1.0
    return max(0.0, (at.timestamp() - now) / 3600)


def check_late_change(p: Proposal, appointment: dict | None, now: float) -> None:
    """The 24-hour rule can't rest on the model's hours_to_appointment alone
    (it sometimes leaves -1): for a reschedule or cancel, the patient record's
    next appointment counts too, and the sooner of the two wins, so a late
    change always reaches Chris (23 Nov 2026)."""
    if p.intent not in ("reschedule", "cancel"):
        return
    rec = hours_until(appointment, now)
    if rec >= 0 and (p.hours_to_appointment < 0 or rec < p.hours_to_appointment):
        p.hours_to_appointment = rec


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
    if proposal.intent == OFF_TOPIC and not proposal.failed:
        # Not worth Chris's time (owner, 23 Nov 2026): the polite reply goes
        # out whatever the confidence or an escalate flag, and a reply that
        # fails the content check is dropped, never handed over. It shows in
        # the morning summary only.
        if not proposal.reply.strip() or reply_problems(proposal.reply):
            return Decision(SILENT, "off_topic_unsafe_reply")
        return Decision(SEND, "off_topic")
    if rule == config.SEND_ALERT:
        # Getting worse (owner, 24 Nov 2026): the concerned reply with the
        # earliest slots goes out at once and staff are pinged as it does
        # (app.py). A reply that can't go out is still a handover, never a
        # draft: someone must hear about it now.
        if proposal.failed or not proposal.reply.strip():
            return Decision(ESCALATE, f"intent:{proposal.intent}:no_reply", holding=True)
        problems = reply_problems(proposal.reply)
        if problems:
            return Decision(ESCALATE, "content:" + ",".join(sorted(set(problems))), holding=True)
        return Decision(SEND, f"intent:{proposal.intent}")
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
        if d.action == DRAFT or (d.action == ESCALATE
                                 and proposal.intent not in config.RED_FLAG_INTENTS
                                 and not proposal.failed):
            return Decision(SILENT, "stage_leave")
        return d
    if d.action == DRAFT:
        return Decision(ESCALATE, f"handover:{d.reason}", holding=True)
    return d


HOLDING_MAX_WORDS = 90
GENERIC_HOLDING = {True: "Thanks for your message! I've passed it to the team and they'll "
                         "get back to you today.",
                   False: "Thanks for your message! I've passed it to the team and they'll "
                          "get back to you when we open."}


def holding_reply(p: Proposal, now: float) -> str:
    """What the customer gets when the code hands a message over instead of
    sending the model's reply: the model's own holding_reply (specific to what
    they asked, no promises that need a person) if it passes the same content
    check as any reply; else the generic line, timed to the clinic's hours."""
    text = (p.holding_reply or "").strip()
    if text and not p.failed and len(text.split()) <= HOLDING_MAX_WORDS \
            and not reply_problems(text):
        return text
    return GENERIC_HOLDING[in_clinic_hours(now)]


def customer_message(d: Decision, p: Proposal, now: float) -> str:
    """What the customer gets for a proposal that is sent or handed over.
    A handover sends the holding_reply, never `reply`: `reply` is the draft
    answer Chris gets to send or edit (owner, 23 Nov 2026). Red flags and
    sensitive topics are the exception: their reply (995, a warm
    acknowledgement) goes out at once. A reply that fails the content check
    is never sent either."""
    reply = (p.reply or "").strip()
    if d.action == ESCALATE and p.intent not in SILENT_HANDOVER_INTENTS:
        return holding_reply(p, now)
    if not reply or reply_problems(reply):
        return holding_reply(p, now)
    if p.intent == "priority":
        return with_team_line(reply)
    return reply


TEAM_LINE = "I've let the team know too, so they're aware."


def with_team_line(reply: str) -> str:
    """Getting worse: the customer is always told the team knows (they are
    pinged as it sends). The model usually says so; if it didn't, the line
    goes in after its opening sentence of concern."""
    if re.search(r"\bteam\b", reply, re.I):
        return reply
    first, sep, rest = reply.partition("\n\n")
    m = re.match(r"(.+?[.!])\s+(\S.*)", first, re.S)
    if m:
        first, rest = m.group(1), m.group(2) + (sep + rest if sep else "")
    return f"{first}\n\n{TEAM_LINE}" + (f"\n\n{rest}" if rest else "")


def human_replied_since(state: ChatState, since: float) -> bool:
    """The pre-send re-check: did a human write in this chat after `since`?
    (`waiting` doesn't count: Chris hasn't written yet.)"""
    return state.mode in (HUMAN, PAUSED) or state.last_human_at > since
