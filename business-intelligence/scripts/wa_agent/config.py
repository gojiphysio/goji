"""
wa_agent config: the WhatsApp assistant's knobs, all overridable by env var.

The rule this service is built around: **the model proposes, the code
disposes.** Claude drafts a reply and says what kind of question it was; every
decision about whether that reply reaches a customer (agent hours, per-intent
autonomy, confidence floor, human takeover, kill switch) is made here and in
policy.py, never in the prompt.
"""
from __future__ import annotations

import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


PROJECT = os.environ.get("GCP_PROJECT", "goji-bi")

# --- Claude -------------------------------------------------------------------
# "api" (Messages API, the real path) or "cli" (TEMPORARY: `claude -p` with the
# local login, for testing model behaviour before the API key; cli_backend.py).
BACKEND = os.environ.get("WA_AGENT_BACKEND", "api")
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
CLI_TIMEOUT_S = int(os.environ.get("WA_AGENT_CLI_TIMEOUT_S", "120"))
MODEL = os.environ.get("WA_AGENT_MODEL", "claude-opus-5-5")
# Short conversational turns: low effort keeps replies quick. Raise per the eval.
EFFORT = os.environ.get("WA_AGENT_EFFORT", "low")
MAX_TOKENS = int(os.environ.get("WA_AGENT_MAX_TOKENS", "4000"))
# Tool rounds per inbound message before we give up and escalate.
MAX_TOOL_ROUNDS = int(os.environ.get("WA_AGENT_MAX_TOOL_ROUNDS", "5"))
# Customer/agent/staff messages replayed to the model as conversation history.
HISTORY_MESSAGES = int(os.environ.get("WA_AGENT_HISTORY_MESSAGES", "20"))

# --- WhatsApp transport -------------------------------------------------------
# Defaults are Meta's Cloud API. A provider (Dualhook, 360dialog, ...) changes
# the base URL and auth header only; the payloads stay Cloud API shaped.
WA_API_BASE = os.environ.get("WA_API_BASE", "https://graph.facebook.com/v23.0")
WA_PHONE_NUMBER_ID = os.environ.get("WA_PHONE_NUMBER_ID", "")
# Meta: /{phone_number_id}/messages. 360dialog-style providers: /messages.
WA_SEND_PATH = os.environ.get("WA_SEND_PATH", "/{phone_number_id}/messages")
WA_AUTH_HEADER = os.environ.get("WA_AUTH_HEADER", "Authorization")
WA_AUTH_PREFIX = os.environ.get("WA_AUTH_PREFIX", "Bearer ")
WA_TOKEN = os.environ.get("WA_TOKEN", "")
# Webhook handshake (GET) and payload signature (POST, X-Hub-Signature-256).
WA_VERIFY_TOKEN = os.environ.get("WA_VERIFY_TOKEN", "")
WA_APP_SECRET = os.environ.get("WA_APP_SECRET", "")
# For providers that forward webhooks without Meta's signature: they POST to
# /webhook/<this token> instead. Long and random; empty disables the route.
WA_WEBHOOK_URL_TOKEN = os.environ.get("WA_WEBHOOK_URL_TOKEN", "")

# --- Handoff policy -----------------------------------------------------------
# Global off switch. While true the service logs everything and sends nothing.
KILL_SWITCH = _env_bool("WA_AGENT_KILL_SWITCH", False)
# After a human (Chris) writes in a chat, the agent stays silent this long.
HUMAN_IDLE_HANDBACK_S = int(os.environ.get("WA_AGENT_HUMAN_IDLE_S", str(24 * 3600)))
# A chat paused because a person wrote in it goes back to the agent on the
# customer's first message this long after that person's last message
# (owner, 24 Nov 2026: 2 weeks). Deliberate pauses never lapse.
HUMAN_PAUSE_S = int(os.environ.get("WA_AGENT_HUMAN_PAUSE_S", str(14 * 86400)))
# Wait this long before sending, then re-check whether a human replied meanwhile.
PRE_SEND_HOLD_S = float(os.environ.get("WA_AGENT_PRE_SEND_HOLD_S", "20"))
# Wait this long after a customer message before calling the model, so a burst
# ("hi" / "quick question" / "how much is...") becomes one run, not three.
DEBOUNCE_S = float(os.environ.get("WA_AGENT_DEBOUNCE_S", "6"))
# Below this self-reported confidence a reply is drafted, never sent.
# Below this an auto-send intent drafts instead (19 Nov 2026: 0.8 -> 0.7; the
# model scores good replies 0.75-0.85, and links, numbers and booking actions
# are checked in code whatever the score).
MIN_CONFIDENCE = float(os.environ.get("WA_AGENT_MIN_CONFIDENCE", "0.7"))
# Off-topic messages in a row before the chat goes quiet on the watch list
# (paused, kept HOLD_DAYS; staff RESUME it if it was a real customer).
OFF_TOPIC_LIMIT = int(os.environ.get("WA_AGENT_OFF_TOPIC_LIMIT", "3"))
# "all" or "after_hours" (outside Mon-Sat 08:00-20:00 SGT, the clinic's hours).
AGENT_HOURS = os.environ.get("WA_AGENT_HOURS", "all")

# What happens to a proposal of each intent: auto (send) | draft | escalate.
# Anything not listed is drafted. Phase 0 runs on test numbers, so FAQ-type
# intents auto-send to exercise the full path; tighten for Phase 1.
INTENT_POLICY: dict[str, str] = {
    "greeting": "auto",
    "faq": "auto",
    "pricing": "auto",
    "location_hours": "auto",
    "service_fit": "auto",
    "availability": "auto",
    "booking": "auto",
    # "When's my appointment?" / "am I booked for Sat?": answered from the
    # patient lookup or my_appointments, keyed on the chat's own number.
    "existing_appointment": "auto",
    # The agent moves the appointment itself (goji-booking /internal/reschedule)
    # after the customer confirms; Chris only hears about failures.
    "reschedule": "auto",
    # Same for cancelling with 24 hours' notice or more (goji-booking
    # /internal/cancel); inside 24 hours the fee is Chris's call, so
    # policy.decide drafts it (owner, 24 Nov 2026).
    "cancel": "auto",
    "billing": "draft",
    "clinical": "draft",
    "complaint": "draft",
    "urgent": "escalate",
    # Symptoms getting worse that need seeing soon, short of a 995 red flag
    # (harder to walk, spreading numbness or weakness): the agent shows calm,
    # proportionate concern, says it's let the team know and offers the
    # earliest slots, today's first, and
    # Chris is pinged as it sends. The chat stays with the agent so it can book
    # the slot they pick (owner, 24 Nov 2026).
    "priority": "send_alert",
    "sensitive": "escalate",  # pregnancy loss, birth trauma, crises: agent goes quiet
    "human_requested": "escalate",
    "other": "draft",
    # "Is this Chris?" with no request yet: the agent answers as the front desk
    # and asks for a message. Chris is told only when they leave one (escalation).
    "person_check": "auto",
    # A photo: the agent can't see it, thanks them and says the team will look.
    "media_received": "auto",
    # Wrong numbers, unrelated questions, attempts to misuse the chat: a short
    # front-desk reply, whatever the confidence, and never a ping (owner,
    # 23 Nov 2026). policy.decide handles it; OFF_TOPIC_LIMIT in a row pauses
    # the chat on the watch list.
    "off_topic": "auto",
}
INTENTS = tuple(INTENT_POLICY)

# --- Go-live rollout ------------------------------------------------------------
# Stage presets (WA_AGENT_STAGE 0-3; Firestore flags doc "rollout" overrides,
# see resolve_rollout). The owner's call (19 Nov 2026): the assistant drives by
# itself, so no stage drafts. What today's policy drafts becomes a handover
# with a holding reply ("escalate"), except in stage 0, where everything off
# the safe list is left alone for Chris ("leave": silent, no notice). A red
# flag ("urgent") always gets the 995/A&E reply and alerts staff (decision D1).
# Unset stage: today's INTENT_POLICY above, drafts and all, so tests and local
# runs behave as before. A deployed service sets a stage.
LEAVE = "leave"
SEND_ALERT = "send_alert"  # reply goes out at once AND staff are pinged
# Health flags: never left for Chris silently or drafted, in any stage.
RED_FLAG_INTENTS = frozenset({"urgent", "priority"})
SAFE_INTENTS = frozenset({"greeting", "faq", "pricing", "location_hours", "availability",
                          "service_fit", "person_check", "media_received", "off_topic",
                          "booking"})  # direct booking on from day one (owner's call)
STAGE2_EXTRA = frozenset({"existing_appointment", "reschedule", "cancel"})
STAGES = (0, 1, 2, 3)


def stage_policy(stage: int | None) -> dict[str, str]:
    """The INTENT_POLICY preset for a rollout stage. Hours are not part of a
    stage: WA_AGENT_HOURS (or the rollout doc's "hours") sets those."""
    if stage not in STAGES:
        return dict(INTENT_POLICY)
    if stage == 3:
        return {i: ("escalate" if r == "draft" else r) for i, r in INTENT_POLICY.items()}
    auto = SAFE_INTENTS | (STAGE2_EXTRA if stage == 2 else frozenset())
    off_list = LEAVE if stage == 0 else "escalate"
    return {i: ("auto" if i in auto else INTENT_POLICY[i] if i in RED_FLAG_INTENTS else off_list)
            for i in INTENT_POLICY}


def _env_stage() -> int | None:
    raw = os.environ.get("WA_AGENT_STAGE", "").strip()
    return int(raw) if raw.isdigit() and int(raw) in STAGES else None


STAGE = _env_stage()
# "quiet": the go-live cut-off and paused chats alone decide which chats the agent may take.
# "new_only": also silent ("out_of_scope") for any number with a patient record
# or an earlier chat.
CONTACT_SCOPES = ("quiet", "new_only")
CONTACT_SCOPE = os.environ.get("WA_AGENT_CONTACT_SCOPE", "quiet")
if CONTACT_SCOPE not in CONTACT_SCOPES:
    CONTACT_SCOPE = "quiet"
HOURS_VALUES = ("all", "after_hours")


def resolve_rollout(flags: dict | None) -> dict:
    """Stage, contact scope and hours: the Firestore rollout doc first (so a
    redeploy can't silently reset them), env as the default. Invalid or
    missing values in the doc fall back to env."""
    f = flags or {}
    stage = f.get("stage")
    stage = stage if isinstance(stage, int) and not isinstance(stage, bool) \
        and stage in STAGES else STAGE
    scope = f.get("contact_scope") if f.get("contact_scope") in CONTACT_SCOPES else CONTACT_SCOPE
    hours = f.get("hours") if f.get("hours") in HOURS_VALUES else AGENT_HOURS
    return {"stage": stage, "contact_scope": scope, "hours": hours}


# The go-live cut-off (Chris, 19 Nov 2026): at go-live, chats with a message
# either way in the GOLIVE_LOOKBACK_DAYS before it are Chris's, and pause on
# their next message. Go-live is a moment someone sets (POST /admin/go-live,
# Firestore flag "golive"); WA_AGENT_GO_LIVE (epoch seconds) is the fallback.
# A deployed (Firestore) run with neither stays silent ("not_live"): it only
# records message times until then. Local memory runs are always live.
GOLIVE_LOOKBACK_DAYS = int(os.environ.get("WA_AGENT_GOLIVE_LOOKBACK_DAYS", "30"))
GO_LIVE = float(os.environ.get("WA_AGENT_GO_LIVE", "0") or 0)

# Staff personal WhatsApp numbers (E.164 digits): Chris, optionally Charles.
# They get a short WhatsApp when a chat needs them, can text stop / start /
# status, and are never treated as customers.
STAFF = frozenset(
    p.strip() for p in os.environ.get("WA_AGENT_STAFF", "").split(",") if p.strip()
)
# Approved template for a ping outside the staff member's 24h window. Body:
# "Staff alert: chat {{1}} on Goji's WhatsApp needs a reply from the team.
# Reason: {{2}}. Open the chat in the WhatsApp Business app to respond."
# ({{1}} "Mei (#004)", {{2}} the reason; staff.template_params). v1
# (goji_staff_alert, one parameter) was recategorised as marketing by Meta.
STAFF_TEMPLATE = os.environ.get("WA_AGENT_STAFF_TEMPLATE", "goji_staff_alert_v2")


def _referrers(raw: str) -> dict[str, str]:
    """"6580000001=Dr Ong,6580000002=Dr Tan" -> {number: label}. A bare number
    is labelled "a referring doctor"."""
    out = {}
    for part in raw.split(","):
        number, _, label = part.strip().partition("=")
        if number.strip():
            out[number.strip()] = label.strip() or "a referring doctor"
    return out


# Referring doctors' WhatsApp numbers (private env file, never the repo). Their
# photos are read for the patient's name and number and forwarded to
# REFERRAL_TO (referral.py); the agent never replies to them, Chris does.
REFERRERS = _referrers(os.environ.get("WA_AGENT_REFERRERS", ""))
# Who gets referral forwards: staff numbers (so their 24h window is tracked).
# Defaults to every staff number.
REFERRAL_TO = tuple(p.strip() for p in os.environ.get("WA_AGENT_REFERRAL_TO", "").split(",")
                    if p.strip()) or tuple(sorted(STAFF))

# Contacts the agent never answers (family, partners, VIP patients). E.164
# digits, comma-separated. Phase 1 moves this to a portal-editable store.
ALWAYS_HUMAN = frozenset(
    p.strip() for p in os.environ.get("WA_AGENT_ALWAYS_HUMAN", "").split(",") if p.strip()
)

# Phase 0 admin endpoints (take over / hand back / kill) are behind this token
# until they move into the front-desk portal's role-gated auth.
ADMIN_TOKEN = os.environ.get("WA_AGENT_ADMIN_TOKEN", "")
# One-tap feedback links in staff emails: the service's public base URL, and
# the key that signs the links (falls back to the admin token).
PUBLIC_URL = os.environ.get("WA_AGENT_PUBLIC_URL", "")
FEEDBACK_SECRET = os.environ.get("WA_AGENT_FEEDBACK_SECRET", "")
# Local battle-testing only (needs WA_AGENT_STATE=memory): drafts and staff
# notices are also sent to the tester's chat, clearly labelled, because a
# local run has no email for them to go to.
TEST_SHOW_DRAFTS = os.environ.get("WA_AGENT_TEST_SHOW_DRAFTS", "") == "1"
# Numbers allowed to send /reset from WhatsApp (E.164 digits, comma-separated).
# Any number may on a local run (WA_AGENT_STATE=memory); never anyone else.
# Appointment confirmations for website bookings, as an approved template
# (goji_appointment_confirmed). Off until the template is approved on the
# clinic's real number.
CONFIRMATIONS = _env_bool("WA_AGENT_CONFIRMATIONS", False)
CONFIRM_TEMPLATE = os.environ.get("WA_AGENT_CONFIRM_TEMPLATE", "goji_appointment_confirmed")
# A long reply may go out as 2 WhatsApp messages, the way Chris writes (owner,
# 24 Nov 2026). Capped because Meta bills each delivered service message past
# 1,000 a month per number (since 1 Oct 2026); a reply under SPLIT_MIN_WORDS is
# always one message.
MAX_BUBBLES = int(os.environ.get("WA_AGENT_MAX_BUBBLES", "2"))  # 1 = one message per reply
SPLIT_MIN_WORDS = int(os.environ.get("WA_AGENT_SPLIT_MIN_WORDS", "60"))
TURBO_AT_START = os.environ.get("WA_AGENT_TURBO", "") == "1"  # local runs: start in /turbo
TESTERS = frozenset(p.strip() for p in os.environ.get("WA_AGENT_TESTERS", "").split(",")
                    if p.strip())

# --- Tools --------------------------------------------------------------------
# Availability comes from goji-booking's 5-minute snapshot, never Plato
# directly: Plato allows 20 requests/min clinic-wide (see booking/README.md).
BOOKING_API_BASE = os.environ.get("BOOKING_API_BASE", "https://booking.gojiphysio.com")
# Booking links go through the trackable redirector (repo rule: no raw /book URL).
BOOKING_LINK_BASE = os.environ.get("BOOKING_LINK_BASE", "https://go.gojiphysio.com/wa-book")
SITE_BASE = "https://www.gojiphysio.com"
# Existing-patient lookup reads BigQuery. Off by default in Phase 0 so testers'
# numbers are never matched against real patient records by accident.
PATIENT_LOOKUP = _env_bool("WA_AGENT_PATIENT_LOOKUP", False)
# Direct booking (booking_client.py). Dry run until go-live: goji-booking checks
# the slot but writes nothing to Plato.
BOOKING_DRY_RUN = _env_bool("WA_AGENT_BOOKING_DRY_RUN", True)
BOOKING_SIMULATE = _env_bool("WA_AGENT_BOOKING_SIMULATE", False)  # local, no private route
# Shared with goji-booking for /internal/book and /internal/booking-confirmed.
INTERNAL_TOKEN = os.environ.get("WA_AGENT_INTERNAL_TOKEN", "")
# Times offered (or a booking stated back) stay open to a yes for a day. It was
# 30 minutes: a customer who waited on the team's answer to a clinical question
# picked a time 32 minutes after the offer and wasn't booked (25 Nov 2026).
# goji-booking checks the slot live when booking, so a stale pick is
# `slot_taken` ("that time was just taken"), never a double booking.
BOOKING_CONFIRM_WINDOW_S = 24 * 3600
# Local tone testing only (needs WA_AGENT_STATE=memory): made-up patient
# context for test numbers, JSON {"6591234567": {"returning": true,
# "first_name": "Sarah", "next_appointment": null, "last_visit": "2026-10-02"}}.
import json as _json
TEST_PATIENTS: dict = _json.loads(os.environ.get("WA_AGENT_TEST_PATIENTS", "") or "{}")

# Keep the 1-hour prompt cache warm while customers are likely to write, so the
# first message after a quiet spell doesn't pay the cold cache write (API only).
KEEP_WARM = _env_bool("WA_AGENT_KEEP_WARM", True)
# Cloud Tasks queue ("projects/P/locations/L/queues/Q"). Set: the webhook queues
# events and the work runs inside /tasks/run, so the service scales to zero and
# warming rides the queue (tasks.py). Unset: background threads (local runs).
TASKS_QUEUE = os.environ.get("WA_AGENT_TASKS_QUEUE", "")
# Writing the waiver tag to Plato. Off: the live test (19 Nov 2026) showed
# Plato's PUT /patient accepts {"tag": [...]} but doesn't save it, even for a
# tag that exists. Until the right API call is known, Chris is asked to add
# the tag herself. goji-booking's /internal/patient-tag now verifies by
# reading back, so turning this on can't silently "succeed".
PLATO_TAG_WRITES = _env_bool("WA_AGENT_PLATO_TAG_WRITES", False)
WARM_EVERY_S = int(os.environ.get("WA_AGENT_WARM_EVERY_S", str(50 * 60)))
WARM_HOURS = (7, 22)  # SGT, [start, end)

# --- Storage / logging --------------------------------------------------------
STATE_BACKEND = os.environ.get("WA_AGENT_STATE", "firestore")  # firestore | memory
FIRESTORE_COLLECTION = os.environ.get("WA_AGENT_COLLECTION", "wa_chats")
EVENTS_TABLE = f"{PROJECT}.marts.wa_agent_events"
LOG_EVENTS = _env_bool("WA_AGENT_LOG_EVENTS", True)
KB_PATH = os.environ.get(
    "WA_AGENT_KB", os.path.join(os.path.dirname(__file__), "_build", "kb.json")
)

# --- Escalation notice --------------------------------------------------------
NOTIFY_EMAIL = os.environ.get("WA_AGENT_NOTIFY_EMAIL", "hello@gojiphysio.com")
GMAIL_USER = os.environ.get("GMAIL_USER", "hello@gojiphysio.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
