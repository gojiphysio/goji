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

    def __init__(self, last=None, failures=0, contact=None, earlier=0, profiles=0):
        self.last, self.failures, self.contact = last, failures, contact
        self.earlier, self.profiles = earlier, profiles
        self.inserts: list[dict] = []
        self.queries: list[str] = []

    def query(self, sql, job_config=None):
        self.queries.append(sql)
        params = {p.name: p.value for p in (job_config.query_parameters if job_config else [])}
        if sql.lstrip().startswith("INSERT"):
            self.inserts.append(params)
            rows = []
        elif "AS earlier" in sql:
            rows = [{"earlier": self.earlier, "profiles": self.profiles}]
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
    def __init__(self, record=None):
        self.record = record
        self.gets: list[str] = []

    def get(self, path, **kw):
        self.gets.append(path)
        if path.endswith("/prereg"):
            return {"url": "https://clinic.platomedical.com/prereg/abc/def"}
        if path.endswith("/updatelink"):
            return {"url": "https://clinic.platomedical.com/secure/regupdate/abc/def"}
        return [self.record]  # Plato answers GET /appointment/{id} with a list


@pytest.fixture
def sent(monkeypatch):
    out: list = []
    monkeypatch.setattr(c, "SMTP_PASS", "app-password")
    monkeypatch.setattr(c, "_send", out.append)
    monkeypatch.setenv("CONFIRMATIONS_TEST_TO", "inbox@example.com")
    monkeypatch.setenv("CONFIRMATIONS_SINCE", "2026-11-26 08:00")
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
    bq = FakeBQ(earlier=1)
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
    bq = FakeBQ(earlier=1)
    assert c.on_booking(FakePlato(), bq, RESULT, DRAFT, source="whatsapp") == "sent"
    assert sent[0]["To"] == "sarah@example.com"
    row = bq.inserts[0]
    assert row["status"] == "sent" and row["seq"] == 0 and row["kind"] == "booked"
    assert "sarah" not in repr(row).lower()
    assert not c.legacy_customer_email()


def test_live_test_patient_only_mails_the_test_inbox(sent, monkeypatch):
    live(monkeypatch)
    c.on_booking(FakePlato(), FakeBQ(earlier=1), RESULT,
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
    bq = FakeBQ(earlier=1)
    assert c.on_booking(FakePlato(), bq, RESULT, DRAFT, source="web") == "failed"
    assert bq.inserts[0]["status"] == "failed"
    assert "sarah@example.com" not in bq.inserts[0]["note"]


# --- first visit: Plato's registration form -------------------------------------------

def _body(msg):
    return msg.get_body(preferencelist=("plain",)).get_content()


def test_first_visit_unlinked_gets_the_prereg_form(sent, monkeypatch):
    live(monkeypatch)
    plato = FakePlato()
    c.on_booking(plato, FakeBQ(earlier=0, profiles=0), RESULT, DRAFT, source="web")
    assert plato.gets == ["/appointment/abcdef123456/prereg"]
    assert "prereg/abc/def" in _body(sent[0])


def test_new_whatsapp_patient_gets_the_profile_form(sent, monkeypatch):
    live(monkeypatch)
    plato = FakePlato()
    c.on_booking(plato, FakeBQ(), {**RESULT, "patient_id": "p123", "patient_created": True},
                 DRAFT, source="whatsapp")
    assert plato.gets == ["/patient/p123/updatelink"]
    assert "regupdate" in _body(sent[0])


@pytest.mark.parametrize("earlier,profiles", [(1, 0), (0, 1)])
def test_returning_patient_gets_no_form(sent, monkeypatch, earlier, profiles):
    live(monkeypatch)
    plato = FakePlato()
    c.on_booking(plato, FakeBQ(earlier=earlier, profiles=profiles), RESULT, DRAFT, source="web")
    assert plato.gets == [] and "registration form" not in _body(sent[0])


# --- staff bookings: webhook, sweep, moves ---------------------------------------------

def test_staff_booking_confirmed_once(sent, monkeypatch):
    live(monkeypatch)
    bq = FakeBQ(earlier=1)
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
    bq = FakeBQ(contact={"full_name": "Sarah Tan", "email": "sarah@example.com"}, earlier=1)
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
    assert c.handle_webhook(plato, FakeBQ(earlier=1), ["5e8cd7cd"]) == 1
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
