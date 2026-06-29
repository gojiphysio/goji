"""Unit tests for the pure extraction in instagram_insights/main.py.

The live fetch (Graph API auth, metric availability per API version) is verified
on first run against the real account; here we test the response-parsing — the
part that's deterministic and where the shape quirks bite.

Run from this dir:  python -m pytest test_extract.py -q
"""
from __future__ import annotations

import json

import main


LOADED = "2026-06-29T00:00:00+00:00"
WIN_END = "2026-06-29"


def test_time_series_shape():
    # profile_views as a day series → one row per value, dated by end_time.
    resp = {"data": [{
        "name": "profile_views", "period": "day",
        "values": [
            {"value": 12, "end_time": "2026-06-27T07:00:00+0000"},
            {"value": 9,  "end_time": "2026-06-28T07:00:00+0000"},
        ],
    }]}
    rows = main.insight_rows(resp, "IG123", "day", LOADED, WIN_END)
    assert len(rows) == 2
    assert rows[0]["metric"] == "profile_views"
    assert rows[0]["metric_date"] == "2026-06-27" and rows[0]["value"] == 12
    assert rows[1]["metric_date"] == "2026-06-28" and rows[1]["value"] == 9
    assert rows[0]["period"] == "day" and rows[0]["ig_user_id"] == "IG123"
    assert json.loads(rows[0]["payload"])["value"] == 12


def test_total_value_shape():
    # reach days_28 comes back as a single total_value, dated to the window end.
    resp = {"data": [{"name": "reach", "period": "days_28",
                      "total_value": {"value": 8421}}]}
    rows = main.insight_rows(resp, "IG123", "days_28", LOADED, WIN_END)
    assert len(rows) == 1
    assert rows[0]["metric"] == "reach" and rows[0]["value"] == 8421
    assert rows[0]["period"] == "days_28"
    assert rows[0]["metric_date"] == WIN_END     # no end_time → window end


def test_skips_non_numeric_and_empty():
    # A nested/dict value (some metrics) is skipped, not crashed; empty data → [].
    resp = {"data": [{"name": "reach", "period": "day",
                      "values": [{"value": {"nested": 1}, "end_time": "2026-06-28T07:00:00+0000"},
                                 {"value": 5, "end_time": "2026-06-28T07:00:00+0000"}]}]}
    rows = main.insight_rows(resp, "IG123", "day", LOADED, WIN_END)
    assert len(rows) == 1 and rows[0]["value"] == 5
    assert main.insight_rows({}, "IG123", "day", LOADED, WIN_END) == []
    assert main.insight_rows({"data": []}, "IG123", "day", LOADED, WIN_END) == []


def test_metric_date_fallback_on_bad_end_time():
    assert main._metric_date(None, WIN_END) == WIN_END
    assert main._metric_date("garbage", WIN_END) == WIN_END
    assert main._metric_date("2026-06-28T07:00:00+0000", WIN_END) == "2026-06-28"
