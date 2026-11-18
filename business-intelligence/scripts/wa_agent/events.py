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

_SALT = os.environ.get("WA_AGENT_HASH_SALT", "goji-wa-agent")
_bq = None
_bq_lock = threading.Lock()


def chat_key(wa_id: str) -> str:
    return hashlib.sha256(f"{_SALT}:{wa_id}".encode()).hexdigest()[:16]


def _client():
    global _bq
    with _bq_lock:
        if _bq is None:
            from google.cloud import bigquery
            _bq = bigquery.Client(project=config.PROJECT)
        return _bq


def record(event: str, wa_id: str, **fields) -> dict:
    """event: inbound | echo | proposal | sent | drafted | escalated | silent |
    mode | status | send_failed | superseded. Returns the row (tests read it)."""
    row = {
        "event_id": str(uuid.uuid4()),
        "event": event,
        "chat_key": chat_key(wa_id) if wa_id else None,
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
