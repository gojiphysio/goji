"""The registration-form link every booking message carries.

https://booking.gojiphysio.com/form/<appointment id>.<signature>

One stable link per appointment, in the confirmation email, the 48-hour
reminder email and both WhatsApp templates (Meta's URL buttons take one
variable at the end of a fixed URL, so the Plato form links themselves can't
go in a template). goji-booking's /form/<token> route works out the right
Plato form when the patient taps it (confirmations.form_destination), so the
link never goes stale and a patient who has already registered gets a "you're
all set" page instead of a form.

The signature (HMAC with the internal token) stops anyone walking appointment
ids: a profile update form shows the patient's details. The reminders job
signs with the same secret; reminders/registration.py keeps a copy of these
two functions (separate deploys) and a test checks they agree.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re

BASE = os.environ.get("FORM_LINK_BASE", "https://booking.gojiphysio.com/form/")
_TOKEN_RE = re.compile(r"^([0-9a-f]{16,64})\.([0-9a-f]{20})$")


def token(appointment_id: str, secret: str) -> str:
    """'<appointment id>.<20 hex signature>', or '' without a secret."""
    if not (secret and appointment_id):
        return ""
    key = hmac.new(secret.encode(), b"form-link", hashlib.sha256).digest()
    sig = hmac.new(key, appointment_id.encode(), hashlib.sha256).hexdigest()[:20]
    return f"{appointment_id}.{sig}"


def url(appointment_id: str, secret: str) -> str:
    t = token(appointment_id, secret)
    return BASE + t if t else ""


def verify(tok: str, secret: str) -> str | None:
    """The appointment id a valid token names, else None."""
    m = _TOKEN_RE.match(tok or "")
    if not (m and secret):
        return None
    expected = token(m.group(1), secret)
    return m.group(1) if hmac.compare_digest(expected, tok) else None
