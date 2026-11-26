"""/internal/book (the WhatsApp assistant's booking route) and the
booking-confirmed callback to the assistant. No network, Plato writes, mail or
BigQuery: Plato is a stub, side effects are recorded."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from booking import app as app_mod
from booking import mailer
from booking.booking import BookingError, create_booking
from booking.test_booking import BASE, NOW, StubPlato

TOKEN = "s3cret-token"
WA_DRAFT = {"service": "physiotherapy", "date": "2026-07-15", "time": "10:00",
            "format": "clinic", "name": "Jane Tan", "phone": "+65 9123 4567",
            "source": "whatsapp", "dry_run": False}
RESULT = {"ok": True, "reference": "GOJI-ABC123", "clinician_name": "Kristy Lim",
          "service": "Physiotherapy", "date": "2026-07-15", "time": "10:00",
          "dry_run": False, "source": "whatsapp"}


class NoWritePlato(StubPlato):
    """Reads like Plato; any write fails the test."""

    def create_appointment(self, payload):
        pytest.fail(f"dry run attempted a Plato write: {payload}")

    def delete_appointment(self, _id):
        pytest.fail("dry run attempted a Plato delete")


@pytest.fixture
def client(monkeypatch):
    calls = {"booked": [], "tracked": [], "admin": [], "customer": [], "posted": []}
    monkeypatch.setattr(app_mod, "_hits", {})
    monkeypatch.setattr(app_mod, "TURNSTILE_SECRET", "")
    monkeypatch.setattr(app_mod, "INTERNAL_TOKEN", TOKEN)
    monkeypatch.setattr(app_mod, "WA_AGENT_URL", "")
    monkeypatch.setattr(app_mod, "_track_async",
                        lambda stage, sid, *a, **kw: calls["tracked"].append(
                            (stage, kw.get("detail"), sid)))
    monkeypatch.setattr(app_mod, "plato", lambda: None)
    monkeypatch.setattr(app_mod.mailer, "send_admin_booking_email",
                        lambda r, d: calls["admin"].append((r, d)))
    monkeypatch.setattr(app_mod.mailer, "send_customer_booking_email",
                        lambda r, d: calls["customer"].append((r, d)))
    monkeypatch.setattr(app_mod, "_run_async", lambda fn: fn())  # callback inline

    def post(url, json=None, headers=None, timeout=None):
        calls["posted"].append({"url": url, "json": json, "headers": headers,
                                "timeout": timeout})

        class R:
            status_code = 200
        return R()
    monkeypatch.setattr(app_mod.requests, "post", post)

    def create(_p, draft, **kw):
        calls["booked"].append((draft, kw))
        return {**RESULT, "dry_run": kw.get("dry_run", False),
                "reference": "DRYRUN-AAAAAA" if kw.get("dry_run") else "GOJI-ABC123",
                "source": kw.get("source", "web")}
    monkeypatch.setattr(app_mod, "create_booking", create)
    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        c.calls = calls
        yield c


def _ibook(c, token=TOKEN, **over):
    headers = {"X-Internal-Token": token} if token is not None else {}
    return c.post("/internal/book", json={**WA_DRAFT, **over}, headers=headers)


def _wa_on(monkeypatch, url="https://wa.example.run.app/"):
    monkeypatch.setattr(app_mod, "WA_AGENT_URL", url)


# ---- auth -------------------------------------------------------------------

def test_route_is_absent_without_a_configured_token(client, monkeypatch):
    monkeypatch.setattr(app_mod, "INTERNAL_TOKEN", "")
    assert _ibook(client).status_code == 404
    assert _ibook(client, token="").status_code == 404
    assert client.calls["booked"] == []


@pytest.mark.parametrize("token", ["wrong", "", None, TOKEN + "x"])
def test_wrong_or_missing_token_is_forbidden(client, token):
    r = _ibook(client, token=token)
    assert r.status_code == 403 and r.get_json()["ok"] is False
    assert client.calls["booked"] == []


def test_right_token_books_without_bot_checks(client, monkeypatch):
    """No honeypot / fill time / Turnstile here, even with Turnstile switched on
    and the browser-only fields looking like a bot."""
    monkeypatch.setattr(app_mod, "TURNSTILE_SECRET", "secret")
    r = _ibook(client, company_url="x", elapsed_ms=10)
    assert r.status_code == 200
    draft, kw = client.calls["booked"][0]
    assert kw == {"email_required": False, "dry_run": False, "source": "whatsapp",
                  "patient_id": "", "create_patient": False}


# ---- request validation -----------------------------------------------------

@pytest.mark.parametrize("value", ["true", "false", 1, 0, None])
def test_dry_run_must_be_a_json_boolean(client, value):
    r = _ibook(client, dry_run=value)
    assert r.status_code == 400 and r.get_json()["code"] == "invalid"
    assert client.calls["booked"] == []


def test_missing_dry_run_means_a_real_booking(client):
    draft = {k: v for k, v in WA_DRAFT.items() if k != "dry_run"}
    r = client.post("/internal/book", json=draft, headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 200 and r.get_json()["dry_run"] is False


def test_only_whatsapp_source_is_accepted(client):
    r = _ibook(client, source="web")
    assert r.status_code == 400 and r.get_json()["code"] == "invalid"


def test_booking_errors_map_like_api_book(client, monkeypatch):
    def fail(code):
        def _f(*_a, **_kw):
            raise BookingError("nope", code)
        return _f
    monkeypatch.setattr(app_mod, "create_booking", fail("slot_taken"))
    r = _ibook(client)
    assert r.status_code == 409
    assert r.get_json() == {"ok": False, "error": "nope", "code": "slot_taken"}
    monkeypatch.setattr(app_mod, "create_booking", fail("invalid"))
    assert _ibook(client).status_code == 400
    assert ("book_error", "whatsapp_invalid") in [t[:2] for t in client.calls["tracked"]]


# ---- response, emails, funnel ----------------------------------------------

def test_real_booking_response_shape(client):
    r = _ibook(client)
    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "reference": "GOJI-ABC123",
                            "clinician_name": "Kristy Lim", "service": "Physiotherapy",
                            "date": "2026-07-15", "time": "10:00", "dry_run": False}


def test_no_email_skips_customer_email_but_not_admin(client):
    assert _ibook(client).status_code == 200
    assert client.calls["customer"] == []
    assert len(client.calls["admin"]) == 1
    assert client.calls["admin"][0][0]["source"] == "whatsapp"


def test_email_given_gets_customer_email(client):
    assert _ibook(client, email="jane@example.com").status_code == 200
    assert len(client.calls["customer"]) == 1


def test_real_booking_is_tracked_as_whatsapp(client):
    _ibook(client)
    (stage, detail, sid), = client.calls["tracked"]
    assert (stage, detail) == ("confirmed", "whatsapp")
    assert sid.startswith("wa-") and "9123" not in sid  # hashed, no phone


def test_dry_run_sends_nothing_and_tracks_nothing(client):
    r = _ibook(client, dry_run=True)
    body = r.get_json()
    assert r.status_code == 200 and body["dry_run"] is True
    assert body["reference"].startswith("DRYRUN-")
    assert client.calls["booked"][0][1]["dry_run"] is True
    assert client.calls["admin"] == [] and client.calls["customer"] == []
    assert client.calls["tracked"] == []


def test_stages_used_are_valid():
    """_track_async silently drops unknown stages; ours must be in the set."""
    assert {"confirmed", "book_error"} <= app_mod.VALID_STAGES


# ---- rate limit -------------------------------------------------------------

def test_daily_contact_limit_applies(client):
    assert _ibook(client).status_code == 200
    assert _ibook(client).status_code == 200
    r = _ibook(client)
    assert r.status_code == 429 and r.get_json()["code"] == "rate_limited"
    assert len(client.calls["booked"]) == 2
    # A dry run is checked against the limit too (it predicts the real answer).
    assert _ibook(client, dry_run=True).status_code == 429


def test_dry_runs_do_not_count_toward_the_limit(client):
    for _ in range(5):
        assert _ibook(client, dry_run=True).status_code == 200
    assert _ibook(client).status_code == 200


def test_limit_is_shared_with_the_website(client):
    """Same phone, one booking from each channel: the third is refused."""
    web = {k: v for k, v in WA_DRAFT.items() if k not in ("source", "dry_run")}
    assert client.post("/api/book", json={**web, "email": "jane@example.com"},
                       headers={"X-Forwarded-For": "1.2.3.4"}).status_code == 200
    assert _ibook(client).status_code == 200
    assert _ibook(client).status_code == 429


# ---- booking-confirmed callback ---------------------------------------------

def test_callback_fires_for_a_whatsapp_booking(client, monkeypatch):
    _wa_on(monkeypatch)
    assert _ibook(client).status_code == 200
    (call,) = client.calls["posted"]
    assert call["url"] == "https://wa.example.run.app/internal/booking-confirmed"
    assert call["headers"] == {"X-Internal-Token": TOKEN}
    assert call["timeout"] == 5
    assert call["json"] == {"phone": "+65 9123 4567", "reference": "GOJI-ABC123",
                            "service": "Physiotherapy", "date": "2026-07-15",
                            "time": "10:00", "clinician_name": "Kristy Lim",
                            "source": "whatsapp", "first_name": "Jane"}


def test_callback_fires_for_a_website_booking(client, monkeypatch):
    _wa_on(monkeypatch)
    web = {k: v for k, v in WA_DRAFT.items() if k not in ("source", "dry_run")}
    r = client.post("/api/book", json={**web, "email": "jane@example.com"},
                    headers={"X-Forwarded-For": "1.2.3.4"})
    assert r.status_code == 200
    (call,) = client.calls["posted"]
    assert call["json"]["source"] == "web"
    assert call["json"]["phone"] == "+65 9123 4567"
    assert call["json"]["reference"] == "GOJI-ABC123"


def test_no_callback_for_a_dry_run(client, monkeypatch):
    _wa_on(monkeypatch)
    assert _ibook(client, dry_run=True).status_code == 200
    assert client.calls["posted"] == []


def test_no_callback_for_a_failed_booking(client, monkeypatch):
    _wa_on(monkeypatch)

    def fail(*_a, **_kw):
        raise BookingError("gone", "slot_taken")
    monkeypatch.setattr(app_mod, "create_booking", fail)
    assert _ibook(client).status_code == 409
    assert client.calls["posted"] == []


def test_no_callback_without_url(client):
    assert _ibook(client).status_code == 200
    assert client.calls["posted"] == []


def test_no_callback_without_token(client, monkeypatch):
    """The website path still books; it just has no secret to call with."""
    _wa_on(monkeypatch)
    monkeypatch.setattr(app_mod, "INTERNAL_TOKEN", "")
    web = {k: v for k, v in WA_DRAFT.items() if k not in ("source", "dry_run")}
    r = client.post("/api/book", json={**web, "email": "jane@example.com"},
                    headers={"X-Forwarded-For": "1.2.3.4"})
    assert r.status_code == 200
    assert client.calls["posted"] == []


def test_callback_failure_never_fails_the_booking(client, monkeypatch):
    _wa_on(monkeypatch)

    def boom(*_a, **_kw):
        raise ConnectionError("assistant down")
    monkeypatch.setattr(app_mod.requests, "post", boom)
    assert _ibook(client).status_code == 200


def test_callback_runs_off_the_request_thread(monkeypatch):
    """The real _run_async hands the POST to a daemon thread."""
    started = []

    class T:
        def __init__(self, target, daemon):
            started.append(daemon)
            self.target = target

        def start(self):
            started.append("started")
    monkeypatch.setattr(app_mod.threading, "Thread", T)
    app_mod._run_async(lambda: None)
    assert started == [True, "started"]


# ---- create_booking: email optional, connect, dry run -------------------------

def test_email_is_still_required_by_default():
    no_email = {k: v for k, v in BASE.items() if k != "email"}
    with pytest.raises(BookingError):
        create_booking(StubPlato(), {**no_email, "clinician_id": "cheryl-long"}, now=NOW)


def test_no_email_books_without_email_or_portal_invite():
    p = StubPlato()
    no_email = {k: v for k, v in BASE.items() if k != "email"}
    res = create_booking(p, {**no_email, "clinician_id": "cheryl-long"}, now=NOW,
                         email_required=False, source="whatsapp")
    assert res["ok"] and res["dry_run"] is False and res["source"] == "whatsapp"
    payload = p.created[0][0]
    assert "email" not in payload
    assert payload["connect"] is False
    assert payload["handphone"] == "+65 9123 4567"
    assert "Booked via WhatsApp assistant." in payload["description"]


def test_no_email_home_visit_has_no_portal_invite():
    p = StubPlato()
    no_email = {k: v for k, v in BASE.items() if k != "email"}
    create_booking(p, {**no_email, "format": "home", "address": "123B Lentor"},
                   now=NOW, email_required=False, source="whatsapp")
    visit = p.created[1][0]
    assert "email" not in visit and visit["connect"] is False


def test_a_given_email_is_still_validated_when_optional():
    for bad in ("not-an-email", "jane@gmail.con"):
        with pytest.raises(BookingError):
            create_booking(StubPlato(), {**BASE, "email": bad}, now=NOW,
                           email_required=False)


def test_whatsapp_booking_with_email_keeps_the_invite():
    p = StubPlato()
    create_booking(p, {**BASE, "clinician_id": "cheryl-long"}, now=NOW,
                   email_required=False, source="whatsapp")
    payload = p.created[0][0]
    assert payload["email"] == "jane@example.com" and payload["connect"] is True


def test_terms_agreed_in_a_whatsapp_chat_go_on_their_own_line():
    """26 Nov 2026: the team agreed a 40-min session billed to the patient's
    employer's insurer at $190. It goes in the Plato note apart from the
    patient's own note, so the front desk bills it right."""
    p = StubPlato()
    create_booking(p, {**BASE, "clinician_id": "cheryl-long", "notes": "postpartum",
                       "arranged": "Bill to FM (company insurance), $190 for 40 min"},
                   now=NOW, email_required=False, source="whatsapp")
    desc = p.created[0][0]["description"]
    assert "\nCondition: postpartum" in desc
    assert "\nAgreed with the clinic: Bill to FM (company insurance), $190 for 40 min" in desc


def test_the_website_cannot_set_agreed_terms():
    p = StubPlato()
    create_booking(p, {**BASE, "clinician_id": "cheryl-long", "arranged": "free session"},
                   now=NOW)
    assert "Agreed with the clinic" not in p.created[0][0]["description"]


def test_agreed_terms_refuse_tags():
    with pytest.raises(BookingError):
        create_booking(StubPlato(), {**BASE, "arranged": "<script>x</script>"}, now=NOW,
                       email_required=False, source="whatsapp")


def test_website_note_is_unchanged():
    p = StubPlato()
    create_booking(p, {**BASE, "clinician_id": "cheryl-long"}, now=NOW)
    assert "Booked via website." in p.created[0][0]["description"]


def test_dry_run_never_writes_and_picks_a_clinician():
    p = NoWritePlato()
    res = create_booking(p, BASE, now=NOW, dry_run=True)  # first available
    assert res["ok"] and res["dry_run"] is True
    assert res["reference"].startswith("DRYRUN-") and len(res["reference"]) == 13
    assert res["clinician_name"] and res["appointment_ids"] == []
    assert p.fresh_reads and all(p.fresh_reads)  # the live re-check still ran


def test_dry_run_refuses_a_taken_slot():
    p = NoWritePlato([{"color": "blue", "starttime": "2026-07-15 10:00:00",
                       "endtime": "2026-07-15 11:00:00"}])
    with pytest.raises(BookingError) as e:
        create_booking(p, {**BASE, "clinician_id": "cheryl-long"}, now=NOW,
                       dry_run=True)
    assert e.value.code == "slot_taken"


def test_dry_run_validates_like_a_real_booking():
    with pytest.raises(BookingError):
        create_booking(NoWritePlato(), {**BASE, "phone": "abc"}, now=NOW, dry_run=True)


def _next_weekday(min_ahead=3) -> date:
    d = datetime.now(app_mod.SGT).date() + timedelta(days=min_ahead)
    while d.weekday() != 2:  # a Wednesday, inside the 60-day window
        d += timedelta(days=1)
    return d


def test_dry_run_end_to_end_never_reaches_plato_writes(client, monkeypatch):
    """Through the route with the real create_booking: a write fails the test."""
    _wa_on(monkeypatch)
    p = NoWritePlato()
    monkeypatch.setattr(app_mod, "plato", lambda: p)
    monkeypatch.setattr(app_mod, "create_booking", create_booking)
    day = _next_weekday().isoformat()
    r = _ibook(client, date=day, dry_run=True, clinician_id="cheryl-long")
    body = r.get_json()
    assert r.status_code == 200, body
    assert body["dry_run"] is True and body["reference"].startswith("DRYRUN-")
    assert body["clinician_name"] == "Cheryl Long" and body["date"] == day
    assert client.calls["posted"] == [] and client.calls["admin"] == []


# ---- admin email ------------------------------------------------------------

def test_admin_email_marks_a_whatsapp_booking(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "SMTP_PASS", "x")
    monkeypatch.setattr(mailer, "_send", lambda msg, what, ref: sent.append(msg))
    result = {**RESULT, "clinician_requested": "First available", "home": False}
    mailer.send_admin_booking_email(result, {k: v for k, v in WA_DRAFT.items()})
    (msg,) = sent
    body = msg.get_content()
    assert msg["Subject"].startswith("New WhatsApp booking")
    assert "Booked via WhatsApp assistant" in body
    assert "(none given)" in body and "Plato sent no confirmation" in body


def test_admin_email_for_website_is_unchanged(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "SMTP_PASS", "x")
    monkeypatch.setattr(mailer, "_send", lambda msg, what, ref: sent.append(msg))
    result = {**RESULT, "source": "web", "clinician_requested": "First available"}
    mailer.send_admin_booking_email(result, {**WA_DRAFT, "email": "jane@example.com"})
    body = sent[0].get_content()
    assert sent[0]["Subject"].startswith("New website booking")
    assert "came in via the website" in body and "Plato's confirmation" in body


def test_whatsapp_booking_links_or_creates_the_patients_own_record(monkeypatch):
    """The texter may book for a spouse or child on the same number: the
    appointment goes on the patient's record, never the texter's by phone."""
    from booking import booking as bk
    posted, appts = [], []

    class P:
        def post(self, path, payload):
            posted.append((path, payload))
            return {"_id": "NEWPATIENT1"}

    monkeypatch.setattr(bk, "_create_appointments",
                        lambda *a, **k: (appts.append(k.get("patient_id")) or (["A1"], "VISIT000001")))
    assert bk._create_patient(P(), "Mei Tan", "+6582823628") == "NEWPATIENT1"
    assert posted == [("patient", {"name": "Mei Tan", "telephone": "+6582823628"})]


def test_create_patient_failure_is_a_booking_error():
    from booking import booking as bk

    class P:
        def post(self, path, payload):
            return {}
    try:
        bk._create_patient(P(), "Mei Tan", "+6582823628")
    except bk.BookingError as e:
        assert e.code == "plato_error"
    else:
        raise AssertionError("expected BookingError")


def test_a_new_patient_is_written_to_the_contact_table(client, monkeypatch):
    """Plato sends no webhook for API writes, so /internal/book writes the
    patient it created itself; an existing patient or a dry run adds nothing."""
    rows = []
    monkeypatch.setattr(app_mod.patient_contacts, "upsert",
                        lambda bq, table, row: rows.append((table, row)) or True)
    monkeypatch.setattr(app_mod, "bq", lambda: None)
    monkeypatch.setattr(app_mod, "create_booking", lambda _p, d, **kw: {
        **RESULT, "dry_run": kw["dry_run"], "patient_id": "" if kw["dry_run"] else "NEW1",
        "patient_created": kw["create_patient"] and not kw["dry_run"]})
    assert _ibook(client, create_patient=True).status_code == 200
    assert rows == [("goji-bi.marts.dim_patient_contact",
                     {"patient_id": "NEW1", "full_name": "Jane Tan",
                      "phone": "+65 9123 4567", "email": None})]
    _ibook(client, create_patient=False)
    _ibook(client, create_patient=True, dry_run=True)
    assert len(rows) == 1


def test_a_failed_contact_write_never_fails_the_booking(client, monkeypatch):
    def boom():
        raise RuntimeError("no bigquery")
    monkeypatch.setattr(app_mod, "bq", boom)
    monkeypatch.setattr(app_mod, "create_booking", lambda _p, d, **kw: {
        **RESULT, "patient_id": "NEW1", "patient_created": True})
    assert _ibook(client, create_patient=True).get_json()["ok"] is True
