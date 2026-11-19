"""
Append-only event log -> marts.wa_agent_events (see sql/marts/62_wa_agent_events.sql).

What Phase 0 measures lives here: response time per step, token use and cost,
what the policy decided, and every mode change. **No message text and no phone
numbers**: chats are keyed by a salted hash of the WhatsApp id, so the table
can be analysed freely while transcripts stay in Firestore under a TTL.

Writes are fire-and-forget on a background thread, the same pattern as the
booking funnel: logging must never slow or break a reply.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid

from . import config

log = logging.getLogger("wa_agent.events")

# The salt is a secret: with the public default anyone could hash every
# Singapore number and reverse a chat_key. The default is only for memory /
# local runs; a deployed (Firestore) run without WA_AGENT_HASH_SALT records
# events with chat_key None (see salt_ok) and logs an error at startup.
DEFAULT_SALT = "goji-wa-agent"
_SALT = os.environ.get("WA_AGENT_HASH_SALT", "") or DEFAULT_SALT
_bq = None
_bq_lock = threading.Lock()


def chat_key(wa_id: str) -> str:
    return hashlib.sha256(f"{_SALT}:{wa_id}".encode()).hexdigest()[:16]


def salt_ok() -> bool:
    """False on a deployed run still using the public default salt."""
    return _SALT != DEFAULT_SALT or config.STATE_BACKEND != "firestore"


def safe_chat_key(wa_id: str) -> str | None:
    """chat_key for anything that leaves Firestore (BigQuery rows, booking
    link refs, feedback links); None when the salt is the public default on
    a deployed run."""
    return chat_key(wa_id) if wa_id and salt_ok() else None


def check_salt() -> bool:
    """Called at startup. Logs loudly when a deployed run has no salt."""
    if not salt_ok():
        log.error("WA_AGENT_HASH_SALT is not set on a deployed (Firestore) run: events are "
                  "recorded WITHOUT chat_key until it is. Set it as a secret and redeploy.")
        return False
    return True


def _client():
    global _bq
    with _bq_lock:
        if _bq is None:
            from google.cloud import bigquery
            _bq = bigquery.Client(project=config.PROJECT)
        return _bq


def record(event: str, wa_id: str, *, key: str | None = None, **fields) -> dict:
    """event: inbound | echo | proposal | sent | drafted | escalated | silent |
    mode | status | send_failed | superseded | autonomy | feedback.
    `key` passes a chat_key directly (feedback links carry the hash, not the
    number). Returns the row (tests read it)."""
    row = {
        "event_id": str(uuid.uuid4()),
        "event": event,
        "chat_key": (key or safe_chat_key(wa_id)) if salt_ok() else None,
        "at": time.time(),
        **{k: v for k, v in fields.items() if k != "steps"},
    }
    if "steps" in fields:
        row["steps_json"] = json.dumps(fields["steps"])
    log.info("event %s", json.dumps(row, default=str))
    if config.LOG_EVENTS:
        threading.Thread(target=_insert, args=(row,), daemon=True).start()
    return row


def _insert(row: dict) -> None:
    try:
        bq_row = dict(row)
        bq_row["at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(row["at"])) + "Z"
        errors = _client().insert_rows_json(config.EVENTS_TABLE, [bq_row])
        if errors:
            log.warning("event insert errors: %s", errors)
    except Exception as e:
        log.warning("event insert failed: %s", e)
