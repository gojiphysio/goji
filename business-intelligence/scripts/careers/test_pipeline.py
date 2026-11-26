"""The store-then-notify pipeline: exactly one of everything, safe retries,
partial-failure recovery, and email failures that never lose an application."""
from __future__ import annotations

import json
from datetime import date, datetime

import pytest
from werkzeug.datastructures import MultiDict

from careers import config, pipeline
from careers.conftest import PHYSIO, form, pdf_bytes
from careers.filecheck import check_cv
from careers.pipeline import StorageFailed, add_months, submit
from careers.validation import parse_application
from careers.vacancies import GENERAL

NOW = datetime(2026, 11, 24, 10, 30, tzinfo=config.SGT)


def _app(vacancy=PHYSIO, **over):
    md = MultiDict()
    for k, v in form(**over).items():
        for item in (v if isinstance(v, list) else [v]):
            md.add(k, item)
    app, errors = parse_application(md, vacancy)
    assert errors == {}
    return app


CV = check_cv("Test CV.pdf", "application/pdf", pdf_bytes())


def test_successful_application_produces_one_of_each(store, sent):
    ref = submit(store, _app(), CV, PHYSIO, now=NOW)
    assert ref == "GOJI-APP-2026-0001"
    folders = store.app_folders()
    assert len(folders) == 1 and folders[0]["name"] == ref
    # Folder is filed under Applications/2026/Physiotherapist, named by reference.
    role = store.files[folders[0]["parents"][0]]
    year = store.files[role["parents"][0]]
    assert (role["name"], year["name"], year["parents"]) == ("Physiotherapist", "2026", ["apps"])
    assert len(store.uploads("cv")) == 1 and len(store.uploads("summary")) == 1
    cv = store.uploads("cv")[0]
    assert cv["name"] == f"{ref}-CV.pdf" and "Test" not in cv["name"]
    assert len(store.rows_) == 2 and store.rows_[1][0] == ref
    assert [m["what"] for m in sent] == ["internal notification", "applicant acknowledgement"]
    assert sent[0]["to"] == "hello@gojiphysio.com"
    assert sent[1]["to"] == "test.applicant@example.com"
    assert store.files[folders[0]["id"]]["appProperties"]["notified"] == "1"


def test_tracker_row_matches_columns_and_starts_new(store, sent):
    submit(store, _app(employment_pref="part_time", days_per_week="2",
                       talent_pool="on", utm_source="linkedin", how_heard="linkedin"),
           CV, PHYSIO, now=NOW)
    row = dict(zip(pipeline.TRACKER_COLUMNS, store.rows_[1]))
    assert len(store.rows_[1]) == len(pipeline.TRACKER_COLUMNS)
    assert row["Recruitment status"] == "New"
    assert row["Days available per week"] == "2 (below the stated minimum)"
    assert row["Talent pool consent"] == "Yes"
    assert row["Retention review date"] == "2027-11-24"  # 12 months with talent pool
    assert row["Application source"] == "LinkedIn (utm: linkedin)"
    assert row["Privacy notice version"] == config.PRIVACY_NOTICE_VERSION
    for manual in ("Assigned reviewer", "Interview date", "Internal notes"):
        assert row[manual] == ""


def test_summary_json_is_stored_and_complete(store, sent):
    submit(store, _app(), CV, PHYSIO, now=NOW)
    s = json.loads(store.blobs[store.uploads("summary")[0]["id"]])
    assert s["reference"] == "GOJI-APP-2026-0001"
    assert s["cv"]["original_name"] == "Test CV.pdf"
    assert s["privacy"]["retention_review_date"] == "2027-05-24"  # 6 months
    assert s["answers"]["clinical_areas"] == ["msk", "sports"]


def test_duplicate_submit_is_idempotent(store, sent):
    app = _app()
    first = submit(store, app, CV, PHYSIO, now=NOW)
    second = submit(store, app, CV, PHYSIO, now=NOW)
    assert first == second
    assert len(store.app_folders()) == 1 and len(store.uploads("cv")) == 1
    assert len(store.rows_) == 2 and len(sent) == 2


def test_references_increment(store, sent):
    a = submit(store, _app(), CV, PHYSIO, now=NOW)
    b = submit(store, _app(email="second@example.com"), CV, PHYSIO, now=NOW)
    assert (a, b) == ("GOJI-APP-2026-0001", "GOJI-APP-2026-0002")


def test_sheets_failure_then_retry_completes_without_duplicates(store, sent):
    app = _app()
    store.fail["append_row"] = 1
    with pytest.raises(StorageFailed):
        submit(store, app, CV, PHYSIO, now=NOW)
    assert len(store.rows_) == 1 and sent == []  # not stored -> no emails
    assert len(store.app_folders()) == 1 and len(store.uploads("cv")) == 1
    ref = submit(store, app, CV, PHYSIO, now=NOW)
    assert ref == "GOJI-APP-2026-0001"
    assert len(store.app_folders()) == 1 and len(store.uploads("cv")) == 1
    assert len(store.rows_) == 2 and len(sent) == 2


def test_drive_upload_failure_then_retry(store, sent):
    app = _app()
    store.fail["upload"] = 1
    with pytest.raises(StorageFailed):
        submit(store, app, CV, PHYSIO, now=NOW)
    assert store.uploads("cv") == [] and len(store.rows_) == 1
    submit(store, app, CV, PHYSIO, now=NOW)
    assert len(store.app_folders()) == 1 and len(store.uploads("cv")) == 1


def test_drive_unreachable_before_folder(store, sent):
    store.fail["find_folder_by_property"] = 1
    with pytest.raises(StorageFailed):
        submit(store, _app(), CV, PHYSIO, now=NOW)
    assert store.app_folders() == []


def test_email_failure_keeps_application_and_never_resubmits(store, sent):
    sent.ok = False
    app = _app()
    ref = submit(store, app, CV, PHYSIO, now=NOW)
    folder = store.app_folders()[0]
    assert ref and len(store.rows_) == 2
    assert "notified" not in folder["appProperties"]
    # A later reconcile sends the missing emails exactly once.
    sent.ok = True
    actions = pipeline.reconcile(store)
    assert actions == [f"{ref}: send missing email(s)"]
    assert len(sent) == 2
    assert pipeline.reconcile(store) == []


def test_reconcile_adds_missing_tracker_row(store, sent):
    store.fail["append_row"] = 1
    with pytest.raises(StorageFailed):
        submit(store, _app(), CV, PHYSIO, now=NOW)
    assert pipeline.reconcile(store, dry_run=True) == [
        "GOJI-APP-2026-0001: add tracker row", "GOJI-APP-2026-0001: send missing email(s)"]
    assert len(store.rows_) == 1  # dry run changed nothing
    pipeline.reconcile(store)
    assert len(store.rows_) == 2 and len(sent) == 2


def test_expression_of_interest_is_filed_separately(store, sent):
    app = _app(GENERAL, job_id="general", role_category="pilates",
               ahpc_status=None, clinical_areas=None)
    ref = submit(store, app, CV, GENERAL, now=NOW)
    role = store.files[store.app_folders()[0]["parents"][0]]
    assert role["name"] == "General Expressions of Interest"
    assert sent[0]["subject"].startswith("[Goji Careers] New expression of interest")
    assert "expression of interest" in sent[1]["body"]
    assert "position" not in sent[1]["body"]  # doesn't imply an open vacancy
    assert ref in sent[1]["body"]


def test_internal_email_matches_brief(store, sent):
    submit(store, _app(), CV, PHYSIO, now=NOW)
    msg = sent[0]
    assert msg["subject"] == ("[Goji Careers] New application - "
                              "Physiotherapist / Senior Physiotherapist")
    body = msg["body"]
    for line in ("Application reference: GOJI-APP-2026-0001", "Candidate: Test Applicant",
                 "Employment preference: Full-time", "Years of experience: 3-5 years",
                 "AHPC registration status: Fully registered",
                 "Earliest availability: One month's notice",
                 "View application: https://drive.google.com/drive/folders/",
                 "View applicant tracker: https://docs.google.com/spreadsheets/d/sheet1"):
        assert line in body
    assert "@example.com" not in body  # candidate contact details stay in Drive


def test_applicant_email_matches_brief(store, sent):
    submit(store, _app(), CV, PHYSIO, now=NOW)
    msg = sent[1]
    assert msg["subject"] == "Thank you for your interest in Goji!"
    assert msg["body"].startswith("Hi Test,")
    assert ("We've received your application for the Physiotherapist / Senior "
            "Physiotherapist position") in msg["body"]
    assert "Cheers,\nThe Goji Team" in msg["body"]


def test_test_mode_redirects_acknowledgement(store, sent, monkeypatch):
    monkeypatch.setattr(config, "TEST_MODE", True)
    monkeypatch.setattr(config, "TEST_RECIPIENT", "qa@gojiphysio.com")
    submit(store, _app(), CV, PHYSIO, now=NOW)
    assert sent[1]["to"] == "qa@gojiphysio.com"


def test_test_mode_without_recipient_fails_closed(store, sent, monkeypatch):
    monkeypatch.setattr(config, "TEST_MODE", True)
    monkeypatch.setattr(config, "TEST_RECIPIENT", "")
    submit(store, _app(), CV, PHYSIO, now=NOW)
    assert [m["what"] for m in sent] == ["internal notification"]


def test_add_months_clamps_month_end():
    assert add_months(date(2026, 8, 31), 6) == date(2027, 2, 28)
    assert add_months(date(2026, 11, 24), 12) == date(2027, 11, 24)
