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
    "cancel": "draft",
    "billing": "draft",
    "clinical": "draft",
    "complaint": "draft",
    "urgent": "escalate",
    "sensitive": "escalate",  # pregnancy loss, birth trauma, crises: agent goes quiet
    "human_requested": "escalate",
    "other": "draft",
    # "Is this Chris?" with no request yet: the agent answers as the front desk
    # and asks for a message. Chris is told only when they leave one (escalation).
    "person_check": "auto",
    # A photo: the agent can't see it, thanks them and says the team will look.
    "media_received": "auto",
}
INTENTS = tuple(INTENT_POLICY)

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
MAX_BUBBLES = int(os.environ.get("WA_AGENT_MAX_BUBBLES", "1"))  # 1 = one message per reply
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
BOOKING_CONFIRM_WINDOW_S = 30 * 60  # a pending booking expires if not confirmed
# Local tone testing only (needs WA_AGENT_STATE=memory): made-up patient
# context for test numbers, JSON {"6591234567": {"returning": true,
# "first_name": "Sarah", "next_appointment": null, "last_visit": "2026-10-02"}}.
import json as _json
TEST_PATIENTS: dict = _json.loads(os.environ.get("WA_AGENT_TEST_PATIENTS", "") or "{}")

# Keep the 1-hour prompt cache warm while customers are likely to write, so the
# first message after a quiet spell doesn't pay the cold cache write (API only).
KEEP_WARM = _env_bool("WA_AGENT_KEEP_WARM", True)
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
