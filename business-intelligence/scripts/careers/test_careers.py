"""Tests for the careers backend. All data is synthetic; nothing touches
Google, SMTP or the network (see fakes.py)."""
from __future__ import annotations

import io

import pytest

from careers import app as app_module
from careers import config, mailer, vacancies
from careers.fakes import DOCX, PDF, VACANCIES, FakeWorkspace
from careers.validation import FileRejected, check_cv

ORIGIN = "https://www.gojiphysio.com"


@pytest.fixture
def env(monkeypatch):
    ws = FakeWorkspace()
    sent = []
    monkeypatch.setattr(app_module, "_ws", ws)
    monkeypatch.setattr(vacancies, "_fetch", lambda: VACANCIES)
    monkeypatch.setattr(vacancies, "_cache", {"at": 0.0, "by_id": None})
    monkeypatch.setattr(mailer, "_send", sent.append)
    monkeypatch.setattr(config, "SMTP_PASS", "x")
    monkeypatch.setattr(config, "CORS_ORIGINS", [ORIGIN])
    monkeypatch.setattr(config, "TURNSTILE_SECRET", "")
    monkeypatch.setattr(config, "TEST_MODE", False)
    monkeypatch.setattr(config, "TEST_EMAIL", "")
    monkeypatch.setattr(config, "APPLICATIONS_FOLDER_ID", "FOLDER")
    monkeypatch.setattr(config, "TRACKER_SHEET_ID", "SHEET")
    return {"ws": ws, "sent": sent, "client": app_module.app.test_client()}


def form(**over):
    f = {"role": "physiotherapist", "full_name": "Test Applicant", "email": "test@example.com",
         "phone": "+65 9123 4567", "employment": "full-time", "years_experience": "3",
         "start_availability": "One month's notice", "intro": "Hello, I'm a physio.",
         "privacy_ack": "yes", "ahpc_status": "Fully registered",
         "clinical_experience": "MSK and sports", "elapsed_ms": "20000"}
    f.update(over)
    return {k: v for k, v in f.items() if v is not None}


def post(client, data, cv=(PDF, "cv.pdf"), headers=None):
    data = dict(data)
    if cv:
        data["cv"] = (io.BytesIO(cv[0]), cv[1])
    h = {"Origin": ORIGIN, "X-Goji-Careers": "1"} if headers is None else headers
    return client.post("/api/applications", data=data, headers=h,
                       content_type="multipart/form-data")


def col(row, name):
    return row[config.TRACKER_COLUMNS.index(name)]


# ---- the happy path -----------------------------------------------------------------

def test_application_is_stored_and_both_emails_sent(env):
    r = post(env["client"], form())
    assert r.status_code == 200, r.json
    ref = r.json["reference"]
    assert ref.startswith("GOJI-APP-") and ref.endswith("-0001")
    [row] = env["ws"].rows
    assert len(row) == len(config.TRACKER_COLUMNS)
    assert col(row, "Application ID") == ref
    assert col(row, "Role applied for") == "Physiotherapist"
    assert col(row, "Recruitment status") == "New"
    assert col(row, "CV link").startswith("https://drive.google.com/file/d/")
    [cv] = env["ws"].files.values()
    assert cv["name"] == f"{ref} - Test Applicant - CV.pdf"
    internal, confirm = env["sent"]
    assert internal["To"] == config.ADMIN_TO and ref in internal.get_content()
    assert confirm["To"] == "test@example.com"


def test_references_count_up(env):
    a = post(env["client"], form()).json["reference"]
    b = post(env["client"], form(email="other@example.com")).json["reference"]
    assert a.endswith("-0001") and b.endswith("-0002")


def test_expression_of_interest_skips_physio_questions(env):
    r = post(env["client"], form(role="general", interest_area="Clinic operations",
                                 ahpc_status=None, clinical_experience=None))
    assert r.status_code == 200, r.json
    row = env["ws"].rows[0]
    assert col(row, "Application type") == "Expression of interest"
    assert col(row, "Interest area (general)") == "Clinic operations"


def test_formula_text_is_stored_as_typed(env):
    post(env["client"], form(intro="=IMPORTXML(\"http://x\",\"//a\")"))
    assert col(env["ws"].rows[0], "Personal introduction").startswith("=IMPORTXML")


# ---- test mode --------------------------------------------------------------------------

def test_test_mode_sends_confirmation_to_test_address(env, monkeypatch):
    monkeypatch.setattr(config, "TEST_MODE", True)
    monkeypatch.setattr(config, "TEST_EMAIL", "tester@gojiphysio.com")
    post(env["client"], form())
    assert [m["To"] for m in env["sent"]] == [config.ADMIN_TO, "tester@gojiphysio.com"]


def test_test_mode_without_address_sends_no_confirmation(env, monkeypatch):
    monkeypatch.setattr(config, "TEST_MODE", True)
    post(env["client"], form())
    assert [m["To"] for m in env["sent"]] == [config.ADMIN_TO]


# ---- refusals ------------------------------------------------------------------------------

def test_missing_fields_are_reported(env):
    r = post(env["client"], form(full_name="", email="nope", intro=""), cv=None)
    assert r.status_code == 400
    assert {"full_name", "email", "intro", "cv"} <= set(r.json["fields"])
    assert env["ws"].rows == [] and env["sent"] == []


@pytest.mark.parametrize("data,name", [(PDF, "cv.exe"), (b"not a pdf", "cv.pdf"),
                                       (PDF, "cv.docx"), (b"", "cv.pdf")])
def test_bad_cv_is_refused(env, data, name):
    r = post(env["client"], form(), cv=(data, name))
    assert r.status_code == 400 and "cv" in r.json["fields"]


def test_cv_check():
    assert check_cv("CV.PDF", PDF) == "pdf"
    assert check_cv("cv.docx", DOCX) == "docx"
    with pytest.raises(FileRejected):
        check_cv("cv.pdf", b"%PDF" + b"x" * (config.MAX_CV_BYTES + 1))


def test_other_sites_are_refused(env):
    assert post(env["client"], form(), headers={"Origin": "https://evil.example",
                                                "X-Goji-Careers": "1"}).status_code == 403
    assert post(env["client"], form(), headers={"Origin": ORIGIN}).status_code == 403
    pre = env["client"].options("/api/applications", headers={"Origin": ORIGIN})
    assert pre.status_code == 204
    assert pre.headers["Access-Control-Allow-Origin"] == ORIGIN


@pytest.mark.parametrize("over", [{"company_url": "http://spam"}, {"elapsed_ms": "500"}])
def test_bot_checks(env, over):
    r = post(env["client"], form(**over))
    assert r.status_code == 400 and r.json["code"] == "bot_check"
    assert env["ws"].rows == []


def test_turnstile_is_required_when_configured(env, monkeypatch):
    monkeypatch.setattr(config, "TURNSTILE_SECRET", "secret")
    monkeypatch.setattr(app_module, "_turnstile_ok", lambda token: token == "good")
    assert post(env["client"], form()).json["code"] == "bot_check"
    assert post(env["client"], form(turnstile_token="bad")).json["code"] == "bot_check"
    assert post(env["client"], form(turnstile_token="good")).status_code == 200


def test_closed_and_unknown_roles(env):
    assert post(env["client"], form(role="old-role")).status_code == 409
    assert post(env["client"], form(role="astronaut")).status_code == 400


def test_storage_failure_sends_nothing(env):
    env["ws"].fail = {"append"}
    r = post(env["client"], form())
    assert r.status_code == 503 and r.json["code"] == "storage_failed"
    assert env["sent"] == []
