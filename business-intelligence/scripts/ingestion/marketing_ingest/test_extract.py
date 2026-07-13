"""Unit tests for the marketing_ingest parsers. Pure — no network / no BQ."""
import pytest

from main import parse_followers, parse_insight_latest, parse_reach


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


def test_parse_reach_is_alias_for_insight_latest():
    # profile_views reuses the same insight-series shape as reach.
    body = {"data": [{"name": "profile_views", "period": "day", "values": [
        {"value": 12, "end_time": "2026-07-10T07:00:00+0000"},
        {"value": 27, "end_time": "2026-07-11T07:00:00+0000"},
    ]}]}
    assert parse_insight_latest(body) == ("2026-07-11", 27)
    assert parse_reach is parse_insight_latest


def test_parse_followers_uses_caller_date():
    # followers_count is a field, not a time series, so the caller supplies the date.
    body = {"followers_count": 1523, "id": "17841400000000000"}
    assert parse_followers(body, "2026-07-13") == ("2026-07-13", 1523)


@pytest.mark.parametrize("body", [
    {},                       # no followers_count key
    {"id": "1784"},           # missing followers_count
    {"followers_count": None},  # null value
])
def test_parse_followers_rejects_bad_shapes(body):
    with pytest.raises((KeyError, ValueError, TypeError)):
        parse_followers(body, "2026-07-13")
