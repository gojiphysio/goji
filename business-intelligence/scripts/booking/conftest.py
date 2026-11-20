"""Test isolation: the tests pin July 2026 dates, so clear the live roster's
start dates (CLINICIAN_AVAILABLE_FROM) unless a test sets its own. Likewise
clear CLINICIAN_WEEKLY_HOURS so the stub Plato rules drive the hours."""
import pytest

from booking import availability


@pytest.fixture(autouse=True)
def _no_clinician_start_dates(monkeypatch):
    monkeypatch.setattr(availability, "CLINICIAN_AVAILABLE_FROM", {})


@pytest.fixture(autouse=True)
def _no_weekly_hours_overrides(monkeypatch):
    monkeypatch.setattr(availability, "CLINICIAN_WEEKLY_HOURS", {})
