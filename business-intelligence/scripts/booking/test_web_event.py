"""Unit tests for the landing-beacon row builder (no BigQuery, no network).

/api/web-event is public and unauthenticated, so every field in the payload is
untrusted input. These pin the coercion rules — especially for the engagement
metrics, where a wrong default is worse than a missing one: it looks like data.
"""
from __future__ import annotations

from booking.app import web_event_row


def test_arrival_event_has_no_engagement_columns():
    """session_start / page_view rows must leave dwell_ms + scroll_pct NULL, so
    a bounce-rate query can't silently average in the arrival rows."""
    row = web_event_row({"event_type": "session_start", "session_id": "s1"}, "UA", None)
    assert row["event_type"] == "session_start"
    assert "dwell_ms" not in row
    assert "scroll_pct" not in row


def test_engagement_event_carries_dwell_and_scroll():
    row = web_event_row(
        {"event_type": "page_engagement", "session_id": "s1",
         "dwell_ms": 11076, "scroll_pct": 50}, "UA", None)
    assert row["dwell_ms"] == 11076
    assert row["scroll_pct"] == 50


def test_zero_scroll_is_recorded_not_dropped():
    """0 = landed and never scrolled — the exact signal we added this for. A
    falsiness check (`if v:`) would drop it and hide every hard bounce."""
    row = web_event_row(
        {"event_type": "page_engagement", "dwell_ms": 0, "scroll_pct": 0}, None, None)
    assert row["dwell_ms"] == 0
    assert row["scroll_pct"] == 0


def test_out_of_range_values_are_clamped():
    row = web_event_row(
        {"event_type": "page_engagement",
         "dwell_ms": 99_999_999_999, "scroll_pct": 4200}, None, None)
    assert row["dwell_ms"] == 86_400_000   # 24h ceiling
    assert row["scroll_pct"] == 100


def test_negative_values_are_floored_at_zero():
    row = web_event_row(
        {"event_type": "page_engagement", "dwell_ms": -5, "scroll_pct": -1}, None, None)
    assert row["dwell_ms"] == 0
    assert row["scroll_pct"] == 0


def test_numeric_strings_are_accepted():
    """JSON from the wild sometimes stringifies numbers; don't lose the row."""
    row = web_event_row(
        {"event_type": "page_engagement", "dwell_ms": "1500", "scroll_pct": "75"},
        None, None)
    assert row["dwell_ms"] == 1500
    assert row["scroll_pct"] == 75


def test_junk_engagement_values_are_dropped_but_row_survives():
    """A bad metric must not cost us the attribution the row also carries."""
    row = web_event_row(
        {"event_type": "page_engagement", "session_id": "s1", "gclid": "abc",
         "dwell_ms": "not-a-number", "scroll_pct": None}, None, None)
    assert "dwell_ms" not in row
    assert "scroll_pct" not in row
    assert row["session_id"] == "s1"
    assert row["gclid"] == "abc"


def test_event_type_defaults_and_is_length_capped():
    assert web_event_row({}, None, None)["event_type"] == "page_view"
    assert len(web_event_row({"event_type": "x" * 200}, None, None)["event_type"]) == 32


def test_referer_is_the_visitors_document_referrer_not_the_header():
    """The beacon is a cross-origin fetch from our own page, so the HTTP Referer
    header is always gojiphysio.com. Storing it made every arrival look like a
    self-referral; the body's `referrer` (document.referrer) is the real source."""
    row = web_event_row({"event_type": "session_start", "referrer": "https://www.google.com/"},
                        "UA", "https://www.gojiphysio.com/")
    assert row["referer"] == "https://www.google.com/"


def test_empty_body_referrer_is_direct_not_the_header():
    """document.referrer == "" is a genuine Direct arrival; falling back to the
    header would mislabel it as our own domain."""
    row = web_event_row({"event_type": "session_start", "referrer": ""},
                        "UA", "https://www.gojiphysio.com/")
    assert row["referer"] is None


def test_header_is_only_a_fallback_when_the_body_has_no_referrer_key():
    row = web_event_row({"event_type": "session_start"}, "UA", "https://example.com/")
    assert row["referer"] == "https://example.com/"
