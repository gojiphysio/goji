"""Tests for the careers backend. All data is synthetic; nothing touches
Google, SMTP or the network (see fakes.py)."""
from __future__ import annotations

import io

import pytest

from careers import app as app_module
from careers import config, mailer, vacancies
from careers.fakes import DOCX, JPG, PDF, PNG, VACANCIES, FakeWorkspace
from careers.validation import FileRejected, check_cv, normalise_phone

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


def pilates_form(**over):
    """A complete Freelance Pilates Instructor application. Lists are sent as
    repeated fields, as the browser does."""
    f = {"role": "pilates-instructor", "full_name": "Test Instructor",
         "email": "pilates@example.com", "phone": "9123 4567",
         "work_eligibility": "Singapore Citizen or Permanent Resident",
         "certification": "Comprehensive certification, Example Pilates Academy",
         "apparatus": ["Mat", "Reformer", "Others"], "apparatus_other": "Spine corrector",
         "teaching_years": "3 to 5 years", "teaching_experience": ["Private 1:1", "Prenatal"],
         "available_days": ["Saturday", "Sunday"], "time_windows": ["Morning"],
         "start_date": "2027-01-04", "privacy_ack": "yes", "elapsed_ms": "20000"}
    f.update(over)
    return {k: v for k, v in f.items() if v is not None}


def post(client, data, cv=(PDF, "cv.pdf"), headers=None, certs=()):
    data = dict(data)
    if cv:
        data["cv"] = (io.BytesIO(cv[0]), cv[1])
    if certs:
        data["certificates"] = [(io.BytesIO(b), n) for b, n in certs]
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


# ---- phone numbers -----------------------------------------------------------------

@pytest.mark.parametrize("raw,stored", [
    ("91234567", "+65 9123 4567"),          # Singapore, no country code
    ("9123 4567", "+65 9123 4567"),
    ("6591234567", "+65 9123 4567"),
    ("+65 9123 4567", "+65 9123 4567"),
    ("+44 7911 123456", "+44 7911 123456"),  # overseas, kept as typed
    ("0447911123456", "0447911123456"),
    ("1234567", ""),                         # too short
    ("call me", ""),
])
def test_phone_numbers(raw, stored):
    assert normalise_phone(raw) == stored


def test_local_number_is_stored_with_plus_65(env):
    assert post(env["client"], form(phone="9123 4567")).status_code == 200
    assert col(env["ws"].rows[-1], "Mobile number") == "+65 9123 4567"



# ---- Freelance Pilates Instructor ------------------------------------------------

def test_pilates_application_is_stored_with_its_own_answers(env):
    r = post(env["client"], pilates_form(), certs=[(PDF, "stott.pdf"), (JPG, "reformer.jpg")])
    assert r.status_code == 200, r.json
    ref = r.json["reference"]
    [row] = env["ws"].rows
    assert len(row) == len(config.TRACKER_COLUMNS)
    assert col(row, "Role applied for") == "Freelance Pilates Instructor"
    assert col(row, "Employment preference") == "Freelance"
    assert col(row, "Apparatus qualifications") == "Mat, Reformer, Others: Spine corrector"
    assert col(row, "Relevant teaching experience") == "Private 1:1, Prenatal"
    assert col(row, "Preferred working days") == "Saturday, Sunday"
    assert col(row, "Preferred time windows") == "Morning"
    assert col(row, "Earliest available start date") == "2027-01-04"
    assert col(row, "Mobile number") == "+65 9123 4567"
    # No physiotherapist-only answers on a Pilates row.
    for c in ("AHPC registration status", "Actual years of clinical experience",
              "Days available per week", "Clinical experience"):
        assert col(row, c) == ""
    names = sorted(f["name"] for f in env["ws"].files.values())
    assert names == [f"{ref} - Test Instructor - CV.pdf",
                     f"{ref} - Test Instructor - Certificate 1.pdf",
                     f"{ref} - Test Instructor - Certificate 2.jpg"]
    assert col(row, "Pilates certificate links").count("https://drive.google.com/file/d/") == 2
    internal, confirm = env["sent"]
    assert internal["Subject"] == ("[Goji Careers] New application — Freelance Pilates "
                                   "Instructor — Test Instructor")
    body = internal.get_content()
    assert "Engagement: Freelance" in body and "AHPC" not in body
    assert body.count("Certificate: https://") == 2
    assert confirm["To"] == "pilates@example.com"
    assert "Freelance Pilates Instructor position" in confirm.get_content()


def test_pilates_needs_no_physio_answers_and_intro_is_optional(env):
    r = post(env["client"], pilates_form(intro=None))
    assert r.status_code == 200, r.json
    assert col(env["ws"].rows[0], "Pilates certificate links") == ""


def test_pilates_required_fields(env):
    r = post(env["client"], pilates_form(work_eligibility=None, certification="", apparatus=None,
                                         teaching_years="", teaching_experience=None,
                                         available_days=None, start_date="next week"))
    assert r.status_code == 400
    assert {"work_eligibility", "certification", "apparatus", "teaching_years",
            "teaching_experience", "available_days", "start_date"} <= set(r.json["fields"])
    assert "employment" not in r.json["fields"] and "intro" not in r.json["fields"]


def test_pilates_drops_values_not_on_the_lists(env):
    post(env["client"], pilates_form(apparatus=["Mat", "Trampoline"], time_windows=["Midnight"]))
    row = env["ws"].rows[0]
    assert col(row, "Apparatus qualifications") == "Mat"
    assert col(row, "Preferred time windows") == ""


@pytest.mark.parametrize("certs", [
    [(PDF, "cert.exe")],                        # wrong type
    [(b"not an image", "cert.png")],            # bad signature
    [(PNG, "a.png")] * 4,                       # too many
])
def test_bad_certificates_are_refused(env, certs):
    r = post(env["client"], pilates_form(), certs=certs)
    assert r.status_code == 400 and "certificates" in r.json["fields"]
    assert env["ws"].files == {}


def test_physio_roles_ignore_certificates_and_pilates_fields(env):
    r = post(env["client"], form(certification="Sneaky", work_eligibility="x"),
             certs=[(PDF, "c.pdf")])
    assert r.status_code == 200
    row = env["ws"].rows[0]
    assert col(row, "Pilates certification and training provider") == ""
    assert len(env["ws"].files) == 1


def test_physio_still_requires_its_questions(env):
    r = post(env["client"], form(ahpc_status=None, employment=None, start_availability=""))
    assert r.status_code == 400
    assert {"ahpc_status", "employment", "start_availability"} <= set(r.json["fields"])
