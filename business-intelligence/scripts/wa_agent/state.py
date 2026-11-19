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
  staff             {windows: {wa_id: ts}}         staff numbers' last inbound (24h window)
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict

from . import config
from .policy import ChatState

RETENTION_DAYS = 30
HISTORY_KEEP = 50
SEEN_KEEP = 200
OUTCOMES_KEEP = 20
FLAG_CACHE_S = 5  # global flags bite within 5s without a read per message


def append_history(state: ChatState, role: str, text: str, ts: float, msg_id: str = "") -> None:
    """role: customer | agent | staff."""
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

    def load(self, wa_id: str) -> ChatState:
        d = self._chats.get(wa_id)
        return ChatState.from_dict(d) if d else ChatState(wa_id=wa_id)

    def save(self, state: ChatState) -> None:
        self._chats[state.wa_id] = state.to_dict()
        self._updated[state.wa_id] = time.time()

    def delete_chat(self, wa_id: str) -> None:
        self._chats.pop(wa_id, None)
        self._updated.pop(wa_id, None)

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

    def note_staff_inbound(self, wa_id: str, ts: float) -> None:
        self._staff_windows[wa_id] = max(ts, self._staff_windows.get(wa_id, 0.0))

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
        self._kill_cache: tuple[float, bool] = (0.0, False)
        self._rollout_cache: tuple[float, dict] = (-1e9, {})
        self._history_cache: tuple[float, bool] = (-1e9, False)

    def load(self, wa_id: str) -> ChatState:
        snap = self._chats.document(wa_id).get()
        return ChatState.from_dict(snap.to_dict()) if snap.exists else ChatState(wa_id=wa_id)

    def save(self, state: ChatState) -> None:
        from datetime import datetime, timedelta, timezone
        doc = state.to_dict()
        doc["expire_at"] = datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS)
        doc["updated_at"] = time.time()  # recent_chats (morning summary, staff status)
        self._chats.document(state.wa_id).set(doc)

    def delete_chat(self, wa_id: str) -> None:
        self._chats.document(wa_id).delete()

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

    def note_staff_inbound(self, wa_id: str, ts: float) -> None:
        self._flags.document("staff").set({"windows": {wa_id: ts}}, merge=True)

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
