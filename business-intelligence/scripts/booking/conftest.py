"""Test isolation: the tests pin July 2026 dates, so clear the live roster's
start dates (CLINICIAN_AVAILABLE_FROM) unless a test sets its own."""
import pytest

from booking import availability


@pytest.fixture(autouse=True)
def _no_clinician_start_dates(monkeypatch):
    monkeypatch.setattr(availability, "CLINICIAN_AVAILABLE_FROM", {})


@pytest.fixture(autouse=True)
def _confirmations_off_unless_a_test_says(monkeypatch):
    """The deploy workflow exports the repo variables (CONFIRMATIONS_MODE=live
    since go-live, 26 Nov 2026), and the tests run in that job: a test that
    didn't set a mode would send for real and reach for BigQuery. Every test
    starts from "off"; tests that need a mode set it themselves."""
    for name in ("CONFIRMATIONS_MODE", "CONFIRMATIONS_SINCE", "CONFIRMATIONS_TEST_TO"):
        monkeypatch.delenv(name, raising=False)
