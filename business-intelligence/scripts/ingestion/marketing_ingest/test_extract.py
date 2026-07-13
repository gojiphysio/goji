"""Unit tests for the marketing_ingest parsers. Pure — no network / no BQ."""
import pytest

from main import parse_reach


def test_parse_reach_takes_latest_datapoint():
    body = {"data": [{"name": "reach", "period": "days_28", "values": [
        {"value": 900, "end_time": "2026-07-10T07:00:00+0000"},
        {"value": 1234, "end_time": "2026-07-11T07:00:00+0000"},
    ]}]}
    assert parse_reach(body) == ("2026-07-11", 1234)


def test_parse_reach_single_datapoint():
    body = {"data": [{"name": "reach", "values": [
        {"value": 42, "end_time": "2026-07-11T07:00:00+0000"},
    ]}]}
    assert parse_reach(body) == ("2026-07-11", 42)


@pytest.mark.parametrize("body", [
    {},                              # no data key
    {"data": []},                    # empty data
    {"data": [{"values": []}]},      # empty series
    {"data": [{}]},                  # no values key
])
def test_parse_reach_rejects_bad_shapes(body):
    # The caller catches these and exits 3; here we just assert they raise.
    with pytest.raises((KeyError, IndexError, ValueError, TypeError)):
        parse_reach(body)
