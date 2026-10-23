"""Test isolation: the tests pin July 2026 dates, so clear the live roster's
start dates (CLINICIAN_AVAILABLE_FROM) unless a test sets its own."""
import pytest

from booking import availability


@pytest.fixture(autouse=True)
def _no_clinician_start_dates(monkeypatch):
    monkeypatch.setattr(availability, "CLINICIAN_AVAILABLE_FROM", {})
