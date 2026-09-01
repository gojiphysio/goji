"""Unit tests for the marketing_ingest parsers. Pure — no network / no BQ."""
import pytest

from main import (parse_followers, parse_insight_latest, parse_reach,
                  parse_search_analytics)


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


# --- Search Console -------------------------------------------------------

def test_parse_search_analytics_totals():
    """date-only dimension: keys[0] is the date, dimension_value stays empty."""
    body = {"rows": [
        {"keys": ["2026-08-30"], "clicks": 12, "impressions": 340,
         "ctr": 0.0353, "position": 8.4},
        {"keys": ["2026-08-31"], "clicks": 9, "impressions": 288,
         "ctr": 0.03125, "position": 9.1},
    ]}
    rows = parse_search_analytics(body, "total")
    assert [r["metric_date"] for r in rows] == ["2026-08-30", "2026-08-31"]
    assert rows[0] == {"metric_date": "2026-08-30", "dimension": "total",
                       "dimension_value": "", "clicks": 12, "impressions": 340,
                       "ctr": 0.0353, "position": 8.4}


def test_parse_search_analytics_query_dimension():
    """date+query: keys[1] becomes dimension_value."""
    body = {"rows": [
        {"keys": ["2026-08-30", "pelvic floor physiotherapy singapore"],
         "clicks": 3, "impressions": 40, "ctr": 0.075, "position": 6.2},
    ]}
    rows = parse_search_analytics(body, "query")
    assert rows[0]["dimension"] == "query"
    assert rows[0]["dimension_value"] == "pelvic floor physiotherapy singapore"
    assert rows[0]["position"] == 6.2


def test_parse_search_analytics_empty_is_not_an_error():
    """A day with no impressions returns no rows — normal, not a failure."""
    assert parse_search_analytics({}, "total") == []
    assert parse_search_analytics({"rows": []}, "total") == []
    assert parse_search_analytics({"rows": None}, "total") == []


def test_parse_search_analytics_skips_rows_without_keys():
    body = {"rows": [{"clicks": 1, "impressions": 2}]}
    assert parse_search_analytics(body, "total") == []


def test_parse_search_analytics_defaults_missing_metrics_to_zero():
    """GSC omits zero-valued metrics; they must not become None in a REQUIRED column."""
    body = {"rows": [{"keys": ["2026-08-30", "physio near me"]}]}
    rows = parse_search_analytics(body, "query")
    assert rows[0]["clicks"] == 0 and rows[0]["impressions"] == 0
    assert rows[0]["ctr"] == 0.0 and rows[0]["position"] == 0.0
