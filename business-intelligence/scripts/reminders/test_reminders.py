"""
Unit tests for the appointment-reminder job — pure functions only, no network,
no BigQuery. These gate the deploy in .github/workflows/deploy-dashboard.yml.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import main
import reminder_mailer as mailer

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

