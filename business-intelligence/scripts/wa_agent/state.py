"""
Per-chat state (mode, recent transcript, de-dupe ids) and the global kill flag.

Firestore in production (free tier covers clinic volume), memory in tests.
The service runs as ONE instance (--max-instances=1, like goji-booking), so a
per-chat in-process lock is enough to serialise webhooks for the same chat.

Transcripts are patient data: each chat doc carries `expire_at`, and the
Firestore TTL policy set up by deploy.sh deletes it RETENTION_DAYS after the
last message. Message text never goes to BigQuery (see events.py).
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


class MemoryStore:
    def __init__(self):
        self._chats: dict[str, dict] = {}
        self._kill = False

    def load(self, wa_id: str) -> ChatState:
        d = self._chats.get(wa_id)
        return ChatState.from_dict(d) if d else ChatState(wa_id=wa_id)

    def save(self, state: ChatState) -> None:
        self._chats[state.wa_id] = state.to_dict()

    def get_kill(self) -> bool:
        return self._kill

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

    def load(self, wa_id: str) -> ChatState:
        snap = self._chats.document(wa_id).get()
        return ChatState.from_dict(snap.to_dict()) if snap.exists else ChatState(wa_id=wa_id)

    def save(self, state: ChatState) -> None:
        from datetime import datetime, timedelta, timezone
        doc = state.to_dict()
        doc["expire_at"] = datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS)
        self._chats.document(state.wa_id).set(doc)

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
