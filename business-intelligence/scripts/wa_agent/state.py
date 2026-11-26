"""
Per-chat state (mode, recent transcript, de-dupe ids) and the global kill flag.

Firestore in production (free tier covers clinic volume), memory in tests.
The service runs as ONE instance (--max-instances=1, like goji-booking), so a
per-chat in-process lock is enough to serialise webhooks for the same chat.

Transcripts are patient data: each chat doc carries `expire_at`, and the
Firestore TTL policy set up by deploy.sh deletes it RETENTION_DAYS after the
last message. Message text never goes to BigQuery (see events.py).

The flags collection (`<collection>_flags`) holds small global docs:
  kill_switch       {on, at}
  autonomy          {intents, at}                  learning.py demotion record
  rollout           {stage, contact_scope, hours}  go-live settings; env is the default
  history_imported  {on, at, source}               coexistence history import landed
  golive            {at, source}                   go-live moment (the 30-day cut-off)
  codes             {next}                         counter for chat codes ("004")
  (and <collection>_holds/{wa_id}: {mode, mode_reason, mode_since, code},
   kept HOLD_DAYS for paused chats, no text)
  staff             {windows: {wa_id: ts},         staff numbers' last inbound (24h window)
                     welcomed: {wa_id: ts}}        and who has had the walkthrough
  (and <collection>_pings/{ping message id}: {wa_id, at}, kept PING_DAYS, so
   a staff swipe-reply to a ping finds its chat; no text)
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict

from . import config
from .policy import ChatState

RETENTION_DAYS = 30
# A paused chat stays paused after its transcript expires: a small "hold"
# record (mode, reason, code, times; no text) outlives the chat doc, so a
# deliberately paused customer coming back after 30 quiet days still reaches
# Chris, not the agent (Chris, 19 Nov 2026). A pause from Chris writing lapses
# after 14 days (policy.apply_pause_expiry). Removed on resume/forget.
HOLD_DAYS = 365
# A staff ping's message id -> the chat it was about, so Chris can swipe-reply
# to the ping with the team's answer (app._staff_answer).
PING_DAYS = 7
# Referral de-dupe marks and forwards held for a staff number whose 24h window
# was shut (<collection>_referrals, TTL on expire_at).
REFERRAL_DAYS = 7
HISTORY_KEEP = 50
SEEN_KEEP = 200
OUTCOMES_KEEP = 20
FLAG_CACHE_S = 5  # global flags bite within 5s without a read per message


def append_history(state: ChatState, role: str, text: str, ts: float, msg_id: str = "") -> None:
    """role: customer | agent | staff | team (the team's answer Chris sent the
    assistant to pass on: context for the model, never sent as written)."""
    state.history.append({"role": role, "text": text, "ts": ts, "id": msg_id})
    del state.history[:-HISTORY_KEEP]


def mark_seen(state: ChatState, msg_id: str) -> bool:
    """Meta retries webhooks. Returns False if this message was already handled."""
    if not msg_id:
        return True
    if msg_id in state.seen_ids:
        return False
    state.seen_ids.append(msg_id)
    del state.seen_ids[:-SEEN_KEEP]
    return True


def hold_doc(state: ChatState) -> dict:
    return {"mode": state.mode, "mode_reason": state.mode_reason,
            "mode_since": state.mode_since, "last_human_at": state.last_human_at,
            "code": state.code}


def from_hold(wa_id: str, hold: dict | None) -> ChatState:
    """A chat with no doc: fresh, or still paused if a hold record exists."""
    if not hold:
        return ChatState(wa_id=wa_id)
    return ChatState(wa_id=wa_id, mode=hold.get("mode", "paused"),
                     mode_reason=hold.get("mode_reason", ""),
                     mode_since=float(hold.get("mode_since") or 0),
                     last_human_at=float(hold.get("last_human_at") or 0),
                     code=hold.get("code", ""), held=True)


def format_code(n: int) -> str:
    return f"{n:03d}"


def parse_code(text: str) -> str:
    """"004", "#4", "chat 4" -> "004"; "" if there's no number."""
    import re
    m = re.search(r"\d+", text or "")
    return format_code(int(m.group())) if m else ""


def note_outcome(state: ChatState, intent: str, outcome: str, at: float) -> None:
    """What the agent did with a message, for the morning summary. outcome:
    answered | link sent | booked | moved | handed over | left | drafted | failed."""
    state.outcomes.append({"at": at, "intent": intent, "outcome": outcome})
    del state.outcomes[:-OUTCOMES_KEEP]


class MemoryStore:
    def __init__(self):
        self._chats: dict[str, dict] = {}
        self._updated: dict[str, float] = {}
        self._kill = False
        self._rollout: dict = {}
        self._history_imported = False
        self._staff_windows: dict[str, float] = {}
        self._go_live = 0.0
        self._next_code = 1
        self._code_lock = threading.Lock()

    def load(self, wa_id: str) -> ChatState:
        d = self._chats.get(wa_id)
        if d:
            return ChatState.from_dict(d)
        return from_hold(wa_id, getattr(self, "_holds", {}).get(wa_id))

    def save(self, state: ChatState) -> None:
        holds = self.__dict__.setdefault("_holds", {})
        if state.mode == "paused":
            holds[state.wa_id], state.held = hold_doc(state), True
        elif state.held:
            holds.pop(state.wa_id, None)
            state.held = False
        self._chats[state.wa_id] = state.to_dict()
        self._updated[state.wa_id] = time.time()

    def expire_chat(self, wa_id: str) -> None:
        """Tests: the transcript TTL ran out (the hold, if any, stays)."""
        self._chats.pop(wa_id, None)

    def delete_chat(self, wa_id: str) -> None:
        self._chats.pop(wa_id, None)
        self._updated.pop(wa_id, None)
        self.__dict__.setdefault("_holds", {}).pop(wa_id, None)

    def recent_chats(self, since: float) -> list[ChatState]:
        return [ChatState.from_dict(d) for w, d in self._chats.items()
                if self._updated.get(w, 0) >= since]

    def get_rollout(self) -> dict:
        return dict(self._rollout)

    def save_rollout(self, rollout: dict) -> None:
        self._rollout = dict(rollout)

    def get_history_imported(self) -> bool:
        return self._history_imported

    def set_history_imported(self, on: bool, source: str = "") -> None:
        self._history_imported = on

    def get_staff_windows(self) -> dict[str, float]:
        return dict(self._staff_windows)

    def get_go_live(self) -> float:
        return self._go_live

    def set_go_live(self, at: float, source: str = "") -> None:
        self._go_live = float(at or 0)

    def next_code(self) -> str:
        with self._code_lock:
            n, self._next_code = self._next_code, self._next_code + 1
        return format_code(n)

    def find_by_code(self, code: str) -> str:
        found = next((w for w, d in self._chats.items() if d.get("code") == code), "")
        return found or next((w for w, h in getattr(self, "_holds", {}).items()
                              if h.get("code") == code), "")

    def paused_chats(self, limit: int = 50) -> list[ChatState]:
        return [ChatState.from_dict(d) for d in self._chats.values()
                if d.get("mode") == "paused"][:limit]

    def note_staff_inbound(self, wa_id: str, ts: float) -> None:
        self._staff_windows[wa_id] = max(ts, self._staff_windows.get(wa_id, 0.0))

    def note_ping(self, msg_id: str, wa_id: str) -> None:
        if msg_id and wa_id:
            self.__dict__.setdefault("_pings", {})[msg_id] = (wa_id, time.time())

    def ping_chat(self, msg_id: str) -> str:
        wa_id, at = getattr(self, "_pings", {}).get(msg_id, ("", 0.0))
        return wa_id if time.time() - at < PING_DAYS * 86400 else ""

    def referral_seen(self, key: str) -> float:
        return getattr(self, "_referrals", {}).get(key, 0.0)

    def note_referral(self, key: str) -> None:
        self.__dict__.setdefault("_referrals", {})[key] = time.time()

    def hold_referral(self, number: str, text: str) -> None:
        self.__dict__.setdefault("_referral_held", {}).setdefault(number, []).append(text)

    def pop_held_referrals(self, number: str) -> list[str]:
        return self.__dict__.setdefault("_referral_held", {}).pop(number, [])

    def staff_welcomed(self, wa_id: str) -> bool:
        return wa_id in getattr(self, "_welcomed", set())

    def mark_staff_welcomed(self, wa_id: str) -> None:
        if not hasattr(self, "_welcomed"):
            self._welcomed = set()
        self._welcomed.add(wa_id)

    def get_kill(self) -> bool:
        return self._kill

    def get_late_changes(self, key: str) -> list[dict]:
        return list(getattr(self, "_late", {}).get(key, []))

    def add_late_change(self, key: str, entry: dict) -> None:
        self.__dict__.setdefault("_late", {}).setdefault(key, []).append(entry)

    def clear_late_changes(self, key: str) -> None:
        self.__dict__.setdefault("_late", {}).pop(key, None)

    def get_autonomy(self) -> dict:
        import copy
        return copy.deepcopy(getattr(self, "_autonomy", {}))

    def save_autonomy(self, autonomy: dict) -> None:
        self._autonomy = autonomy

    def set_kill(self, on: bool) -> None:
        self._kill = on


class FirestoreStore:
    def __init__(self, collection: str = config.FIRESTORE_COLLECTION):
        from google.cloud import firestore  # imported lazily: tests don't need it
        self._db = firestore.Client(project=config.PROJECT)
        self._chats = self._db.collection(collection)
        self._flags = self._db.collection(f"{collection}_flags")
        self._holds = self._db.collection(f"{collection}_holds")
        self._pings = self._db.collection(f"{collection}_pings")
        self._referrals = self._db.collection(f"{collection}_referrals")
        self._kill_cache: tuple[float, bool] = (0.0, False)
        self._rollout_cache: tuple[float, dict] = (-1e9, {})
        self._history_cache: tuple[float, bool] = (-1e9, False)
        self._golive_cache: tuple[float, float] = (-1e9, 0.0)
        self._code_lock = threading.Lock()

    def load(self, wa_id: str) -> ChatState:
        snap = self._chats.document(wa_id).get()
        if snap.exists:
            return ChatState.from_dict(snap.to_dict())
        hold = self._holds.document(wa_id).get()  # paused, transcript expired
        return from_hold(wa_id, hold.to_dict() if hold.exists else None)

    def save(self, state: ChatState) -> None:
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        if state.mode == "paused":
            self._holds.document(state.wa_id).set(
                {**hold_doc(state), "expire_at": now + timedelta(days=HOLD_DAYS)})
            state.held = True
        elif state.held:  # resumed: the pause record goes
            self._holds.document(state.wa_id).delete()
            state.held = False
        doc = state.to_dict()
        doc["expire_at"] = now + timedelta(days=RETENTION_DAYS)
        doc["updated_at"] = time.time()  # recent_chats (morning summary, staff status)
        self._chats.document(state.wa_id).set(doc)

    def delete_chat(self, wa_id: str) -> None:
        self._chats.document(wa_id).delete()
        self._holds.document(wa_id).delete()

    def recent_chats(self, since: float) -> list[ChatState]:
        """Chat docs saved since `since` (epoch s). One single-field range
        query on updated_at; Firestore indexes single fields automatically."""
        try:
            from google.cloud.firestore_v1.base_query import FieldFilter
            q = self._chats.where(filter=FieldFilter("updated_at", ">=", since))
        except ImportError:  # older client
            q = self._chats.where("updated_at", ">=", since)
        return [ChatState.from_dict(snap.to_dict() or {}) for snap in q.stream()]

    def _flag(self, name: str) -> dict:
        snap = self._flags.document(name).get()
        return (snap.to_dict() or {}) if snap.exists else {}

    def get_rollout(self) -> dict:
        at, val = self._rollout_cache
        if time.monotonic() - at < FLAG_CACHE_S:
            return dict(val)
        val = {k: v for k, v in self._flag("rollout").items() if k != "at"}
        self._rollout_cache = (time.monotonic(), val)
        return dict(val)

    def save_rollout(self, rollout: dict) -> None:
        self._flags.document("rollout").set({**rollout, "at": time.time()})
        self._rollout_cache = (time.monotonic(), dict(rollout))

    def get_history_imported(self) -> bool:
        at, val = self._history_cache
        if time.monotonic() - at < FLAG_CACHE_S:
            return val
        val = bool(self._flag("history_imported").get("on"))
        self._history_cache = (time.monotonic(), val)
        return val

    def set_history_imported(self, on: bool, source: str = "") -> None:
        self._flags.document("history_imported").set(
            {"on": on, "at": time.time(), "source": source})
        self._history_cache = (time.monotonic(), on)

    def get_staff_windows(self) -> dict[str, float]:
        return dict(self._flag("staff").get("windows") or {})

    def get_go_live(self) -> float:
        at, val = self._golive_cache
        if time.monotonic() - at < FLAG_CACHE_S:
            return val
        val = float(self._flag("golive").get("at") or 0)
        self._golive_cache = (time.monotonic(), val)
        return val

    def set_go_live(self, at: float, source: str = "") -> None:
        self._flags.document("golive").set({"at": float(at or 0), "source": source,
                                            "set_at": time.time()})
        self._golive_cache = (time.monotonic(), float(at or 0))

    def next_code(self) -> str:
        """One instance (--max-instances=1), so an in-process lock around the
        read-increment-write is enough."""
        with self._code_lock:
            n = int(self._flag("codes").get("next") or 1)
            self._flags.document("codes").set({"next": n + 1})
        return format_code(n)

    def find_by_code(self, code: str) -> str:
        try:
            from google.cloud.firestore_v1.base_query import FieldFilter
            q = self._chats.where(filter=FieldFilter("code", "==", code))
        except ImportError:
            q = self._chats.where("code", "==", code)
        found = next((snap.id for snap in q.limit(1).stream()), "")
        if found:
            return found
        try:
            from google.cloud.firestore_v1.base_query import FieldFilter
            h = self._holds.where(filter=FieldFilter("code", "==", code))
        except ImportError:
            h = self._holds.where("code", "==", code)
        return next((snap.id for snap in h.limit(1).stream()), "")

    def paused_chats(self, limit: int = 50) -> list[ChatState]:
        try:
            from google.cloud.firestore_v1.base_query import FieldFilter
            q = self._chats.where(filter=FieldFilter("mode", "==", "paused"))
        except ImportError:
            q = self._chats.where("mode", "==", "paused")
        return [ChatState.from_dict(snap.to_dict() or {}) for snap in q.limit(limit).stream()]

    def note_staff_inbound(self, wa_id: str, ts: float) -> None:
        self._flags.document("staff").set({"windows": {wa_id: ts}}, merge=True)

    def note_ping(self, msg_id: str, wa_id: str) -> None:
        from datetime import datetime, timedelta, timezone
        if msg_id and wa_id:
            self._pings.document(msg_id).set({
                "wa_id": wa_id, "at": time.time(),
                "expire_at": datetime.now(timezone.utc) + timedelta(days=PING_DAYS)})

    def ping_chat(self, msg_id: str) -> str:
        """The chat a ping was about; "" if unknown or older than PING_DAYS
        (the TTL deletes it within a day or so of expire_at)."""
        if not msg_id:
            return ""
        snap = self._pings.document(msg_id).get()
        d = (snap.to_dict() or {}) if snap.exists else {}
        return d.get("wa_id", "") if time.time() - float(d.get("at") or 0) < PING_DAYS * 86400 else ""

    def _referral_expiry(self):
        from datetime import datetime, timedelta, timezone
        return datetime.now(timezone.utc) + timedelta(days=REFERRAL_DAYS)

    def referral_seen(self, key: str) -> float:
        """When this patient (a hash) was last forwarded; 0 if never or expired."""
        snap = self._referrals.document(key).get()
        at = float(((snap.to_dict() or {}) if snap.exists else {}).get("at") or 0)
        return at if time.time() - at < REFERRAL_DAYS * 86400 else 0.0

    def note_referral(self, key: str) -> None:
        self._referrals.document(key).set({"at": time.time(),
                                           "expire_at": self._referral_expiry()})

    def hold_referral(self, number: str, text: str) -> None:
        from google.cloud import firestore
        self._referrals.document(f"held_{number}").set(
            {"texts": firestore.ArrayUnion([text]), "expire_at": self._referral_expiry()},
            merge=True)

    def pop_held_referrals(self, number: str) -> list[str]:
        ref = self._referrals.document(f"held_{number}")
        snap = ref.get()
        if not snap.exists:
            return []
        ref.delete()
        return list((snap.to_dict() or {}).get("texts") or [])

    def staff_welcomed(self, wa_id: str) -> bool:
        return wa_id in (self._flag("staff").get("welcomed") or {})

    def mark_staff_welcomed(self, wa_id: str) -> None:
        self._flags.document("staff").set({"welcomed": {wa_id: time.time()}}, merge=True)

    def get_kill(self) -> bool:
        # Read at most every 5s: the switch must bite fast, not cost a read per message.
        at, val = self._kill_cache
        if time.monotonic() - at < 5:
            return val
        snap = self._flags.document("kill_switch").get()
        val = bool(snap.exists and (snap.to_dict() or {}).get("on"))
        self._kill_cache = (time.monotonic(), val)
        return val

    def set_kill(self, on: bool) -> None:
        self._flags.document("kill_switch").set({"on": on, "at": time.time()})
        self._kill_cache = (time.monotonic(), on)

    # Late changes (cancel/reschedule inside 24h) per chat, kept beyond the
    # transcript TTL so the first-time fee waiver can be checked. Keyed by the
    # salted chat hash; holds dates and hours of notice only, no text.
    def get_late_changes(self, key: str) -> list[dict]:
        snap = self._db.collection("wa_agent_late_changes").document(key).get()
        return (snap.to_dict() or {}).get("changes", []) if snap.exists else []

    def add_late_change(self, key: str, entry: dict) -> None:
        from google.cloud import firestore
        self._db.collection("wa_agent_late_changes").document(key).set(
            {"changes": firestore.ArrayUnion([entry])}, merge=True)

    def clear_late_changes(self, key: str) -> None:
        self._db.collection("wa_agent_late_changes").document(key).delete()

    def get_autonomy(self) -> dict:
        """Per-intent auto-send record for automatic demotion (learning.py).
        One small doc; read per message, written on auto-sends and rescues."""
        snap = self._flags.document("autonomy").get()
        return (snap.to_dict() or {}).get("intents", {}) if snap.exists else {}

    def save_autonomy(self, autonomy: dict) -> None:
        self._flags.document("autonomy").set({"intents": autonomy, "at": time.time()})


def make_store():
    return FirestoreStore() if config.STATE_BACKEND == "firestore" else MemoryStore()


class ChatLocks:
    """One lock per chat so two webhooks for the same customer never interleave."""

    def __init__(self):
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = defaultdict(threading.Lock)

    def __call__(self, wa_id: str) -> threading.Lock:
        with self._guard:
            return self._locks[wa_id]
