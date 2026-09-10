"""Unit tests for the PII contact extractors added to the patients ingest.

These feed marts.dim_patient_contact (full name + phone) for the staff Front
Desk dashboard. Run from this directory:  python -m pytest test_extract.py -q
"""
from __future__ import annotations

import pytest

import main


# --- full_name --------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Charles Wong", "Charles Wong"),
    ("  Charles   Wong  ", "Charles Wong"),   # collapses internal whitespace
    ("Madonna", "Madonna"),
    ("", None),
    ("   ", None),
    (None, None),
])
def test_full_name(raw, expected):
    assert main.full_name(raw) == expected


# --- extract_phone ----------------------------------------------------------

@pytest.mark.parametrize("record,expected", [
    ({"mobile": "+6591234567"}, "+6591234567"),
    ({"phone": "98765432"}, "98765432"),
    ({"handphone": " 8123 4567 "}, "8123 4567"),
    ({"contact": {"number": "+6590001111"}}, "+6590001111"),
    ({"tel": {"value": "62223333"}}, "62223333"),
    ({"name": "no phone here"}, None),
    ({}, None),
])
def test_extract_phone(record, expected):
    assert main.extract_phone(record) == expected


def test_mobile_preferred_over_other_keys():
    # _PHONE_KEYS order: mobile wins when several are present.
    rec = {"phone": "62223333", "mobile": "91112222"}
    assert main.extract_phone(rec) == "91112222"


# --- extract_email ----------------------------------------------------------
#
# Added for the appointment-reminder job: an appointment payload carries an
# address only when the front desk types one in (~4% of upcoming appointments),
# while the Plato profile has it for nearly everyone.

@pytest.mark.parametrize("record,expected", [
    ({"email": "sarah@example.com"}, "sarah@example.com"),
    ({"email": "  sarah@example.com  "}, "sarah@example.com"),
    ({"email_address": "a.b+tag@sub.example.co.uk"}, "a.b+tag@sub.example.co.uk"),
    ({"contact": {"address": "x@y.com"}}, None),      # 'contact' isn't an email key
    ({"mail": {"value": "x@y.com"}}, "x@y.com"),
    ({"name": "no email here"}, None),
    ({}, None),
])
def test_extract_email(record, expected):
    assert main.extract_email(record) == expected


@pytest.mark.parametrize("junk", [
    "", "   ", "-", "n/a", "none", "nil",
    "no-email", "sarah at example.com",
    "@example.com", "sarah@", "sarah@example",
    "sarah@.com", "sarah@example.",
    "one@two@three.com", "sarah @example.com",
])
def test_junk_is_not_treated_as_an_email(junk):
    """A stray '-' or 'n/a' in Plato's email field would otherwise become a hard
    SMTP bounce on every single daily reminder run."""
    assert main.extract_email({"email": junk}) is None


def test_email_key_order():
    # _EMAIL_KEYS order: the plain 'email' field wins when several are present.
    rec = {"mail": "old@example.com", "email": "current@example.com"}
    assert main.extract_email(rec) == "current@example.com"


def test_contact_row_carries_email_but_dimension_does_not():
    """PII boundary: dim_patient_contact holds contact details; dim_patient
    stays PII-free. Email must never leak into the analytics dimension."""
    import inspect
    src = inspect.getsource(main)
    # The dimension's schema block must not gain an email field.
    dim_schema = src.split('bigquery.SchemaField("sex",')[0]
    assert 'SchemaField("email"' not in dim_schema
