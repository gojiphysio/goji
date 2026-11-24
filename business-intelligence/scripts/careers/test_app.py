"""/api/apply end to end against the in-memory store: origin, bot check,
validation, closed roles, file rejection, size cap, rate limits, and the
absence of any read/list endpoint."""
from __future__ import annotations

import io

import pytest

from careers import app as app_mod
from careers import config
from careers.conftest import form, pdf_bytes

ORIGIN = {"Origin": "https://www.gojiphysio.com", "X-Forwarded-For": "6.6.6.6, 1.2.3.4"}


@pytest.fixture
def client(store, sent, monkeypatch):
    monkeypatch.setattr(app_mod, "_hits", {})
    monkeypatch.setattr(app_mod, "store", lambda: store)
    monkeypatch.delenv("TURNSTILE_SECRET", raising=False)
    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        c.store, c.sent = store, sent
        yield c


def _post(c, cv=("Test CV.pdf", pdf_bytes(), "application/pdf"), headers=ORIGIN, **over):
    data = form(**over)
    if cv is not None:
        name, body, mime = cv
        data["cv"] = (io.BytesIO(body), name, mime)
    return c.post("/api/apply", data=data, headers=headers,
                  content_type="multipart/form-data")


def test_success(client):
    r = _post(client)
    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "reference": "GOJI-APP-2026-0001"}
    assert r.headers["Access-Control-Allow-Origin"] == "https://www.gojiphysio.com"
    assert r.headers["Cache-Control"] == "no-store"


def test_response_never_echoes_applicant_data(client):
    r = _post(client, full_name="Echo Test", email="echo@example.com", intro="x")
    body = r.get_data(as_text=True)
    assert "Echo Test" not in body and "echo@example.com" not in body


def test_foreign_origin_refused(client):
    r = _post(client, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert "Access-Control-Allow-Origin" not in r.headers
    assert _post(client, headers={}).status_code == 403
    assert client.store.app_folders() == []


def test_missing_fields_return_field_errors(client):
    r = _post(client, full_name="", email="nope", cv=None)
    assert r.status_code == 400
    fields = r.get_json()["fields"]
    assert {"full_name", "email", "cv"} <= set(fields)


def test_unsupported_file_rejected(client):
    r = _post(client, cv=("cv.exe", b"MZ" + b"\x00" * 100, "application/octet-stream"))
    assert r.status_code == 400 and "cv" in r.get_json()["fields"]
    r = _post(client, cv=("cv.pdf", b"MZ" + b"\x00" * 100, "application/pdf"))
    assert r.status_code == 400 and "cv" in r.get_json()["fields"]
    assert client.store.app_folders() == []


def test_oversized_request_rejected(client):
    big = pdf_bytes() + b"0" * (config.MAX_REQUEST_BYTES + 10)
    r = _post(client, cv=("cv.pdf", big, "application/pdf"))
    assert r.status_code == 413 and r.get_json()["code"] == "too_large"


def test_closed_and_unknown_roles(client):
    r = _post(client, job_id="pilates-instructor")
    assert r.status_code == 410 and r.get_json()["code"] == "closed"
    r = _post(client, job_id="made-up-role")
    assert r.status_code == 400 and r.get_json()["code"] == "unknown_role"
    assert client.store.app_folders() == []


def test_vacancy_list_unavailable_is_retryable(client, monkeypatch):
    from careers import vacancies
    monkeypatch.setattr(vacancies, "all_vacancies", lambda: None)
    assert _post(client).status_code == 503
    # ...but an expression of interest still works.
    r = _post(client, job_id="general", role_category="other",
              ahpc_status=None, clinical_areas=None)
    assert r.status_code == 200


def test_honeypot_and_speed_checks(client):
    assert _post(client, company_url="http://spam").status_code == 400
    assert _post(client, elapsed_ms="900").get_json()["code"] == "bot_check"
    assert client.store.app_folders() == []


def test_turnstile_enforced_when_configured(client, monkeypatch):
    monkeypatch.setenv("TURNSTILE_SECRET", "s3cret")
    assert _post(client).get_json()["code"] == "bot_check"  # no token
    monkeypatch.setattr(app_mod, "_turnstile_ok", lambda token, ip: token == "good")
    assert _post(client, turnstile_token="bad").status_code == 400
    assert _post(client, turnstile_token="good").status_code == 200


def test_storage_failure_is_503_and_retry_safe(client):
    data = form()
    client.store.fail["append_row"] = 1
    r = _post(client, submission_id=data["submission_id"])
    assert r.status_code == 503 and r.get_json()["retry"] is True
    r = _post(client, submission_id=data["submission_id"])
    assert r.status_code == 200
    assert len(client.store.app_folders()) == 1 and len(client.store.rows_) == 2


def test_double_click_gives_same_reference(client):
    sid = form()["submission_id"]
    a = _post(client, submission_id=sid).get_json()
    b = _post(client, submission_id=sid).get_json()
    assert a == b and len(client.store.app_folders()) == 1 and len(client.sent) == 2


def test_per_email_daily_limit(client):
    for _ in range(config.APPLICATIONS_PER_EMAIL_DAY):
        assert _post(client).status_code == 200
    assert _post(client).status_code == 429


def test_per_ip_attempt_limit(client, monkeypatch):
    monkeypatch.setattr(config, "ATTEMPTS_PER_IP_HOUR", 2)
    _post(client, full_name="")
    _post(client, full_name="")
    assert _post(client).status_code == 429


def test_no_endpoint_reads_or_lists_applications(client):
    for path in ("/api/apply", "/api/applications", "/api/application/GOJI-APP-2026-0001",
                 "/applications"):
        r = client.get(path, headers=ORIGIN)
        assert r.status_code in (404, 405), path
