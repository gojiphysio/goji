"""confirmations.py: one confirmation email per appointment. No network, mail
or BigQuery: SMTP, Plato and BigQuery are fakes that record what they're asked."""
from __future__ import annotations

from datetime import datetime, timezone
from email import message_from_bytes
from email.policy import default as default_policy

import pytest

from booking import app as app_mod
from booking import confirmations as c

NOW = datetime(2026, 11, 26, 9, 0)  # clinic time
STAMP = datetime(2026, 11, 26, 1, 0, tzinfo=timezone.utc)

PLATO_APPT = {
    "_id": "5e8cd7cdcfb94ef586a66764e84b308d",
    "starttime": "2026-12-03 10:00:00", "endtime": "2026-12-03 11:00:00",
    "title": "Sarah Tan", "email": "sarah@example.com", "handphone": "+65 9123 4567",
    "patient_id": "", "color": "green", "code_Bottom": "hDWW",
    "description": "", "created_on": "2026-11-26 08:30:00",
}


class FakeBQ:
    """Answers the module's queries by what they ask for; records inserts."""

    def __init__(self, last=None, failures=0, contact=None, profile=("p0", True)):
        """profile: (patient_id, consent signed) for the registration lookup,
        or None for "no profile matches"."""
        self.last, self.failures, self.contact, self.profile = last, failures, contact, profile
        self.inserts: list[dict] = []
        self.queries: list[str] = []

    def query(self, sql, job_config=None):
        self.queries.append(sql)
        params = {p.name: p.value for p in (job_config.query_parameters if job_config else [])}
        if sql.lstrip().startswith("INSERT"):
            self.inserts.append(params)
            rows = []
        elif "AS signed" in sql:
            rows = ([{"patient_id": self.profile[0], "signed": self.profile[1]}]
                    if self.profile else [])
        elif "COUNT(*) AS n" in sql:
            rows = [{"n": self.failures}]
        elif "start_key, sequence" in sql:
            rows = [{"start_key": self.last[0], "sequence": self.last[1]}] if self.last else []
        elif "full_name, email" in sql:
            rows = [self.contact] if self.contact else []
        else:
            raise AssertionError(f"unexpected query: {sql[:80]}")

        class Job:
            def result(self, timeout=None):
                return rows
        return Job()


class FakePlato:
    def __init__(self, record=None, patient=None):
        self.record, self.patient = record, patient or {}
        self.gets: list[str] = []

    def get(self, path, **kw):
        self.gets.append(path)
        if path.endswith("/prereg"):
            return {"url": "https://clinic.platomedical.com/prereg/abc/def"}
        if path.endswith("/updatelink"):
            return {"url": "https://clinic.platomedical.com/secure/regupdate/abc/def"}
        if path.startswith("/patient/"):
            return [self.patient]
        return [self.record]  # Plato answers GET /appointment/{id} with a list


@pytest.fixture
def sent(monkeypatch):
    out: list = []
    monkeypatch.setattr(c, "SMTP_PASS", "app-password")
    monkeypatch.setattr(c, "_send", out.append)
    monkeypatch.setenv("CONFIRMATIONS_TEST_TO", "inbox@example.com")
    monkeypatch.setenv("CONFIRMATIONS_SINCE", "2026-11-26 08:00")
    monkeypatch.setattr(c, "INTERNAL_TOKEN", "tok")  # signs the form link
    return out


def live(monkeypatch):
    monkeypatch.setenv("CONFIRMATIONS_MODE", "live")


# --- links + parsing ------------------------------------------------------------

def test_confirm_url_matches_plato_own_email():
    # Copied from a real Plato confirmation email (30 Oct 2026).
    assert c.confirm_url("5e8cd7cdcfb94ef586a66764e84b308d", "gojihealth") == (
        "https://clinic.platomedical.com/appointment_confirm/Z29qaWhlYWx0aA==/"
        "5e8cd7cdcfb94ef586a66764e84b308d")


def test_from_plato_reads_a_staff_booking():
    a = c.from_plato(PLATO_APPT)
    assert (a.service, a.clinician, a.home, a.name) == (
        "Physiotherapy", "Kristy Ng", False, "Sarah Tan")
    assert a.start_key == "2026-12-03 10:00" and a.reference == "GOJI-4B308D"


@pytest.mark.parametrize("change", [
    {"email": "", "handphone": "", "patient_id": ""},  # travel leg / lunch / block
    {"cancelled": 1}, {"void": "true"}, {"status": "No_Show"},
    {"starttime": ""},
])
def test_from_plato_skips_what_isnt_a_session(change):
    assert c.from_plato({**PLATO_APPT, **change}) is None


def test_from_plato_home_visit_keeps_the_address():
    a = c.from_plato({**PLATO_APPT, "code_Bottom": "sCla", "color": "blue",
                      "description": "HOME VISIT — Physiotherapy.\nAddress: 12 Lentor Hill"})
    assert a.home and a.address == "12 Lentor Hill" and a.clinician == "Cheryl Long"


# --- the email ------------------------------------------------------------------

def test_clinic_email_has_everything_the_clinic_asked_for():
    a = c.from_plato(PLATO_APPT)
    text = c.render_text(a, "booked", None)
    for needle in ("Hi Sarah,", "Physiotherapy", "Thursday, 3 December 2026, 10:00am",
                   "Kristy Ng", "GOJI-4B308D", c.confirm_url(a.appointment_id),
                   "#01-13, Lentor Modern", "getting-here", "maps.app.goo.gl/Mm3eYLNMUwwx8USv8",
                   "$50 fee", "https://go.gojiphysio.com/confirm-wa", "calendar invite"):
        assert needle in text, needle
    assert "wa.me" not in text and "registration form" not in text
    assert "will come to" not in text


def test_registration_form_only_when_given():
    a = c.from_plato(PLATO_APPT)
    url = "https://clinic.platomedical.com/prereg/abc/def"
    assert url in c.render_text(a, "booked", url)
    assert url in c.render_html(a, "booked", url)


def test_home_visit_email_swaps_the_clinic_block():
    a = c.from_plato({**PLATO_APPT, "code_Bottom": "sCla",
                      "description": "Address: 12 Lentor Hill"})
    text = c.render_text(a, "booked", None)
    assert "will come to 12 Lentor Hill" in text and "parking" in text
    assert "Lentor Modern" not in text


def test_moved_email_says_so():
    a = c.from_plato(PLATO_APPT)
    assert c.subject(a, "moved").startswith("Moved: Physiotherapy, Thu 3 Dec at 10:00am")
    assert "has moved" in c.render_text(a, "moved", None)


def test_html_escapes_the_patient_name():
    a = c.from_plato({**PLATO_APPT, "title": "<b>Sarah</b>"})
    assert "<b>Sarah" not in c.render_html(a, "booked", None)


# --- calendar invite ------------------------------------------------------------

def test_invite_lands_in_the_calendar_without_alerts_or_replies():
    ics = c.build_ics(c.from_plato(PLATO_APPT), sequence=2, now=STAMP)
    assert "METHOD:REQUEST" in ics
    assert "UID:5e8cd7cdcfb94ef586a66764e84b308d@gojiphysio.com" in ics
    assert "SEQUENCE:2" in ics
    # Wall clock as Plato stores it, with the clinic's zone: never shifted.
    assert "DTSTART;TZID=Asia/Singapore:20261203T100000" in ics
    assert "DTEND;TZID=Asia/Singapore:20261203T110000" in ics
    assert "VALARM" not in ics
    unfolded = ics.replace("\r\n ", "")
    assert "RSVP=FALSE" in unfolded and "mailto:sarah@example.com" in unfolded
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))
    assert ics.endswith("\r\n") and "\n" not in ics.replace("\r\n", "")


def test_message_carries_the_invite_twice_and_marks_test_copies():
    a = c.from_plato(PLATO_APPT)
    msg = c.build_message(a, to="inbox@example.com", kind="booked", sequence=0,
                          form_url=None, now=STAMP)
    parsed = message_from_bytes(msg.as_bytes(), policy=default_policy)
    types = [p.get_content_type() for p in parsed.walk()]
    assert "text/calendar" in types and "application/ics" in types
    cal = next(p for p in parsed.walk() if p.get_content_type() == "text/calendar")
    assert cal.get_param("method") == "REQUEST"
    assert parsed["Subject"].startswith("[TEST] Booked:")
    real = c.build_message(a, to="sarah@example.com", kind="booked", sequence=0,
                           form_url=None, now=STAMP)
    assert real["Subject"].startswith("Booked:")


# --- modes --------------------------------------------------------------------------

RESULT = {"visit_id": "abcdef123456", "date": "2026-12-03", "time": "10:00",
          "duration_min": 60, "service": "Physiotherapy", "physio_focus": "Women's Health",
          "clinician_name": "Claire Ng", "home": False, "patient_id": "", "dry_run": False}
DRAFT = {"name": "Sarah Tan", "email": "sarah@example.com", "phone": "+65 9123 4567"}


def test_off_by_default_sends_nothing(sent, monkeypatch):
    monkeypatch.delenv("CONFIRMATIONS_MODE", raising=False)
    bq = FakeBQ()
    assert c.on_booking(FakePlato(), bq, RESULT, DRAFT, source="web") is None
    assert not sent and not bq.queries
    assert c.legacy_customer_email()


def test_test_mode_sends_to_the_test_inbox_only(sent, monkeypatch):
    monkeypatch.setenv("CONFIRMATIONS_MODE", "test")
    bq = FakeBQ()
    assert c.on_booking(FakePlato(), bq, RESULT, DRAFT, source="web") == "test"
    assert sent[0]["To"] == "inbox@example.com"
    assert bq.inserts[0]["status"] == "test" and bq.inserts[0]["source"] == "web"
    assert c.legacy_customer_email()  # patients keep the old email meanwhile


def test_test_mode_without_an_inbox_stays_off(sent, monkeypatch):
    monkeypatch.setenv("CONFIRMATIONS_MODE", "test")
    monkeypatch.setenv("CONFIRMATIONS_TEST_TO", "")
    assert not c.enabled()


def test_live_sends_to_the_patient_and_ledgers_no_address(sent, monkeypatch):
    live(monkeypatch)
    bq = FakeBQ()
    assert c.on_booking(FakePlato(), bq, RESULT, DRAFT, source="whatsapp") == "sent"
    assert sent[0]["To"] == "sarah@example.com"
    row = bq.inserts[0]
    assert row["status"] == "sent" and row["seq"] == 0 and row["kind"] == "booked"
    assert "sarah" not in repr(row).lower()
    assert not c.legacy_customer_email()


def test_live_test_patient_only_mails_the_test_inbox(sent, monkeypatch):
    live(monkeypatch)
    c.on_booking(FakePlato(), FakeBQ(), RESULT,
                 {**DRAFT, "name": "ZZ Goji Shop Test"}, source="whatsapp")
    assert sent[0]["To"] == "inbox@example.com"


def test_dry_run_booking_sends_nothing(sent, monkeypatch):
    live(monkeypatch)
    assert c.on_booking(FakePlato(), FakeBQ(), {**RESULT, "dry_run": True}, DRAFT,
                        source="whatsapp") is None
    assert not sent


def test_failed_send_is_ledgered_without_the_address(sent, monkeypatch):
    live(monkeypatch)

    def boom(msg):
        raise RuntimeError("550 rejected sarah@example.com")
    monkeypatch.setattr(c, "_send", boom)
    bq = FakeBQ()
    assert c.on_booking(FakePlato(), bq, RESULT, DRAFT, source="web") == "failed"
    assert bq.inserts[0]["status"] == "failed"
    assert "sarah@example.com" not in bq.inserts[0]["note"]


# --- registration form: until the Clinic Consent Form is signed -----------------

def _body(msg):
    return msg.get_body(preferencelist=("plain",)).get_content()


SIGNED = {"others": {"consents": [{"title": "Clinic Consent Form", "name": "consent.html",
                                    "created_on": 1793000000}]}}


FORM = "https://booking.gojiphysio.com/form/"


def test_no_profile_gets_the_form_link_without_a_plato_read(sent, monkeypatch):
    live(monkeypatch)
    plato = FakePlato()
    result = dict(RESULT)
    c.on_booking(plato, FakeBQ(profile=None), result, DRAFT, source="web")
    assert plato.gets == []
    assert FORM + "abcdef123456." in _body(sent[0])
    # The WhatsApp callback carries the same link's token.
    assert result["form_token"].startswith("abcdef123456.")


@pytest.mark.parametrize("profile", [("p123", False), ("p9", True)])
def test_existing_profile_never_gets_the_form(sent, monkeypatch, profile):
    """Clinic decision (26 Nov 2026): gaps in an existing profile are fixed in
    person, signed consent or not. No Plato read either."""
    live(monkeypatch)
    plato = FakePlato()
    result = {**RESULT, "patient_id": profile[0]}
    c.on_booking(plato, FakeBQ(profile=profile), result, DRAFT, source="whatsapp")
    assert plato.gets == [] and "registration form" not in _body(sent[0])
    assert "form_token" not in result


def test_signed_patient_gets_no_form_and_no_plato_read(sent, monkeypatch):
    live(monkeypatch)
    plato = FakePlato()
    result = dict(RESULT)
    c.on_booking(plato, FakeBQ(profile=("p9", True)), result, DRAFT, source="web")
    assert plato.gets == [] and "registration form" not in _body(sent[0])
    assert "form_token" not in result


def test_no_secret_means_no_form(sent, monkeypatch):
    live(monkeypatch)
    monkeypatch.setattr(c, "INTERNAL_TOKEN", "")
    c.on_booking(FakePlato(), FakeBQ(profile=None), RESULT, DRAFT, source="web")
    assert "registration form" not in _body(sent[0])


def test_lookup_failure_means_no_form(sent, monkeypatch):
    live(monkeypatch)

    class BrokenBQ(FakeBQ):
        def query(self, sql, job_config=None):
            if "AS signed" in sql:
                raise RuntimeError("no such column")
            return super().query(sql, job_config)
    plato = FakePlato()
    c.on_booking(plato, BrokenBQ(), RESULT, DRAFT, source="web")
    assert plato.gets == [] and "registration form" not in _body(sent[0])


def test_moved_email_never_carries_the_form(sent, monkeypatch):
    live(monkeypatch)
    plato = FakePlato()
    c.on_plato_appointment(plato, FakeBQ(last=("2026-12-02 10:00", 0), profile=None),
                           PLATO_APPT, source="staff", now=NOW)
    assert "registration form" not in _body(sent[0])


def test_consent_title_matches_the_nightly_import():
    src = open("ingestion/plato_patients/main.py").read()
    assert f'CONSENT_TITLE = "{c.CONSENT_TITLE}"' in src


# --- staff bookings: webhook, sweep, moves ---------------------------------------------

def test_staff_booking_confirmed_once(sent, monkeypatch):
    live(monkeypatch)
    bq = FakeBQ()
    assert c.on_plato_appointment(FakePlato(), bq, PLATO_APPT, source="staff",
                                  now=NOW) == "sent"
    assert bq.inserts[0]["start"] == "2026-12-03 10:00"
    # The same appointment again (an edit to its notes): nothing.
    bq2 = FakeBQ(last=("2026-12-03 10:00", 0))
    assert c.on_plato_appointment(FakePlato(), bq2, PLATO_APPT, source="staff",
                                  now=NOW) is None
    assert len(sent) == 1


def test_staff_move_sends_moved_with_next_sequence(sent, monkeypatch):
    live(monkeypatch)
    bq = FakeBQ(last=("2026-12-02 10:00", 1))
    assert c.on_plato_appointment(FakePlato(), bq, PLATO_APPT, source="staff",
                                  now=NOW) == "sent"
    assert bq.inserts[0]["kind"] == "moved" and bq.inserts[0]["seq"] == 2
    assert sent[0]["Subject"].startswith("Moved:")
    cal = next(p for p in sent[0].walk() if p.get_content_type() == "text/calendar")
    assert "SEQUENCE:2" in cal.get_content()


@pytest.mark.parametrize("change", [
    {"created_on": "2026-11-20 10:00:00"},   # made before the cutoff
    {"starttime": "2026-11-25 10:00:00", "endtime": "2026-11-25 11:00:00"},  # in the past
])
def test_staff_path_leaves_old_and_past_appointments(sent, monkeypatch, change):
    live(monkeypatch)
    assert c.on_plato_appointment(FakePlato(), FakeBQ(), {**PLATO_APPT, **change},
                                  source="sweep", now=NOW) is None
    assert not sent


def test_staff_path_off_without_a_cutoff(sent, monkeypatch):
    live(monkeypatch)
    monkeypatch.setenv("CONFIRMATIONS_SINCE", "")
    assert c.on_plato_appointment(FakePlato(), FakeBQ(), PLATO_APPT, source="staff",
                                  now=NOW) is None


def test_linked_patient_email_comes_from_the_profile(sent, monkeypatch):
    live(monkeypatch)
    rec = {**PLATO_APPT, "email": "", "patient_id": "p9", "title": "S Tan"}
    bq = FakeBQ(contact={"full_name": "Sarah Tan", "email": "sarah@example.com"})
    assert c.on_plato_appointment(FakePlato(), bq, rec, source="staff", now=NOW) == "sent"
    assert sent[0]["To"] == "sarah@example.com" and "Hi Sarah," in _body(sent[0])


def test_no_email_anywhere_sends_and_ledgers_nothing(sent, monkeypatch):
    live(monkeypatch)
    bq = FakeBQ()
    rec = {**PLATO_APPT, "email": "", "patient_id": "p9"}
    assert c.on_plato_appointment(FakePlato(), bq, rec, source="staff", now=NOW) is None
    assert not sent and not bq.inserts


def test_gives_up_after_repeated_failures(sent, monkeypatch):
    live(monkeypatch)
    assert c.on_plato_appointment(FakePlato(), FakeBQ(failures=3), PLATO_APPT,
                                  source="sweep", now=NOW) is None
    assert not sent


def test_webhook_ids_only_appointment_upserts_for_our_db():
    payload = {"events": [
        {"db": "gojihealth", "event": "appointment:upsert", "object_id": "a1"},
        {"db": "gojihealth", "event": "appointment:upsert", "object_id": "a1"},
        {"db": "gojihealth", "event": "appointment:delete", "object_id": "a2"},
        {"db": "gojihealth", "event": "patient:upsert", "object_id": "p1"},
        {"db": "elsewhere", "event": "appointment:upsert", "object_id": "a3"},
        {"db": "gojihealth", "event": "appointment:upsert", "object_id": "bad id!"},
    ]}
    assert c.webhook_appointment_ids(payload, "gojihealth") == ["a1"]
    assert c.webhook_appointment_ids(None, "gojihealth") == []


def test_handle_webhook_reads_back_and_confirms(sent, monkeypatch):
    live(monkeypatch)
    monkeypatch.setattr(c, "_take_read", lambda: True)
    future = {**PLATO_APPT, "starttime": "2030-01-02 10:00:00", "endtime": "2030-01-02 11:00:00"}
    plato = FakePlato(record=future)
    assert c.handle_webhook(plato, FakeBQ(), ["5e8cd7cd"]) == 1
    assert plato.gets == ["/appointment/5e8cd7cd"]


# --- app wiring -------------------------------------------------------------------

def test_app_live_mode_drops_the_old_customer_email(monkeypatch):
    live(monkeypatch)
    monkeypatch.setenv("CONFIRMATIONS_TEST_TO", "")
    calls = []
    monkeypatch.setattr(app_mod.mailer, "send_customer_booking_email",
                        lambda r, d: calls.append("legacy"))
    monkeypatch.setattr(app_mod.confirmations, "on_booking",
                        lambda p, b, r, d, source: calls.append(("new", source)))
    monkeypatch.setattr(app_mod, "plato", lambda: None)
    monkeypatch.setattr(app_mod, "bq", lambda: None)
    app_mod._confirm_customer(RESULT, DRAFT, "web")
    assert calls == [("new", "web")]


def test_app_off_mode_keeps_the_old_email_only(monkeypatch):
    monkeypatch.delenv("CONFIRMATIONS_MODE", raising=False)
    calls = []
    monkeypatch.setattr(app_mod.mailer, "send_customer_booking_email",
                        lambda r, d: calls.append("legacy"))
    monkeypatch.setattr(app_mod.confirmations, "on_booking",
                        lambda *a, **k: calls.append("new"))
    app_mod._confirm_customer(RESULT, DRAFT, "web")
    assert calls == ["legacy"]


def test_webhook_route_hands_appointments_to_confirmations(monkeypatch):
    live(monkeypatch)
    monkeypatch.setenv("CONFIRMATIONS_TEST_TO", "")
    monkeypatch.setattr(app_mod, "INTERNAL_TOKEN", "tok")
    monkeypatch.setattr(app_mod, "plato", lambda: None)
    monkeypatch.setattr(app_mod, "bq", lambda: None)
    monkeypatch.setattr(app_mod, "_run_webhook_work", lambda fn: fn())
    got = []
    monkeypatch.setattr(app_mod.confirmations, "handle_webhook",
                        lambda p, b, ids: got.append(ids) or 0)
    path = "/plato/webhook/" + app_mod.patient_contacts.webhook_token("tok")
    r = app_mod.app.test_client().post(path, json={"events": [
        {"db": "gojihealth", "event": "appointment:upsert", "object_id": "a1"}]})
    assert r.status_code == 200 and got == [["a1"]]


def test_confirmed_appointment_is_thanked_not_asked():
    a = c.from_plato({**PLATO_APPT, "code_Right": "qK8x"})
    assert a.confirmed
    for body in (c.render_text(a, "moved", None), c.render_html(a, "moved", None)):
        assert "confirmed this appointment" in body
        assert c.confirm_url(a.appointment_id) not in body


# --- WhatsApp: front-desk bookings and the go-ahead -------------------------------

class FakeResp:
    status_code = 200


def test_front_desk_booking_is_confirmed_on_whatsapp_too(sent, monkeypatch):
    live(monkeypatch)
    monkeypatch.setattr(c, "WA_AGENT_URL", "https://wa.example")
    monkeypatch.setattr(c, "INTERNAL_TOKEN", "tok")
    posts = []
    import requests
    monkeypatch.setattr(requests, "post", lambda url, json=None, timeout=None, headers=None:
                        posts.append((url, json)) or FakeResp())
    bq = FakeBQ()
    assert c.on_plato_appointment(FakePlato(), bq, PLATO_APPT, source="staff", now=NOW) == "sent"
    url, body = posts[0]
    assert url == "https://wa.example/internal/booking-confirmed"
    assert body["send_template"] is True and body["source"] == "staff"
    assert (body["date"], body["time"], body["first_name"]) == ("2026-12-03", "10:00", "Sarah")
    assert bq.inserts[0]["channel"] == "both"


def test_front_desk_booking_without_email_goes_on_whatsapp_only(sent, monkeypatch):
    live(monkeypatch)
    monkeypatch.setattr(c, "WA_AGENT_URL", "https://wa.example")
    monkeypatch.setattr(c, "INTERNAL_TOKEN", "tok")
    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResp())
    bq = FakeBQ()
    rec = {**PLATO_APPT, "email": ""}
    assert c.on_plato_appointment(FakePlato(), bq, rec, source="staff", now=NOW) == "sent"
    assert not sent and bq.inserts[0]["channel"] == "whatsapp"


def test_staff_move_is_email_only(sent, monkeypatch):
    live(monkeypatch)
    monkeypatch.setattr(c, "WA_AGENT_URL", "https://wa.example")
    monkeypatch.setattr(c, "INTERNAL_TOKEN", "tok")
    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("no WhatsApp for a move"))
    c.on_plato_appointment(FakePlato(), FakeBQ(last=("2026-12-02 10:00", 0)), PLATO_APPT,
                           source="staff", now=NOW)
    assert sent[0]["Subject"].startswith("Moved:")


def test_test_mode_never_whatsapps(sent, monkeypatch):
    monkeypatch.setenv("CONFIRMATIONS_MODE", "test")
    monkeypatch.setattr(c, "WA_AGENT_URL", "https://wa.example")
    monkeypatch.setattr(c, "INTERNAL_TOKEN", "tok")
    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("WhatsApp in test mode"))
    c.on_plato_appointment(FakePlato(), FakeBQ(), PLATO_APPT, source="staff", now=NOW)
    assert sent[0]["To"] == "inbox@example.com"


def test_web_callback_carries_the_go_ahead_only_when_live(monkeypatch):
    for mode, expected in (("off", False), ("test", False), ("live", True)):
        monkeypatch.setenv("CONFIRMATIONS_MODE", mode)
        monkeypatch.setattr(app_mod, "WA_AGENT_URL", "https://wa.example")
        monkeypatch.setattr(app_mod, "INTERNAL_TOKEN", "tok")
        monkeypatch.setattr(app_mod, "_run_async", lambda fn: fn())
        posts = []
        monkeypatch.setattr(app_mod.requests, "post", lambda url, json=None, timeout=None,
                            headers=None: posts.append(json) or FakeResp())
        app_mod._notify_wa_agent({"reference": "GOJI-1"}, {"phone": "+6591234567"}, "web")
        assert posts[0]["send_template"] is expected, mode


# --- the form link and where it goes --------------------------------------------

from booking import formlink


def test_form_token_round_trip_and_tamper():
    t = formlink.token("4b1e9c0d2a7f4e3b8c6d5a4f3e2d1c0b", "sec")
    assert formlink.verify(t, "sec") == "4b1e9c0d2a7f4e3b8c6d5a4f3e2d1c0b"
    assert formlink.verify(t, "other") is None
    assert formlink.verify("4b1e9c0d2a7f4e3b8c6d5a4f3e2d1c0c" + t[32:], "sec") is None
    assert formlink.verify("../../etc", "sec") is None and formlink.token("a", "") == ""


class DestPlato:
    def __init__(self, appt, patient=None, prereg=True):
        self.appt, self.prereg = appt, prereg
        self.patient = {"email": "sarah@example.com"} if patient is None else patient
        self.params = []

    def get(self, path, **kw):
        self.params.append(kw.get("params"))
        if path.endswith("/prereg"):
            return {"url": "https://clinic.platomedical.com/prereg/a/b"} if self.prereg else \
                {"error": "Appointment is already linked with a patient profile."}
        if path.endswith("/updatelink"):
            return {"url": "https://clinic.platomedical.com/secure/regupdate/a/b"}
        if path.startswith("/patient/"):
            return [self.patient]
        return [self.appt] if self.appt else []


def test_destination_no_profile_is_prereg():
    assert c.form_destination(DestPlato({"_id": "a1", "patient_id": ""}), "a1") == (
        "form", "https://clinic.platomedical.com/prereg/a/b")


def test_destination_with_a_profile_is_done():
    assert c.form_destination(DestPlato({"_id": "a1", "patient_id": "p1"}), "a1") == (
        "done", None)


def test_destination_linked_since_the_link_was_sent_is_done():
    class Linked(DestPlato):
        reads = 0

        def get(self, path, **kw):
            if path == "/appointment/a1":
                Linked.reads += 1
                return [{"_id": "a1", "patient_id": "" if Linked.reads == 1 else "p1"}]
            return super().get(path, **kw)
    assert c.form_destination(Linked({"_id": "a1"}, prereg=False), "a1") == ("done", None)


def test_destination_gone():
    assert c.form_destination(DestPlato(None), "a1") == ("gone", None)


def test_form_route(monkeypatch):
    monkeypatch.setattr(app_mod, "INTERNAL_TOKEN", "tok")
    client = app_mod.app.test_client()
    t = formlink.token("4b1e9c0d2a7f4e3b8c6d5a4f3e2d1c0b", "tok")
    monkeypatch.setattr(app_mod, "plato", lambda: DestPlato({"_id": "x", "patient_id": ""}))
    r = client.get("/form/" + t)
    assert r.status_code == 302 and r.headers["Location"].endswith("/prereg/a/b")
    monkeypatch.setattr(app_mod, "plato", lambda: DestPlato({"_id": "x", "patient_id": "p"},
                                                            SIGNED))
    r = client.get("/form/" + t)
    assert r.status_code == 200 and b"all set" in r.data
    assert client.get("/form/" + t[:-1] + "0").status_code == 404


def test_staff_path_reads_use_the_priority_share(sent, monkeypatch):
    """The 5-minute availability refresh can hold Plato's whole bulk share; the
    first staff booking after go-live failed its bulk read (26 Nov 2026)."""
    live(monkeypatch)
    monkeypatch.setattr(c, "_take_read", lambda: True)
    future = {**PLATO_APPT, "starttime": "2030-01-02 10:00:00", "endtime": "2030-01-02 11:00:00"}
    calls = []

    class Rec(FakePlato):
        def get(self, path, **kw):
            calls.append(kw.get("bulk", False))
            return super().get(path, **kw)
    c.handle_webhook(Rec(record=future, patient={"created_by": "api"}),
                     FakeBQ(profile=("p1", False)), ["5e8cd7cd"])
    assert calls and not any(calls)
