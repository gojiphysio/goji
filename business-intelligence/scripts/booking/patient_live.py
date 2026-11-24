"""Fresh patient contacts for the WhatsApp assistant's lookup.

The assistant finds who a chat is by matching its number against
marts.dim_patient_contact, which plato-patients-ingest rebuilds once a day. A
patient created since then was a stranger to it: on 24 Nov 2026 the assistant
booked a new patient at 10:03 and told the same number "no patient record" at
16:30. So goji-booking appends a row to marts.patient_contact_live whenever a
patient is created or changed, and the assistant reads both tables.

Two writers, because Plato only sends webhooks for what staff do in Plato,
never for API calls:
  - Plato's patient:upsert / patient:merge webhook (/plato/webhook/<token>):
    patients the front desk registers or edits.
  - /internal/book when it creates a patient: the assistant's own bookings.

Rows are name + phone only, the same scoped PII exception as
dim_patient_contact. The table's partitions expire after 7 days; by then the
nightly table has the patient.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone

log = logging.getLogger("goji-booking")

# At most this many patients fetched per webhook delivery. A staff action is
# one patient; a forged or runaway batch must not spend the clinic's Plato
# budget (20 req/min shared with the booking form).
MAX_PATIENTS_PER_DELIVERY = 20

# Same probe order as ingestion/plato_patients/main.py (extract_phone), so a
# live row and the nightly row hold the same number. Keep the two in step.
_PHONE_KEYS = (
    "mobile", "handphone", "hp", "phone", "tel", "telephone",
    "contact_number", "contactnumber", "contact",
)


def webhook_token(internal_token: str) -> str:
    """The secret path segment of the webhook URL given to Plato, derived from
    the internal token so there's no second secret to store. Rotating the
    internal token changes the URL: register the webhook again."""
    if not internal_token:
        return ""
    return hmac.new(internal_token.encode(), b"plato-webhook", hashlib.sha256).hexdigest()[:32]


def extract_phone(patient: dict) -> str | None:
    for k in _PHONE_KEYS:
        v = patient.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            for kk in ("number", "value", "mobile", "phone"):
                vv = v.get(kk)
                if isinstance(vv, str) and vv.strip():
                    return vv.strip()
    return None


def full_name(patient: dict) -> str | None:
    name = patient.get("name")
    if isinstance(name, dict):
        name = f"{name.get('first') or ''} {name.get('last') or ''}"
    if not isinstance(name, str):
        return None
    return " ".join(name.split()) or None


def contact_row(patient_id: str, name: str | None, phone: str | None, source: str,
                now: datetime | None = None) -> dict | None:
    """A patient_contact_live row, or None when there's no number to match on."""
    if not patient_id or not phone:
        return None
    return {"patient_id": patient_id, "full_name": name, "phone": phone, "source": source,
            "received_at": (now or datetime.now(timezone.utc)).isoformat()}


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


def record(bq, table: str, rows: list[dict]) -> int:
    """Streaming insert (rows are queryable at once). Returns rows written;
    never raises: a lost row only means waiting for the nightly job."""
    rows = [r for r in rows if r]
    if not rows:
        return 0
    try:
        errors = bq.insert_rows_json(table, rows)
    except Exception as e:
        log.warning("patient_contact_live insert failed: %s", e)
        return 0
    if errors:
        log.warning("patient_contact_live insert returned errors: %s", errors)
        return 0
    return len(rows)


def refresh(plato, bq, table: str, ids: list[str]) -> int:
    """Read each patient from Plato and append its contact row. Background
    work: uses the non-reserved part of the Plato budget."""
    rows = []
    for pid in ids:
        try:
            p = plato.get(f"/patient/{pid}", bulk=True, max_wait_s=60) or {}
        except Exception as e:
            log.warning("plato webhook: patient read failed: %s", e)
            continue
        if isinstance(p, dict):
            rows.append(contact_row(pid, full_name(p), extract_phone(p), "plato_webhook"))
    return record(bq, table, rows)
