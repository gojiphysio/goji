"""Form validation: required fields, conditional fields, no auto-rejection."""
from __future__ import annotations

from werkzeug.datastructures import MultiDict

from careers.conftest import PHYSIO, form
from careers.validation import normalise_phone, parse_application
from careers.vacancies import GENERAL


def _parse(vacancy=PHYSIO, **over):
    f = form(**over)
    md = MultiDict()
    for k, v in f.items():
        for item in (v if isinstance(v, list) else [v]):
            md.add(k, item)
    return parse_application(md, vacancy)


def test_full_time_application_is_valid():
    app, errors = _parse()
    assert errors == {}
    assert app["role"] == "Physiotherapist / Senior Physiotherapist"
    assert app["days_per_week"] is None and app["is_physio"]
    assert app["clinical_areas"] == ["msk", "sports"]


def test_part_time_requires_days_per_week():
    _, errors = _parse(employment_pref="part_time")
    assert "days_per_week" in errors
    app, errors = _parse(employment_pref="part_time", days_per_week="4",
                         available_days=["mon", "wed", "sat"])
    assert errors == {} and app["days_per_week"] == 4
    assert app["available_days"] == ["mon", "wed", "sat"] and not app["below_min_days"]


def test_below_minimum_days_is_recorded_not_rejected():
    app, errors = _parse(employment_pref="either", days_per_week="2")
    assert errors == {}
    assert app["below_min_days"] is True


def test_missing_required_fields_each_get_a_message():
    _, errors = _parse(full_name="", email="", phone="", employment_pref="",
                       years_experience="", start_availability="", intro="",
                       ahpc_status="", clinical_areas=[], privacy_ack="")
    assert set(errors) >= {"full_name", "email", "phone", "employment_pref",
                           "years_experience", "start_availability", "intro",
                           "ahpc_status", "clinical_areas", "privacy_ack"}


def test_invalid_email():
    for bad in ("jane", "jane@", "jane@example", "jane..x@example.com", "a b@example.com"):
        _, errors = _parse(email=bad)
        assert "email" in errors, bad


def test_phone_needs_country_code():
    assert normalise_phone("+65 9123 4567") == "+65 9123 4567"
    assert normalise_phone("0065 9123 4567") == "+65 9123 4567"
    assert normalise_phone("+44 (0)7700 900123") == "+44 (0)7700 900123"
    assert normalise_phone("9123 4567") is None
    assert normalise_phone("+65 12") is None
    assert normalise_phone("+65 9123 4567\r\nBcc: x@y.z") is None


def test_unknown_option_values_are_rejected_or_dropped():
    _, errors = _parse(employment_pref="contract", years_experience="99", ahpc_status="maybe")
    assert {"employment_pref", "years_experience", "ahpc_status"} <= set(errors)
    app, _ = _parse(clinical_areas=["msk", "hacking"], certifications=["dry_needling", "x"])
    assert app["clinical_areas"] == ["msk"] and app["certifications"] == ["dry_needling"]


def test_submission_id_must_be_uuid4():
    _, errors = _parse(submission_id="not-a-uuid")
    assert "submission_id" in errors


def test_linkedin_must_be_a_linkedin_url():
    assert "linkedin" in _parse(linkedin="javascript:alert(1)")[1]
    assert "linkedin" in _parse(linkedin="https://evil.example/in/jane")[1]
    app, errors = _parse(linkedin="https://www.linkedin.com/in/jane-test/")
    assert "linkedin" not in errors and app["linkedin"].endswith("/jane-test/")


def test_expression_of_interest_needs_role_type_and_not_physio_fields():
    _, errors = _parse(GENERAL, job_id="general", ahpc_status=None, clinical_areas=None)
    assert "role_category" in errors and "ahpc_status" not in errors
    app, errors = _parse(GENERAL, job_id="general", role_category="operations",
                         role_interest="Clinic operations executive",
                         ahpc_status=None, clinical_areas=None)
    assert errors == {}
    assert app["application_type"] == "expression_of_interest"
    assert app["role"] == "Clinic operations: Clinic operations executive (expression of interest)"
    assert app["ahpc_status"] is None


def test_physio_expression_of_interest_asks_physio_questions():
    _, errors = _parse(GENERAL, job_id="general", role_category="physiotherapy",
                       ahpc_status=None, clinical_areas=None)
    assert {"ahpc_status", "clinical_areas"} <= set(errors)


def test_text_is_cleaned_and_capped():
    app, _ = _parse(full_name="  Test\r\nBcc: x@y.z  ", intro="x" * 5000)
    assert "\n" not in app["full_name"] and "\r" not in app["full_name"]
    assert len(app["intro"]) == 3000


def test_formula_like_text_is_kept_as_typed():
    # Stored verbatim; the Sheets write (valueInputOption=RAW) keeps it literal.
    app, errors = _parse(full_name='=HYPERLINK("http://x","y")')
    assert errors == {} and app["full_name"].startswith("=HYPERLINK")
