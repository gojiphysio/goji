"""
Unit tests for the appointment-reminder job — pure functions only, no network,
no BigQuery. These gate the deploy in .github/workflows/deploy-dashboard.yml.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import main
import reminder_mailer as mailer
import reminder_whatsapp as wa

SGT = ZoneInfo("Asia/Singapore")


# --- the D+2 window --------------------------------------------------------

def test_monday_noon_targets_wednesday():
    """The clinic's own example: run Monday, remind Wednesday's appointments."""
    monday_noon = datetime(2026, 9, 7, 12, 0, tzinfo=SGT)
    assert monday_noon.strftime("%A") == "Monday"
    assert main.target_date(2, now=monday_noon) == "2026-09-09"
    assert datetime.fromisoformat("2026-09-09").strftime("%A") == "Wednesday"


def test_weekend_runs_leave_no_gap():
    """Saturday covers Monday and Sunday covers Tuesday, so running all 7 days
    means no appointment is missed over a weekend."""
    saturday = datetime(2026, 9, 12, 12, 0, tzinfo=SGT)
    sunday = datetime(2026, 9, 13, 12, 0, tzinfo=SGT)
    assert main.target_date(2, now=saturday) == "2026-09-14"   # Monday
    assert main.target_date(2, now=sunday) == "2026-09-15"     # Tuesday


def test_appt_date_comes_from_the_rows_not_recomputed():
    """The D+2 window lives in the view's WHERE clause. If the job recomputed the
    date in Python the two could drift and patients would be told a date that
    doesn't match their appointment, so the date is read off the data."""
    from datetime import date
    rows = [{"appointment_id": "a1", "appt_date": date(2026, 9, 9)}]
    assert main.resolve_appt_date(rows) == "2026-09-09"
    # A string date (some drivers) works too.
    assert main.resolve_appt_date([{"appt_date": "2026-09-09"}]) == "2026-09-09"


def test_empty_run_still_gets_a_date_label():
    """No appointments means no row to read a date from; the digest still needs
    a date in its subject line."""
    monday_noon = datetime(2026, 9, 7, 12, 0, tzinfo=SGT)
    assert main.target_date(now=monday_noon) == "2026-09-09"
    assert main.resolve_appt_date([]) == main.target_date()


def test_target_date_is_clinic_local_not_utc():
    """23:00 UTC on the 7th is already 07:00 on the 8th in Singapore, so the
    window must advance with SGT (-> the 10th), not with UTC (-> the 9th)."""
    late_utc = datetime(2026, 9, 7, 23, 0, tzinfo=ZoneInfo("UTC"))
    assert main.target_date(2, now=late_utc) == "2026-09-10"


# --- grouping --------------------------------------------------------------

def _row(appt_id, email, time, name="Sarah Tan", home=False, phone="+6591234567"):
    return {"appointment_id": appt_id, "email": email, "time": time,
            "name": name, "is_home_visit": home, "phone": phone}


def test_same_day_appointments_become_one_email():
    """Physio at 9am then Pilates at 2pm is ONE email listing both, not two."""
    groups, unreachable = main.group_by_recipient([
        _row("a1", "sarah@example.com", "09:00"),
        _row("a2", "sarah@example.com", "14:00"),
    ])
    assert unreachable == []
    assert len(groups) == 1
    assert groups[0]["times"] == ["09:00", "14:00"]
    # Both appointments still get their own ledger row.
    assert sorted(groups[0]["appointment_ids"]) == ["a1", "a2"]


def test_email_match_is_case_insensitive():
    groups, _ = main.group_by_recipient([
        _row("a1", "Sarah@Example.com", "09:00"),
        _row("a2", "sarah@example.com", "14:00"),
    ])
    assert len(groups) == 1


def test_missing_email_is_unreachable_not_an_error():
    groups, unreachable = main.group_by_recipient([
        _row("a1", "", "09:00", name="Marcus Lim"),
        _row("a2", "   ", "10:00", name="Priya K"),
        _row("a3", "ok@example.com", "11:00"),
    ])
    assert len(groups) == 1
    assert len(unreachable) == 2
    assert {r["name"] for r in unreachable} == {"Marcus Lim", "Priya K"}


def test_groups_are_ordered_by_first_appointment():
    groups, _ = main.group_by_recipient([
        _row("a1", "late@example.com", "16:00"),
        _row("a2", "early@example.com", "08:00"),
    ])
    assert [g["email"] for g in groups] == ["early@example.com", "late@example.com"]


def test_home_visit_and_clinic_flags():
    clinic, _ = main.group_by_recipient([_row("a1", "x@y.com", "09:00")])
    assert clinic[0]["has_clinic"] and not clinic[0]["has_home_visit"]
    home, _ = main.group_by_recipient([_row("a1", "x@y.com", "09:00", home=True)])
    assert home[0]["has_home_visit"] and not home[0]["has_clinic"]
    # A patient with both on one day gets both blocks.
    both, _ = main.group_by_recipient([
        _row("a1", "x@y.com", "09:00"),
        _row("a2", "x@y.com", "15:00", home=True),
    ])
    assert both[0]["has_clinic"] and both[0]["has_home_visit"]


# --- rendering -------------------------------------------------------------

def test_wall_clock_times_are_not_shifted():
    """REGRESSION GUARD. stg.appointments.start_at holds clinic wall-clock parsed
    as UTC, and the view formats it at 'UTC' to read it back out. A 9am session
    must render as '9:00 am' — if anyone "fixes" the view to Asia/Singapore this
    becomes 5:00 pm and every patient is told the wrong time."""
    assert mailer._fmt_time("09:00") == "9:00 am"
    assert mailer._fmt_time("14:30") == "2:30 pm"
    assert mailer._fmt_time("00:15") == "12:15 am"
    assert mailer._fmt_time("12:00") == "12:00 pm"


def test_fmt_when_single_and_multiple():
    assert mailer.fmt_when("2026-09-09", ["09:00"]) == \
        "Wednesday, 9 September 2026 at 9:00 am"
    assert mailer.fmt_when("2026-09-09", ["09:00", "14:00"]) == \
        "Wednesday, 9 September 2026 at 9:00 am and 2:00 pm"
    assert mailer.fmt_when("2026-09-09", ["09:00", "14:00", "18:30"]) == \
        "Wednesday, 9 September 2026 at 9:00 am, 2:00 pm and 6:30 pm"


def test_first_name_only():
    assert mailer.first_name("Sarah Tan") == "Sarah"
    assert mailer.first_name("Sarah") == "Sarah"
    # Never render 'Dear ,'
    assert mailer.first_name(None) == "there"
    assert mailer.first_name("  ") == "there"


def test_clinic_body_has_directions_and_no_home_visit_block():
    body = mailer.render_reminder_body(
        "Sarah Tan", "2026-09-09", ["09:00"],
        has_clinic=True, has_home_visit=False)
    assert body.startswith("Dear Sarah,")
    assert "Wednesday, 9 September 2026 at 9:00 am" in body
    assert "Lentor Modern" in body
    assert "getting-here" in body
    assert "home visit" not in body.lower()
    assert "$50 fee" in body
    assert "Team Goji Physiotherapy" in body


def test_home_visit_body_has_no_clinic_address():
    body = mailer.render_reminder_body(
        "Marcus Lim", "2026-09-09", ["15:00"],
        has_clinic=False, has_home_visit=True)
    assert "Lentor Modern" not in body
    assert "Google Maps" not in body
    assert "meet you at the address confirmed" in body


def test_whatsapp_cta_is_the_tracked_redirector():
    """Repo rule: every outbound customer CTA routes through go.gojiphysio.com so
    the click is attributable. Never a raw wa.me link."""
    body = mailer.render_reminder_body(
        "Sarah", "2026-09-09", ["09:00"], has_clinic=True, has_home_visit=False)
    assert "go.gojiphysio.com/reminder-wa" in body
    assert "wa.me" not in body


# --- digest ----------------------------------------------------------------

def test_digest_lists_unreachable_patients_for_whatsapp():
    body = mailer.render_digest_body(
        sent=[{"name": "Sarah Tan", "time": "09:00"}],
        skipped=[{"name": "Marcus Lim", "phone": "+6591112222", "time": "14:00"}],
        failed=[],
        target_date="2026-09-09", dry_run=False)
    assert "Marcus Lim" in body
    assert "+6591112222" in body
    assert "WhatsApp" in body
    assert "Sent: 1 reminder(s)" in body


def test_dry_run_digest_says_so_loudly():
    body = mailer.render_digest_body(
        sent=[{"name": "Sarah Tan", "time": "09:00"}],
        skipped=[], failed=[], target_date="2026-09-09", dry_run=True)
    assert body.startswith("DRY RUN")
    assert "Would have sent: 1" in body


def test_digest_reports_failures_as_retryable():
    body = mailer.render_digest_body(
        sent=[], skipped=[],
        failed=[{"name": "Sarah Tan", "time": "09:00", "error": "SMTP timeout"}],
        target_date="2026-09-09", dry_run=False)
    assert "SMTP timeout" in body
    assert "retry" in body.lower()


# --- PII boundary ----------------------------------------------------------

def test_ledger_notes_never_carry_an_email_address():
    """marts.appointment_reminder_events is PII-free by design. The likeliest
    send failure is SMTPRecipientsRefused, whose str() is a dict keyed on the
    patient's address — writing it raw would put PII in the warehouse."""
    import smtplib
    err = smtplib.SMTPRecipientsRefused(
        {"sarah.tan@example.com": (550, b"5.1.1 User unknown")})
    note = main.scrub(str(err))
    assert "sarah.tan@example.com" not in note
    assert "@example.com" not in note
    assert "[email]" in note
    # The actionable part survives.
    assert "550" in note


def test_scrub_handles_empty_and_long_input():
    assert main.scrub(None) is None
    assert main.scrub("") is None
    assert len(main.scrub("x" * 900)) == 400


# --- container build -------------------------------------------------------

def test_multi_source_copy_ends_with_slash():
    """Docker rejects a multi-source COPY whose destination isn't a directory
    ending in '/'. This shipped broken once: the sibling ingestion jobs copy a
    single file, so their `COPY main.py .` is fine and the pattern doesn't carry
    over to two files. The failure only surfaced in Cloud Build, after merge to
    main, and it blocked every deploy step behind it."""
    import pathlib
    dockerfile = pathlib.Path(__file__).with_name("Dockerfile").read_text()
    for line in dockerfile.splitlines():
        line = line.strip()
        if not line.upper().startswith("COPY "):
            continue
        parts = line.split()[1:]          # drop 'COPY'
        parts = [p for p in parts if not p.startswith("--")]
        if len(parts) > 2:                # >1 source + 1 destination
            dest = parts[-1]
            assert dest.endswith("/"), (
                f"multi-source COPY needs a trailing slash on the destination: {line!r}")


def test_dockerfile_copies_every_module_main_imports():
    """A module left out of the COPY builds fine and then crashes on the first
    scheduled run, which is the worst place to find out."""
    import pathlib
    here = pathlib.Path(__file__).parent
    dockerfile = (here / "Dockerfile").read_text()
    local_modules = {p.name for p in here.glob("*.py")
                     if not p.name.startswith("test_")}
    for mod in local_modules:
        assert mod in dockerfile, f"{mod} is never COPYed into the image"


def test_no_log_line_interpolates_a_recipient_address():
    """Cloud Logging is a different surface from BigQuery, but the same PII
    boundary applies: it's retained ~30 days and readable by anyone with a
    logging role. This shipped leaking addresses once —

        INFO DRY RUN would send to beatricekohh@gmail.com (1 appt)

    — so log lines key on appointment_id instead. The digest to hello@ is where
    the human-readable list belongs."""
    import ast, pathlib
    src = pathlib.Path(main.__file__).read_text()
    tree = ast.parse(src)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not (isinstance(f, ast.Attribute)
                and isinstance(f.value, ast.Name) and f.value.id == "log"):
            continue
        for arg in node.args[1:]:            # args after the format string
            flat = ast.unparse(arg)
            # g["email"] / r["email"] / .get("email") in a log argument.
            if "email" in flat and "no email" not in flat:
                offenders.append(f"line {node.lineno}: log(..., {flat})")
            # ...and the same for a phone number or a WhatsApp recipient.
            if "phone" in flat or flat in ("to", "wa_to", "params"):
                offenders.append(f"line {node.lineno}: log(..., {flat})")
    assert not offenders, "recipient address in a log line: " + "; ".join(offenders)


def test_no_whatsapp_log_line_interpolates_a_recipient():
    """Same boundary in the WhatsApp module: log the appointment, never `to`."""
    import ast, pathlib
    tree = ast.parse(pathlib.Path(wa.__file__).read_text())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "log"):
            for arg in node.args[1:]:
                assert ast.unparse(arg) not in ("to", "params", "OVERRIDE_TO"), (
                    f"line {node.lineno}: recipient in a log line")


# --- test mode (REMINDER_OVERRIDE_TO) --------------------------------------

def _sent_messages(monkeypatch):
    """Capture EmailMessages instead of opening an SMTP connection."""
    captured = []
    monkeypatch.setattr(mailer, "_send", lambda msg, what, ref: captured.append(msg))
    monkeypatch.setattr(mailer, "SMTP_PASS", "x")
    return captured


def test_override_sends_to_the_override_address_not_the_patient(monkeypatch):
    monkeypatch.setattr(mailer, "OVERRIDE_TO", "hello@gojiphysio.com")
    msgs = _sent_messages(monkeypatch)
    mailer.send_reminder("patient@example.com", "Sarah Tan", "2026-09-12",
                         ["09:00"], has_clinic=True, has_home_visit=False)
    assert len(msgs) == 1
    assert msgs[0]["To"] == "hello@gojiphysio.com"
    assert "patient@example.com" not in str(msgs[0]["To"])
    # The intended recipient is visible in the subject so each can be checked.
    assert "patient@example.com" in msgs[0]["Subject"]
    assert msgs[0]["Subject"].startswith("[TEST -> ")


def test_override_body_is_identical_to_the_real_thing(monkeypatch):
    """The point of test mode is seeing exactly what the patient would get."""
    args = ("Sarah Tan", "2026-09-12", ["09:00"])
    kw = dict(has_clinic=True, has_home_visit=False)
    real = mailer.render_reminder_body(*args, **kw)

    monkeypatch.setattr(mailer, "OVERRIDE_TO", "hello@gojiphysio.com")
    msgs = _sent_messages(monkeypatch)
    mailer.send_reminder("patient@example.com", *args, **kw)
    text = msgs[0].get_body(preferencelist=("plain",)).get_content()
    assert text.rstrip("\n") == real.rstrip("\n")
    html = msgs[0].get_body(preferencelist=("html",)).get_content()
    assert html.strip() == mailer.render_reminder_html(*args, **kw).strip()


def test_without_override_the_patient_is_the_recipient(monkeypatch):
    monkeypatch.setattr(mailer, "OVERRIDE_TO", "")
    msgs = _sent_messages(monkeypatch)
    mailer.send_reminder("patient@example.com", "Sarah Tan", "2026-09-12",
                         ["09:00"], has_clinic=True, has_home_visit=False)
    assert msgs[0]["To"] == "patient@example.com"
    assert msgs[0]["Subject"] == mailer.SUBJECT
    assert "TEST" not in msgs[0]["Subject"]


def test_test_mode_ledgers_test_never_sent():
    """A 'sent' row would suppress the real reminder on the day, so an
    end-to-end test would silently cost those patients their reminder. Holds
    on both channels."""
    wa_http = FakeSession()
    out = main.dispatch(
        [_appt("a1", phone="91234567", email=""),
         _appt("a2", phone="", email="x@y.com")],
        DAY, dry_run=False, wa_enabled=True, test_mode=True,
        send_whatsapp=_wa_sender(wa_http), send_email=lambda g, d: None)
    assert {e["status"] for e in out["ledger"]} == {"test"}


def test_recipient_query_does_not_suppress_test_or_dry_run_rows():
    """Only 'sent' suppresses. 'test', 'dry_run' and 'failed' must fall through
    so the real reminder still goes out."""
    assert "!= 'sent'" in main.RECIPIENTS_SQL
    for status in ("test", "dry_run", "failed"):
        assert f"!= '{status}'" not in main.RECIPIENTS_SQL


def test_digest_announces_test_mode(monkeypatch):
    monkeypatch.setattr(mailer, "OVERRIDE_TO", "hello@gojiphysio.com")
    body = mailer.render_digest_body(
        sent=[{"name": "Sarah Tan", "time": "09:00"}], skipped=[], failed=[],
        target_date="2026-09-12", dry_run=False)
    assert body.startswith("TEST MODE")
    assert "No patient was emailed." in body



# ===========================================================================
# WhatsApp channel
# ===========================================================================

DAY = "2026-11-26"   # a Thursday


class FakeResponse:
    def __init__(self, status_code=200, body=None, text=None):
        self.status_code = status_code
        self._body = body
        self.text = text if text is not None else ("" if body is None else str(body))

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class FakeSession:
    """Stands in for requests: records every POST and answers from a queue
    (default: a 200 with a fresh wamid)."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if self.responses:
            r = self.responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        return FakeResponse(200, {"messaging_product": "whatsapp",
                                  "contacts": [{"input": "x", "wa_id": "x"}],
                                  "messages": [{"id": f"wamid.{len(self.calls)}"}]})

    def sent_to(self):
        return [c["json"]["to"] for c in self.calls]

    def appointment_ids(self):
        return [c["json"]["template"]["components"][1]["parameters"][0]["payload"]
                .split(":", 1)[1] for c in self.calls]


def _wa_sender(session):
    return lambda to, params, appt_id: wa.send_template(to, params, appt_id,
                                                        session=session)


def _appt(appt_id, *, phone="91234567", email="sarah@example.com", time="10:00",
          name="Sarah Tan", treatment="Physiotherapy", clinician="PCL", home=False):
    return {"appointment_id": appt_id, "phone": phone, "email": email,
            "time": time, "name": name, "treatment_type": treatment,
            "clinician_id": clinician, "is_home_visit": home}


class EmailSpy:
    def __init__(self, fail_for=()):
        self.groups = []
        self.fail_for = set(fail_for)

    def __call__(self, g, day):
        if g["email"] in self.fail_for:
            raise RuntimeError("SMTP timeout")
        self.groups.append(g)


def _run(rows, *, wa_enabled=True, dry_run=False, session=None, email=None):
    session = session if session is not None else FakeSession()
    email = email if email is not None else EmailSpy()
    out = main.dispatch(rows, DAY, dry_run=dry_run, wa_enabled=wa_enabled,
                        send_whatsapp=_wa_sender(session), send_email=email)
    return out, session, email


def _by_appt(out):
    ledger = {e["appointment_id"]: e for e in out["ledger"]}
    assert len(ledger) == len(out["ledger"]), "an appointment was ledgered twice"
    return ledger


# --- phone normalisation ---------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("91234567", "6591234567"),
    ("81234567", "6581234567"),
    ("9123 4567", "6591234567"),
    ("9123-4567", "6591234567"),
    ("+65 9123 4567", "6591234567"),
    ("+6591234567", "6591234567"),
    ("6591234567", "6591234567"),
    ("(65) 9123-4567", "6591234567"),
    ("0065 9123 4567", "6591234567"),
    ("  91234567  ", "6591234567"),
    # already international: kept
    ("+44 7700 900123", "447700900123"),
    ("0044 7700 900123", "447700900123"),
    ("+60 12-345 6789", "60123456789"),
    ("60123456789", "60123456789"),
])
def test_normalise_phone_usable(raw, expected):
    assert wa.normalise_phone(raw) == expected


@pytest.mark.parametrize("raw", [
    None, "", "   ", "-", "n/a",
    "61234567",          # SG landline
    "+65 6123 4567",     # SG landline with country code
    "31234567",          # SG VoIP
    "9123456",           # 7 digits
    "912345678",         # 9 digits, no country code
    "659123456",         # 65 + 7 digits
    "9123 4567 / 8123 4567",   # two numbers in one field
    "+1234",
])
def test_normalise_phone_unusable(raw):
    assert wa.normalise_phone(raw) is None


# --- template params -------------------------------------------------------

def test_slot_format_matches_the_template_example():
    assert wa.fmt_slot("2026-11-26", "10:00") == "Thu 26 Nov, 10:00am"
    assert wa.fmt_slot("2026-11-26", "14:30") == "Thu 26 Nov, 2:30pm"
    assert wa.fmt_slot("2026-11-26", "12:00") == "Thu 26 Nov, 12:00pm"
    assert wa.fmt_slot("2026-11-26", "00:15") == "Thu 26 Nov, 12:15am"
    assert wa.fmt_slot("2026-12-01", "09:05") == "Tue 1 Dec, 9:05am"
    # No time -> date only, never a dangling comma.
    assert wa.fmt_slot("2026-11-26", None) == "Thu 26 Nov"


def test_whatsapp_times_are_wall_clock_not_shifted():
    """REGRESSION GUARD, same trap as the email: the view's appt_time_sgt is the
    clinic wall clock (start_at formatted at 'UTC'). A 9am session is '9:00am',
    not 5:00pm (+8h) or 1:00am (-8h)."""
    params = wa.template_params(_appt("a1", time="09:00"), DAY)
    assert params[2] == "Thu 26 Nov, 9:00am"


def test_template_params_in_order():
    assert wa.template_params(_appt("a1"), DAY) == [
        "Sarah", "physiotherapy", "Thu 26 Nov, 10:00am", "Cheryl"]


def test_service_and_clinician_fallbacks():
    assert wa.service_word("Pilates") == "Pilates"
    assert wa.service_word("S&C") == "strength and conditioning"
    assert wa.service_word("Home Visit") == "home visit"
    # Untyped/Unknown never guess a service.
    assert wa.service_word("Untyped") == "upcoming"
    assert wa.service_word(None) == "upcoming"
    assert wa.clinician_first_name("PKN") == "Kristy"
    assert wa.clinician_first_name(None) == "our team"
    assert wa.clinician_first_name("XYZ") == "our team"
    # Never "Hi ,".
    assert wa.template_params(_appt("a1", name=None), DAY)[0] == "there"


def test_every_booking_clinician_has_a_first_name():
    """booking/config.py is where a new clinician is added. If their doctor code
    isn't mapped here, their patients' reminders say 'with our team'."""
    import pathlib, re
    cfg = pathlib.Path(__file__).parent.parent / "booking" / "config.py"
    codes = set(re.findall(r'"doctor":\s*"([A-Z]+)"', cfg.read_text()))
    assert codes, "couldn't read doctor codes from booking/config.py"
    assert codes <= set(wa.CLINICIAN_FIRST_NAMES), codes - set(wa.CLINICIAN_FIRST_NAMES)


def test_every_treatment_type_has_a_service_word():
    """stg/03_appointments.sql maps Plato type codes to treatment_type. A new
    type there should get a word here rather than fall to 'upcoming'."""
    import pathlib, re
    sql = pathlib.Path(__file__).parent.parent / "sql" / "stg" / "03_appointments.sql"
    text = sql.read_text()
    case = text[text.index("CASE COALESCE(JSON_VALUE(payload, '$.code_Bottom')"):
                text.index("AS treatment_type")]
    types = set(re.findall(r"WHEN '[^']*'\s+THEN '([^']+)'", case))
    types -= {"Untyped", "Unknown"}
    assert types and types <= set(wa.SERVICE_WORDS), types - set(wa.SERVICE_WORDS)


def test_preview_renders_the_approved_wording():
    assert wa.render_preview(["Sarah", "physiotherapy", "Thu 26 Nov, 10:00am",
                              "Cheryl"]) == (
        "Hi Sarah, a reminder of your physiotherapy appointment on Thu 26 Nov, "
        "10:00am with Cheryl at Goji Women's and Family Physiotherapy.\n\n"
        "If you need to reschedule, please let us know at least 24 hours before.")


# --- Cloud API payload + send ----------------------------------------------

def test_payload_shape():
    assert wa.build_payload("6591234567", ["Sarah", "physiotherapy",
                                           "Thu 26 Nov, 10:00am", "Cheryl"],
                            "appt123") == {
        "messaging_product": "whatsapp",
        "to": "6591234567",
        "type": "template",
        "template": {
            "name": "goji_appointment_reminder",
            "language": {"code": "en"},
            "components": [
                {"type": "body", "parameters": [
                    {"type": "text", "text": "Sarah"},
                    {"type": "text", "text": "physiotherapy"},
                    {"type": "text", "text": "Thu 26 Nov, 10:00am"},
                    {"type": "text", "text": "Cheryl"},
                ]},
                {"type": "button", "sub_type": "quick_reply", "index": "0",
                 "parameters": [{"type": "payload",
                                 "payload": "reminder_confirm:appt123"}]},
                {"type": "button", "sub_type": "quick_reply", "index": "1",
                 "parameters": [{"type": "payload",
                                 "payload": "reminder_reschedule:appt123"}]},
            ],
        },
    }


def test_send_posts_to_the_cloud_api(monkeypatch):
    monkeypatch.setattr(wa, "WA_API_BASE", "https://graph.facebook.com/v23.0/")
    monkeypatch.setattr(wa, "WA_PHONE_NUMBER_ID", "1234567890")
    monkeypatch.setattr(wa, "WA_TOKEN", "tok")
    s = FakeSession()
    msg_id = wa.send_template("6591234567", ["a", "b", "c", "d"], "appt1", session=s)
    assert msg_id == "wamid.1"
    assert s.calls[0]["url"] == "https://graph.facebook.com/v23.0/1234567890/messages"
    assert s.calls[0]["headers"]["Authorization"] == "Bearer tok"
    assert s.calls[0]["json"]["to"] == "6591234567"


def test_send_through_a_provider_transport(monkeypatch):
    """A 360dialog-style provider: its own base, /messages, a raw key header."""
    monkeypatch.setattr(wa, "WA_API_BASE", "https://waba-v2.360dialog.io")
    monkeypatch.setattr(wa, "WA_SEND_PATH", "/messages")
    monkeypatch.setattr(wa, "WA_AUTH_HEADER", "D360-API-KEY")
    monkeypatch.setattr(wa, "WA_AUTH_PREFIX", "")
    monkeypatch.setattr(wa, "WA_PHONE_NUMBER_ID", "")
    monkeypatch.setattr(wa, "WA_TOKEN", "key")
    s = FakeSession()
    wa.send_template("6591234567", ["a", "b", "c", "d"], "appt1", session=s)
    assert s.calls[0]["url"] == "https://waba-v2.360dialog.io/messages"
    assert s.calls[0]["headers"]["D360-API-KEY"] == "key"
    assert "Authorization" not in s.calls[0]["headers"]
    assert not wa.needs_phone_number_id()


def test_provider_transport_needs_no_phone_number_id(monkeypatch):
    monkeypatch.setattr(wa, "WA_SEND_PATH", "/messages")
    monkeypatch.setattr(wa, "WA_TOKEN", "key")
    monkeypatch.setattr(wa, "WA_PHONE_NUMBER_ID", "")
    monkeypatch.setattr(wa, "OVERRIDE_TO", "")
    monkeypatch.setattr(mailer, "OVERRIDE_TO", "")
    ok, notes, _ = main.whatsapp_config(True, dry_run=False)
    assert ok, notes
    monkeypatch.setattr(wa, "WA_SEND_PATH", "/{phone_number_id}/messages")
    ok, notes, _ = main.whatsapp_config(True, dry_run=False)
    assert not ok and "WA_PHONE_NUMBER_ID" in notes[0]


@pytest.mark.parametrize("response, fragment", [
    (FakeResponse(400, {"error": {"message": "Template name does not exist in the translation",
                                  "type": "OAuthException", "code": 132001,
                                  "fbtrace_id": "Ab"}}), "132001"),
    (FakeResponse(401, {"error": {"message": "Invalid OAuth access token", "code": 190}}),
     "HTTP 401"),
    (FakeResponse(500, None, text="<html>oops</html>"), "HTTP 500"),
    (FakeResponse(200, {"error": {"message": "weird", "code": 1}}), "weird"),
    (FakeResponse(200, {"messaging_product": "whatsapp", "messages": []}), "no message id"),
    (FakeResponse(200, None, text="not json"), "not JSON"),
])
def test_send_raises_on_any_refusal(response, fragment):
    with pytest.raises(wa.WhatsAppSendError, match=fragment):
        wa.send_template("6591234567", ["a", "b", "c", "d"], "appt1",
                         session=FakeSession(response))


def test_send_raises_on_network_error():
    import requests
    s = FakeSession(requests.ConnectionError("boom"))
    with pytest.raises(wa.WhatsAppSendError, match="network error"):
        wa.send_template("6591234567", ["a", "b", "c", "d"], "appt1", session=s)


def test_whatsapp_override_replaces_the_recipient_at_send(monkeypatch):
    monkeypatch.setattr(wa, "OVERRIDE_TO", "6588887777")
    s = FakeSession()
    wa.send_template("6591234567", ["a", "b", "c", "d"], "appt1", session=s)
    assert s.sent_to() == ["6588887777"]


# --- channel choice --------------------------------------------------------

def test_usable_mobile_and_email_get_both_channels():
    """Clinic decision (25 Nov 2026): the email goes out anyway, in parallel
    with WhatsApp."""
    out, http, email = _run([_appt("a1")])
    assert http.sent_to() == ["6591234567"]
    assert [g["email"] for g in email.groups] == ["sarah@example.com"]
    e = _by_appt(out)["a1"]
    assert (e["status"], e["channel"], e["wa_message_id"]) == ("sent", "both", "wamid.1")
    assert sorted(x["channel"] for x in out["sent"]) == ["email", "whatsapp"]


def test_confirmed_with_email_gets_the_email_but_no_whatsapp():
    """The template's first button asks them to confirm; they already have."""
    out, http, email = _run([{**_appt("a1"), "confirmed": True}])
    assert http.calls == []
    assert len(email.groups) == 1 and email.groups[0]["confirmed"] is True
    assert email.groups[0]["confirm"] == []
    assert (_by_appt(out)["a1"]["channel"]) == "email"


def test_confirmed_without_email_still_gets_whatsapp():
    out, http, email = _run([{**_appt("a1", email=""), "confirmed": True}])
    assert http.sent_to() == ["6591234567"] and email.groups == []
    assert out["skipped"] == []
    assert _by_appt(out)["a1"]["channel"] == "whatsapp"


def test_no_usable_mobile_falls_to_email():
    out, http, email = _run([_appt("a1", phone="61234567")])   # landline
    assert http.calls == []
    assert [g["email"] for g in email.groups] == ["sarah@example.com"]
    e = _by_appt(out)["a1"]
    assert (e["status"], e["channel"], e["wa_message_id"]) == ("sent", "email", None)


def test_one_whatsapp_per_appointment_in_time_order():
    """A template carries one appointment, so two sessions = two messages,
    earliest first, even if the query returned them out of order. The email
    lists both."""
    out, http, email = _run([_appt("pm", time="14:00"), _appt("am", time="09:00")])
    assert http.appointment_ids() == ["am", "pm"]
    slots = [c["json"]["template"]["components"][0]["parameters"][2]["text"]
             for c in http.calls]
    assert slots == ["Thu 26 Nov, 9:00am", "Thu 26 Nov, 2:00pm"]
    assert len(email.groups) == 1 and email.groups[0]["times"] == ["09:00", "14:00"]


def test_whatsapp_failure_is_noted_and_the_email_still_counts():
    fail = FakeResponse(400, {"error": {"message": "Invalid parameter", "code": 100}})
    out, http, email = _run(
        [_appt("am", time="09:00"), _appt("pm", time="14:00")],
        session=FakeSession(fail))      # first send fails, second succeeds
    assert http.appointment_ids() == ["am", "pm"]
    assert len(email.groups) == 1 and email.groups[0]["appointment_ids"] == ["am", "pm"]
    ledger = _by_appt(out)
    assert (ledger["am"]["status"], ledger["am"]["channel"]) == ("sent", "email")
    assert "whatsapp failed" in ledger["am"]["note"]
    assert (ledger["pm"]["status"], ledger["pm"]["channel"]) == ("sent", "both")


def test_email_failure_is_noted_when_whatsapp_got_through():
    out, _, _ = _run([_appt("a1")], email=EmailSpy(fail_for={"sarah@example.com"}))
    e = _by_appt(out)["a1"]
    assert (e["status"], e["channel"]) == ("sent", "whatsapp")
    assert "email failed" in e["note"]


def test_whatsapp_failure_with_no_email_goes_on_the_by_hand_list():
    fail = FakeResponse(500, None, text="down")
    out, _, email = _run([_appt("a1", email="")], session=FakeSession(fail))
    assert email.groups == []
    assert len(out["skipped"]) == 1
    assert "WhatsApp failed" in out["skipped"][0]["reason"]
    e = _by_appt(out)["a1"]
    # 'failed', not skipped: a same-day re-run tries again.
    assert (e["status"], e["channel"]) == ("failed", "whatsapp")


def test_neither_phone_nor_email_is_skipped_no_contact():
    out, http, email = _run([_appt("a1", phone="", email="")])
    assert http.calls == [] and email.groups == []
    assert out["skipped"] == [{"name": "Sarah Tan", "phone": "", "time": "10:00"}]
    e = _by_appt(out)["a1"]
    assert (e["status"], e["channel"]) == ("skipped_no_contact", "none")


def test_email_failure_after_whatsapp_failure_keeps_both_errors():
    fail = FakeResponse(400, {"error": {"message": "bad", "code": 100}})
    out, _, _ = _run([_appt("a1")], session=FakeSession(fail),
                     email=EmailSpy(fail_for={"sarah@example.com"}))
    e = _by_appt(out)["a1"]
    assert (e["status"], e["channel"]) == ("failed", "email")
    assert "whatsapp failed" in e["note"] and "SMTP timeout" in e["note"]
    assert len(out["failed"]) == 1


def test_mixed_day_ledgers_every_appointment_exactly_once():
    fail = FakeResponse(400, {"error": {"message": "bad", "code": 100}})
    rows = [
        _appt("wa1", time="08:00"),
        _appt("wafail", time="09:00", email="jo@example.com", name="Jo Lee"),
        _appt("email1", time="10:00", phone="", email="amy@example.com", name="Amy"),
        _appt("none1", time="11:00", phone="", email="", name="Bo"),
        _appt("wa2", time="12:00", phone="+44 7700 900123", name="Cy", email=""),
    ]
    sess = FakeSession(FakeResponse(200, {"messages": [{"id": "wamid.A"}]}), fail)
    out, http, email = _run(rows, session=sess)
    ledger = _by_appt(out)
    assert set(ledger) == {"wa1", "wafail", "email1", "none1", "wa2"}
    assert {k: v["channel"] for k, v in ledger.items()} == {
        "wa1": "both", "wafail": "email", "email1": "email",
        "none1": "none", "wa2": "whatsapp"}
    assert sorted(g["email"] for g in email.groups) == [
        "amy@example.com", "jo@example.com", "sarah@example.com"]


# --- DRY_RUN ---------------------------------------------------------------

def test_dry_run_sends_nothing_on_either_channel():
    out, http, email = _run(
        [_appt("a1"), _appt("a2", phone="", email="amy@example.com", time="11:00")],
        dry_run=True)
    assert http.calls == []
    assert email.groups == []
    ledger = _by_appt(out)
    assert {(e["status"], e["channel"]) for e in ledger.values()} == {
        ("dry_run", "both"), ("dry_run", "email")}
    # The template is still rendered, for the digest.
    assert out["preview"].startswith("Hi Sarah, a reminder of your physiotherapy")
    assert "Thu 26 Nov, 10:00am with Cheryl" in out["preview"]


# --- disabled flag = today's job, exactly ----------------------------------

def test_disabled_never_touches_whatsapp_and_groups_email_as_before():
    rows = [_appt("a1", time="09:00"), _appt("a2", time="14:00"),
            _appt("a3", time="11:00", email="", name="Marcus Lim")]
    out, http, email = _run(rows, wa_enabled=False)
    assert http.calls == []
    # Same grouping as before: one email listing both sessions.
    assert len(email.groups) == 1
    assert email.groups[0]["times"] == ["09:00", "14:00"]
    ledger = _by_appt(out)
    assert {k: (v["status"], v["channel"]) for k, v in ledger.items()} == {
        "a1": ("sent", "email"), "a2": ("sent", "email"),
        "a3": ("skipped_no_email", "none")}
    assert out["preview"] is None


def test_disabled_digest_is_byte_identical_to_the_email_only_digest():
    """Pinned from the digest as it was before the WhatsApp channel existed."""
    body = mailer.render_digest_body(
        sent=[{"name": "Sarah Tan", "time": "09:00", "email": "s@x.com", "channel": "email"},
              {"name": "Jo Lee", "time": "14:30", "email": "j@x.com", "channel": "email"}],
        skipped=[{"name": "Marcus Lim", "phone": "91112222", "time": "11:00"},
                 {"name": None, "phone": None, "time": "08:00"}],
        failed=[{"name": "Ann Ho", "time": "10:00", "error": "SMTP timeout"}],
        target_date=DAY, dry_run=False)
    assert body == (
        "Appointment reminders for Thursday, 26 November 2026\n\nSent: 2 reminder(s)"
        "\n\nCouldn't reach — no email on file (2). Please WhatsApp these:\n"
        "    8:00 am  —  no phone either\n   11:00 am  Marcus Lim  91112222\n\n"
        "Failed to send (1) — will retry next run:\n  Ann Ho: SMTP timeout\n\n"
        "Sent to:\n    9:00 am  Sarah Tan\n    2:30 pm  Jo Lee\n\n"
        "— the appointment-reminders job")
    dry = mailer.render_digest_body(
        sent=[{"name": "Sarah Tan", "time": "09:00"}], skipped=[], failed=[],
        target_date=DAY, dry_run=True)
    assert dry == (
        "DRY RUN — no patient emails were sent.\n\nAppointment reminders for "
        "Thursday, 26 November 2026\n\nWould have sent: 1 reminder(s)\n\n"
        "Would have sent to:\n    9:00 am  Sarah Tan\n\n— the appointment-reminders job")


def test_whatsapp_config_off_by_default_and_safe(monkeypatch):
    monkeypatch.setattr(wa, "WA_TOKEN", "tok")
    monkeypatch.setattr(wa, "WA_PHONE_NUMBER_ID", "123")
    monkeypatch.setattr(wa, "OVERRIDE_TO", "")
    monkeypatch.setattr(wa, "OVERRIDE_TO_RAW", "")
    monkeypatch.setattr(mailer, "OVERRIDE_TO", "")
    assert main.whatsapp_config(False, dry_run=False) == (False, [], None)
    assert main.whatsapp_config(True, dry_run=False) == (True, [], None)

    # Missing credentials: WhatsApp off for the run, said in the digest.
    monkeypatch.setattr(wa, "WA_TOKEN", "")
    on, notices, err = main.whatsapp_config(True, dry_run=False)
    assert not on and err is None and "WA_TOKEN" in notices[0]
    # ...but a dry run needs no credentials.
    assert main.whatsapp_config(True, dry_run=True)[0] is True
    monkeypatch.setattr(wa, "WA_TOKEN", "tok")

    # Email test mode without a WhatsApp override: WhatsApp skipped, so the
    # test can't message a patient.
    monkeypatch.setattr(mailer, "OVERRIDE_TO", "hello@gojiphysio.com")
    on, notices, err = main.whatsapp_config(True, dry_run=False)
    assert not on and err is None and "skipped" in notices[0]
    # Both overrides: WhatsApp on, aimed at the override number.
    monkeypatch.setattr(wa, "OVERRIDE_TO", "6588887777")
    monkeypatch.setattr(wa, "OVERRIDE_TO_RAW", "88887777")
    on, notices, err = main.whatsapp_config(True, dry_run=False)
    assert on and err is None and "+6588887777" in notices[0]
    # WhatsApp override alone would email patients for real: refused.
    monkeypatch.setattr(mailer, "OVERRIDE_TO", "")
    assert main.whatsapp_config(True, dry_run=False)[2]
    # An override that isn't a WhatsApp number: refused.
    monkeypatch.setattr(wa, "OVERRIDE_TO", "")
    monkeypatch.setattr(wa, "OVERRIDE_TO_RAW", "61234567")
    monkeypatch.setattr(mailer, "OVERRIDE_TO", "hello@gojiphysio.com")
    assert main.whatsapp_config(True, dry_run=False)[2]


# --- idempotency -----------------------------------------------------------

def test_guard_suppresses_sent_on_either_channel():
    """The SQL guard keys on status alone. If it ever filtered on channel too,
    switching channels would re-remind everyone."""
    where = main.RECIPIENTS_SQL.rsplit("WHERE", 1)[1]  # the guard, not a subquery
    assert "COALESCE(e.status, '') != 'sent'" in where
    assert "channel" not in where


def test_rerun_after_success_sends_nothing():
    """Simulate a Cloud Run retry: apply the guard to the first run's ledger and
    run again. Neither channel may send twice."""
    rows = [_appt("a1"), _appt("a2", phone="", email="amy@example.com", time="11:00"),
            _appt("a3", phone="", email="", time="12:00")]
    first, http1, email1 = _run(rows)
    assert len(http1.calls) == 1 and len(email1.groups) == 2
    latest = {e["appointment_id"]: e["status"] for e in first["ledger"]}
    remaining = [r for r in rows if latest.get(r["appointment_id"], "") != "sent"]
    second, http2, email2 = _run(remaining)
    assert http2.calls == [] and email2.groups == []
    assert [e["appointment_id"] for e in second["ledger"]] == ["a3"]


def test_ledger_insert_carries_channel_and_message_id():
    captured = {}

    class FakeJob:
        def result(self):
            return []

    class FakeBQ:
        def query(self, sql, job_config=None):
            captured["sql"] = sql
            captured["params"] = {p.name: p.value for p in job_config.query_parameters}
            return FakeJob()

    main.write_ledger(FakeBQ(), "goji-bi", "marts", [
        main.ledger_entry("a1", "sent", "whatsapp", wa_message_id="wamid.X"),
        main.ledger_entry("a2", "skipped_no_contact", "none"),
    ], DAY)
    assert "channel, wa_message_id, sent_at" in captured["sql"]
    p = captured["params"]
    assert (p["a0"], p["s0"], p["c0"], p["w0"]) == ("a1", "sent", "whatsapp", "wamid.X")
    assert (p["a1"], p["c1"], p["w1"]) == ("a2", "none", None)


def test_ledger_sql_has_the_channel_columns():
    """The INSERT names channel / wa_message_id; the table must have them, and
    an existing table only gets them through the ALTER (CREATE TABLE IF NOT
    EXISTS is a no-op once it exists)."""
    import pathlib
    sql = (pathlib.Path(__file__).parent.parent / "sql" / "marts"
           / "48_appointment_reminder_events.sql").read_text()
    assert "ADD COLUMN IF NOT EXISTS channel" in sql
    assert "ADD COLUMN IF NOT EXISTS wa_message_id" in sql


def test_ledger_notes_never_carry_a_phone_number():
    note = main.scrub("whatsapp failed: HTTP 400: (#131030) Recipient +65 9123 4567 "
                      "not in allowed list (6591234567)")
    assert "9123" not in note and "6591234567" not in note
    assert "[phone]" in note and "131030" in note


# --- two-channel digest ----------------------------------------------------

def test_two_channel_digest_shows_channel_per_patient_and_the_by_hand_list():
    body = mailer.render_digest_body(
        sent=[{"name": "Sarah Tan", "time": "09:00", "channel": "whatsapp",
               "detail": "physiotherapy with Cheryl, Thu 26 Nov, 9:00am"},
              {"name": "Jo Lee", "time": "10:00", "channel": "email",
               "detail": "(WhatsApp failed)"},
              {"name": "Amy", "time": "11:00", "channel": "email"}],
        skipped=[{"name": "Marcus Lim", "phone": "61234567", "time": "14:00"},
                 {"name": "Bo", "phone": "91112222", "time": "15:00",
                  "reason": "WhatsApp failed: HTTP 500"}],
        failed=[], target_date=DAY, dry_run=False, whatsapp=True)
    assert "Sent: 3 reminder(s) — 1 WhatsApp, 2 email" in body
    assert "Sarah Tan  [WhatsApp]  physiotherapy with Cheryl" in body
    assert "Jo Lee  [email]  (WhatsApp failed)" in body
    assert "Amy  [email]" in body
    assert "no WhatsApp and no email (2)" in body
    assert "Marcus Lim  61234567" in body
    assert "Bo  91112222  (WhatsApp failed: HTTP 500)" in body
    assert "contact these by hand" in body


def test_two_channel_dry_run_digest_previews_the_template():
    out, _, _ = _run([_appt("a1")], dry_run=True)
    body = mailer.render_digest_body(out["sent"], out["skipped"], out["failed"],
                                     DAY, dry_run=True, whatsapp=True,
                                     preview=out["preview"],
                                     notices=["Test mode: something"])
    assert body.startswith("DRY RUN — no patient messages were sent.")
    assert "Test mode: something" in body
    assert "Would have sent: 2 reminder(s) — 1 WhatsApp, 1 email" in body
    assert "  Hi Sarah, a reminder of your physiotherapy appointment" in body


# --- Plato's Confirm Appointment link ------------------------------------------

def test_confirm_url_matches_plato_and_the_booking_confirmation():
    # Copied from a real Plato reminder email (30 Oct 2026).
    assert mailer.confirm_url("5e8cd7cdcfb94ef586a66764e84b308d") == (
        "https://clinic.platomedical.com/appointment_confirm/Z29qaWhlYWx0aA==/"
        "5e8cd7cdcfb94ef586a66764e84b308d")


def test_one_session_gets_one_confirm_link():
    body = mailer.render_reminder_body(
        "Sarah", "2026-09-09", ["09:00"], has_clinic=True, has_home_visit=False,
        confirm_links=[("09:00", mailer.confirm_url("a1"))])
    assert "Please confirm you're coming:\n  https://clinic.platomedical.com/" in body


def test_several_sessions_get_a_link_each_by_time():
    body = mailer.render_reminder_body(
        "Sarah", "2026-09-09", ["09:00", "14:00"], has_clinic=True, has_home_visit=False,
        confirm_links=[("09:00", "https://x/a1"), ("14:00", "https://x/a2")])
    assert "  9:00 am: https://x/a1\n  2:00 pm: https://x/a2" in body


def test_no_confirm_links_keeps_the_old_body():
    kw = dict(has_clinic=True, has_home_visit=False)
    assert "confirm" not in mailer.render_reminder_body("Sarah", "2026-09-09", ["09:00"], **kw)


def test_group_carries_a_confirm_entry_per_appointment():
    groups, _ = main.group_by_recipient([
        {"appointment_id": "b", "email": "s@x.com", "name": "S", "time": "14:00"},
        {"appointment_id": "a", "email": "S@x.com", "name": "S", "time": "09:00"},
    ])
    assert groups[0]["confirm"] == [("09:00", "a"), ("14:00", "b")]


def test_maps_link_is_the_clinic_choice():
    assert mailer.MAPS_LINK == "https://maps.app.goo.gl/Mm3eYLNMUwwx8USv8"


def test_html_reminder_has_a_confirm_button_and_the_same_words():
    kw = dict(has_clinic=True, has_home_visit=False)
    url = mailer.confirm_url("a1")
    html = mailer.render_reminder_html("Sarah <b>", "2026-09-09", ["09:00"],
                                       confirm_links=[("09:00", url)], **kw)
    assert f'href="{url}"' in html and "Confirm I&#39;m coming" in html
    assert "<b>" not in html  # the name is escaped
    assert 'href="https://go.gojiphysio.com/reminder-wa"' in html
    assert "$50 fee" in html and "Lentor Modern" in html


def test_html_reminder_one_button_per_session():
    html = mailer.render_reminder_html(
        "Sarah", "2026-09-09", ["09:00", "14:00"], has_clinic=True, has_home_visit=False,
        confirm_links=[("09:00", "https://x/a1"), ("14:00", "https://x/a2")])
    assert "Confirm 9:00 am" in html and "Confirm 2:00 pm" in html


def test_confirmed_reminder_thanks_instead_of_asking():
    kw = dict(has_clinic=True, has_home_visit=False)
    body = mailer.render_reminder_body("Sarah", "2026-09-09", ["09:00"], confirmed=True, **kw)
    assert "Thank you for confirming" in body and "Please confirm" not in body
    html = mailer.render_reminder_html("Sarah", "2026-09-09", ["09:00"], confirmed=True, **kw)
    assert "Thank you for confirming" in html and "Confirm I&#39;m coming" not in html


def test_mixed_day_asks_only_for_the_unconfirmed_session():
    groups, _ = main.group_by_recipient([
        {**_row("a", "s@x.com", "09:00"), "confirmed": True},
        _row("b", "s@x.com", "14:00"),
    ])
    assert groups[0]["confirm"] == [("14:00", "b")] and groups[0]["confirmed"]


# --- registration form still owed -------------------------------------------------

import registration


class FakePlatoHTTP:
    def __init__(self, patient=None, fail=False):
        self.patient, self.fail, self.paths = patient or {}, fail, []

    def get(self, url, timeout=None, headers=None):
        self.paths.append(url.split("/gojihealth/")[1])
        fail, patient = self.fail, self.patient

        class R:
            def raise_for_status(self):
                if fail:
                    raise RuntimeError("boom")

            def json(self):
                if url.endswith("/prereg"):
                    return {"url": "https://clinic.platomedical.com/prereg/x"}
                if url.endswith("/updatelink"):
                    return {"url": "https://clinic.platomedical.com/secure/regupdate/x"}
                return [patient]
        return R()


def _plato(**kw):
    return registration.Plato(key="k", session=FakePlatoHTTP(**kw))


SIGNED = {"others": {"consents": [{"title": "Clinic Consent Form", "name": "consent.html",
                                    "created_on": 1793000000}]}}


def test_no_profile_gets_the_prereg_form():
    p = _plato()
    url = registration.form_link(p, {"appointment_id": "a1", "profile_id": None,
                                     "consent_signed": False})
    assert url.endswith("/prereg/x") and p.http.paths == ["appointment/a1/prereg"]


def test_unsigned_profile_gets_its_update_form():
    p = _plato(patient={"name": "Jo", "created_by": "api"})
    url = registration.form_link(p, {"appointment_id": "a1", "profile_id": "p1",
                                     "consent_signed": False})
    assert url.endswith("/regupdate/x")
    assert p.http.paths == ["patient/p1", "patient/p1/updatelink"]


def test_signed_last_night_means_no_read_and_no_form():
    p = _plato()
    assert registration.form_link(p, {"appointment_id": "a1", "profile_id": "p1",
                                      "consent_signed": True}) is None
    assert p.http.paths == []


def test_signed_since_last_night_is_caught_live():
    p = _plato(patient=SIGNED)
    assert registration.form_link(p, {"appointment_id": "a1", "profile_id": "p1",
                                      "consent_signed": False}) is None
    assert p.http.paths == ["patient/p1"]


@pytest.mark.parametrize("patient", [
    {}, {"others": {}}, {"others": {"consents": []}},
    {"others": {"consents": [{"title": "Another Form", "created_on": 1793000000}]}},
    {"others": {"consents": [{"title": "Clinic Consent Form", "created_on": 0}]}},
])
def test_anything_but_a_signed_clinic_consent_is_unsigned(patient):
    assert not registration.consent_signed(patient)


def test_plato_failure_means_no_form_line():
    assert registration.form_link(_plato(fail=True), {"appointment_id": "a1",
                                                      "consent_signed": False}) is None


def test_read_cap(monkeypatch):
    monkeypatch.setattr(registration, "MAX_READS", 1)
    p = _plato()
    row = {"appointment_id": "a1", "consent_signed": False}
    assert registration.form_link(p, row) and registration.form_link(p, row) is None


def test_consent_title_matches_the_nightly_import():
    src = open("../ingestion/plato_patients/main.py").read()
    assert f'CONSENT_TITLE = "{registration.CONSENT_TITLE}"' in src


def test_reminder_asks_for_the_form_in_text_and_html():
    kw = dict(has_clinic=True, has_home_visit=False, form_url="https://clinic.platomedical.com/prereg/x")
    body = mailer.render_reminder_body("Sarah", "2026-09-09", ["09:00"], **kw)
    assert "registration form yet" in body and "prereg/x" in body
    html = mailer.render_reminder_html("Sarah", "2026-09-09", ["09:00"],
                                       confirm_links=[("09:00", "https://x/c")], **kw)
    assert html.index("Confirm I&#39;m coming") < html.index(">Registration form</a>")
    assert html.count("prereg/x") == 1


def test_group_carries_the_form_link():
    groups, _ = main.group_by_recipient([
        {**_row("a", "s@x.com", "09:00"), "form_url": None},
        {**_row("b", "s@x.com", "14:00"), "form_url": "https://f"},
    ])
    assert groups[0]["form_url"] == "https://f"
