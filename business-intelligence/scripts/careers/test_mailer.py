"""Email content, header safety and test mode."""
from careers import config, mailer

ROLE = {"id": "senior-physiotherapist", "title": "Senior Physiotherapist"}
GENERAL = {"id": "general", "title": "General expression of interest"}
APP = {"full_name": "Jane Tan", "email": "jane@example.com", "employment": "Part-time",
       "years_experience": 6, "ahpc_status": "Fully registered",
       "start_availability": "1 March 2027", "also_consider": "Yes"}


def test_internal_message_matches_brief_and_has_no_attachment(monkeypatch):
    monkeypatch.setattr(config, "TRACKER_SHEET_ID", "SHEET")
    m = mailer.internal_message("GOJI-APP-2026-0007", ROLE, APP, "FOLDER")
    assert m["Subject"] == "[Goji Careers] New application — Senior Physiotherapist"
    body = m.get_content()
    for line in ("Application reference: GOJI-APP-2026-0007", "Candidate: Jane Tan",
                 "Role: Senior Physiotherapist", "Employment preference: Part-time",
                 "Years of experience: 6", "AHPC registration status: Fully registered",
                 "Earliest availability: 1 March 2027",
                 "View application: https://drive.google.com/drive/folders/FOLDER",
                 "View applicant tracker: https://docs.google.com/spreadsheets/d/SHEET/edit"):
        assert line in body
    assert not m.is_multipart()


def test_ack_uses_first_name_and_promises_no_timeline():
    m = mailer.ack_message("GOJI-APP-2026-0007", ROLE, APP)
    body = m.get_content()
    assert m["To"] == "jane@example.com"
    assert body.startswith("Hi Jane,")
    assert "Senior Physiotherapist position" in body
    for promise in ("within", "days", "week"):
        assert promise not in body.lower()


def test_general_ack_does_not_mention_a_vacancy():
    body = mailer.ack_message("R", GENERAL, APP).get_content()
    assert "position" not in body and "expression of interest" in body


def test_test_mode_redirects_and_fails_closed(monkeypatch):
    monkeypatch.setattr(config, "TEST_MODE", True)
    monkeypatch.setattr(config, "TEST_EMAIL", "")
    assert mailer.ack_message("R", ROLE, APP) is None          # no test inbox -> no email
    monkeypatch.setattr(config, "TEST_EMAIL", "hello+careers-test@gojiphysio.com")
    m = mailer.ack_message("R", ROLE, APP)
    assert m["To"] == "hello+careers-test@gojiphysio.com"


def test_name_cannot_inject_headers():
    app = dict(APP, full_name="Jane\r\nBcc: victim@example.com")
    m = mailer.internal_message("R", ROLE, app, "F")
    assert m["Bcc"] is None
    assert "Candidate: Jane Bcc: victim@example.com" in m.get_content()
