"""Keep marts.dim_patient_contact current between nightly rebuilds.

The WhatsApp assistant recognises a chat by matching its number against
dim_patient_contact. plato-patients-ingest rebuilds that table each night, so
a patient created during the day was a stranger to the assistant until the
next run: on 24 Nov 2026 it booked a new patient at 10:03 and told the same
number "no patient record" at 16:30.

Patients are created or changed in two places, and each one updates the
table as it happens:
  - staff in Plato: Plato's patient:upsert / patient:merge webhook
    (/plato/webhook/<token>); we read the patient back from Plato.
  - goji-booking itself: /internal/book when it creates a patient. Plato
    sends no webhook for API writes, so this one is ours to write.
The nightly rebuild stays the repair (Plato doesn't store or replay webhook
events, and drops a webhook after 5 failed deliveries in a day) and reports
any patient these writers missed (plato_patients/main.py, contact drift).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import threading
import time
from collections import deque

from .plato import one_record

log = logging.getLogger("goji-booking")

# At most this many patients per webhook delivery: a staff action is one
# patient, and a runaway batch must not spend the clinic's Plato budget.
MAX_PATIENTS_PER_DELIVERY = 20
# Our own cap on webhook-driven Plato reads, below the limiter's bulk share, so
# a burst of staff edits can't starve the 5-minute availability snapshot (which
# pages Plato from the same share). A patient over the cap waits for the
# nightly rebuild.
READS_PER_MIN = int(os.environ.get("PLATO_WEBHOOK_READS_PER_MIN", "4"))
READ_MAX_WAIT_S = 5.0
# /internal/book waits on the write and the assistant gives up on a booking
# after 30s. Past this we stop waiting; the statement still finishes in
# BigQuery.
WRITE_WAIT_S = 5.0

# Same field probes as ingestion/plato_patients/main.py (full_name,
# extract_phone, extract_email), so an event row and the nightly row agree
# (test_patient_contacts.py checks). Change both.
_PHONE_KEYS = (
    "mobile", "handphone", "hp", "phone", "tel", "telephone",
    "contact_number", "contactnumber", "contact",
)
_EMAIL_KEYS = ("email", "email_address", "emailaddress", "e_mail", "mail")

_UPSERT_SQL = """
MERGE `{table}` t
USING (SELECT @patient_id AS patient_id, @full_name AS full_name,
              @phone AS phone, @email AS email) s
ON t.patient_id = s.patient_id
WHEN MATCHED THEN UPDATE SET full_name = s.full_name, phone = s.phone,
  email = s.email, _updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (patient_id, full_name, phone, email, _updated_at)
  VALUES (s.patient_id, s.full_name, s.phone, s.email, CURRENT_TIMESTAMP())
"""


def webhook_token(internal_token: str) -> str:
    """The secret path segment of the webhook URL given to Plato, derived from
    the internal token so there's no second secret to store. Rotating the
    internal token changes the URL: register the webhook again."""
    if not internal_token:
        return ""
    return hmac.new(internal_token.encode(), b"plato-webhook", hashlib.sha256).hexdigest()[:32]


def _probe(patient: dict, keys: tuple[str, ...], nested: tuple[str, ...]) -> str | None:
    for k in keys:
        v = patient.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            for kk in nested:
                vv = v.get(kk)
                if isinstance(vv, str) and vv.strip():
                    return vv.strip()
    return None


def _looks_like_email(raw: str) -> bool:
    v = raw.strip()
    if not v or v.count("@") != 1 or any(c.isspace() for c in v):
        return False
    local, _, domain = v.partition("@")
    return bool(local) and "." in domain and not domain.startswith(".") \
        and not domain.endswith(".")


def _email(patient: dict) -> str | None:
    for k in _EMAIL_KEYS:
        v = patient.get(k)
        if isinstance(v, str) and _looks_like_email(v):
            return v.strip()
        if isinstance(v, dict):
            for kk in ("address", "value", "email"):
                vv = v.get(kk)
                if isinstance(vv, str) and _looks_like_email(vv):
                    return vv.strip()
    return None


def from_plato(patient_id: str, patient: dict) -> dict:
    """A contact row from a Plato patient record, as the nightly job builds it."""
    name = patient.get("name")
    if isinstance(name, dict):
        name = f"{name.get('first') or ''} {name.get('last') or ''}"
    full_name = " ".join(name.split()) if isinstance(name, str) else ""
    return {"patient_id": patient_id, "full_name": full_name or None,
            "phone": _probe(patient, _PHONE_KEYS, ("number", "value", "mobile", "phone")),
            "email": _email(patient)}


def upsert(bq, table: str, row: dict) -> bool:
    """Write one patient's contact row. Never raises: a missed write only means
    waiting for the nightly rebuild (which reports it as drift)."""
    try:
        from google.cloud import bigquery
        params = [bigquery.ScalarQueryParameter(k, "STRING", row.get(k))
                  for k in ("patient_id", "full_name", "phone", "email")]
        bq.query(_UPSERT_SQL.format(table=table),
                 job_config=bigquery.QueryJobConfig(query_parameters=params)
                 ).result(timeout=WRITE_WAIT_S)
        return True
    except Exception as e:
        log.warning("patient contact not updated: %s", e)
        return False


def patient_ids(payload: object, db: str) -> tuple[list[str], list[str]]:
    """From a webhook delivery: the patient ids to refresh (for a merge, the
    record that survives) and any webhook:token tokens to activate. Events for
    another Plato database are ignored."""
    ids: list[str] = []
    tokens: list[str] = []
    events = payload.get("events") if isinstance(payload, dict) else None
    for e in events if isinstance(events, list) else []:
        if not isinstance(e, dict) or e.get("db") != db:
            continue
        kind = e.get("event")
        pid = e.get("object_id") if kind == "patient:upsert" else (
            e.get("to_id") if kind == "patient:merge" else None)
        if isinstance(pid, str) and pid.replace("-", "").isalnum() and len(pid) <= 64:
            if pid not in ids:
                ids.append(pid)
        elif kind == "webhook:token" and isinstance(e.get("token"), str):
            tokens.append(e["token"])
    return ids[:MAX_PATIENTS_PER_DELIVERY], tokens


_reads: deque[float] = deque()
_reads_lock = threading.Lock()


def _take_read(now: float | None = None) -> bool:
    """One webhook read from our per-minute allowance, or False if it's spent."""
    now = time.monotonic() if now is None else now
    with _reads_lock:
        while _reads and now - _reads[0] >= 60:
            _reads.popleft()
        if len(_reads) >= READS_PER_MIN:
            return False
        _reads.append(now)
        return True


def refresh(plato, bq, table: str, ids: list[str]) -> int:
    """Read each patient from Plato and write its contact row. The
    non-reserved part of the Plato budget, no retries (a retry into a 429
    keeps the whole clinic throttled), at most READS_PER_MIN."""
    written = skipped = 0
    for pid in ids:
        if not _take_read():
            skipped += 1
            continue
        try:
            p = plato.get(f"/patient/{pid}", bulk=True, max_wait_s=READ_MAX_WAIT_S,
                          _retries=0)
        except Exception as e:
            log.warning("plato webhook: patient read failed: %s", e)
            continue
        patient = one_record(p)
        if patient is None:
            log.warning("plato webhook: unexpected patient response (%s)", type(p).__name__)
            continue
        if upsert(bq, table, from_plato(pid, patient)):
            written += 1
    if skipped:
        log.info("plato webhook: %d patient(s) over the read cap, left to the nightly rebuild",
                 skipped)
    return written
