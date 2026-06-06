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
