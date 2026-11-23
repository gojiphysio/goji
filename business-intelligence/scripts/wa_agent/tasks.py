"""
Cloud Tasks, so the service can scale to zero (Charles, 19 Nov 2026: an
always-on instance for ~40 messages a day is wasteful).

The webhook puts each event on a queue and acks Meta at once; Cloud Tasks then
POSTs it back to /tasks/run, and the 30-40s of work (debounce, model, pre-send
hold) happens inside that request, so Cloud Run bills only while it works and
CPU is never throttled mid-turn. Cache warming rides the same queue: after a
turn, a warm task is scheduled WARM_EVERY_S later, and each warm schedules the
next while inside WARM_HOURS.

Tasks are plain HTTP tasks (no OIDC, so no actAs grant): the body is signed
with an HMAC keyed on the admin token, and /tasks/run checks it. Someone who
can read the queue sees a signature for that one body only; replaying it is
harmless (webhook de-dupe by message id).

REST through google-auth (already a dependency of the Google clients) rather
than the google-cloud-tasks package.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import threading
import time
from dataclasses import asdict

from . import config

log = logging.getLogger("wa_agent.tasks")
SIGNATURE_HEADER = "X-Task-Signature"
_session = None
_lock = threading.Lock()


def enabled() -> bool:
    return bool(config.TASKS_QUEUE and config.PUBLIC_URL)


def sign(body: bytes) -> str:
    return hmac.new((config.ADMIN_TOKEN or "").encode(), body, hashlib.sha256).hexdigest()


def valid(body: bytes, signature: str) -> bool:
    return bool(config.ADMIN_TOKEN and signature) and hmac.compare_digest(sign(body), signature)


def encode(kind: str, obj=None, **extra) -> bytes:
    """One task body: {"kind", "event": <dataclass fields>, ...extra}."""
    payload = {"kind": kind, **extra}
    if obj is not None:
        payload["event"] = asdict(obj)
    return json.dumps(payload, sort_keys=True).encode()


def _authed():
    global _session
    with _lock:
        if _session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession
            creds, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"])
            _session = AuthorizedSession(creds)
        return _session


def enqueue(body: bytes, *, delay_s: float = 0, name: str = "") -> bool:
    """Create the task. True if queued (or a task with that name already
    exists: named tasks de-duplicate the warm chain)."""
    task = {"httpRequest": {
        "httpMethod": "POST",
        "url": config.PUBLIC_URL.rstrip("/") + "/tasks/run",
        "headers": {"Content-Type": "application/json", SIGNATURE_HEADER: sign(body)},
        "body": base64.b64encode(body).decode(),
    }, "dispatchDeadline": "600s"}
    if delay_s > 0:
        at = time.gmtime(time.time() + delay_s)
        task["scheduleTime"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", at)
    if name:
        task["name"] = f"{config.TASKS_QUEUE}/tasks/{name}"
    r = _authed().post(f"https://cloudtasks.googleapis.com/v2/{config.TASKS_QUEUE}/tasks",
                       json={"task": task}, timeout=10)
    if r.status_code == 409:  # ALREADY_EXISTS: that warm is already scheduled
        return True
    if r.status_code >= 300:
        log.warning("enqueue failed: HTTP %s %s", r.status_code, r.text[:200])
        return False
    return True


def warm_name(now: float) -> str:
    """One warm task per WARM_EVERY_S slot, whoever schedules it."""
    return f"warm-{int((now + config.WARM_EVERY_S) // config.WARM_EVERY_S)}"
