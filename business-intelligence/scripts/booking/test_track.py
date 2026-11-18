"""/api/track is public and unauthenticated. Only browser-observable stages may
be written through it; the server-only ones (confirmed, book_error,
availability_empty) are logged by the server itself. A forged book_error once
carried an HTML payload in `detail` toward the dashboard (2026-11-12).
"""
from __future__ import annotations

import pytest

from booking import app as app_mod


@pytest.fixture
def calls(monkeypatch):
    seen = []
    monkeypatch.setattr(app_mod, "_track_async", lambda *a, **kw: seen.append((a, kw)))
    app_mod.app.config["TESTING"] = True
    return seen


@pytest.mark.parametrize("stage", ["confirmed", "book_error", "availability_empty",
                                   "bogus", None])
def test_server_only_and_unknown_stages_are_dropped(calls, stage):
    with app_mod.app.test_client() as c:
        r = c.post("/api/track", json={"stage": stage, "session_id": "s1",
                                       "detail": "<img src=x onerror=alert(1)>"})
    assert r.status_code == 204
    assert calls == []


@pytest.mark.parametrize("stage", sorted(app_mod.CLIENT_STAGES))
def test_client_stages_are_recorded(calls, stage):
    with app_mod.app.test_client() as c:
        r = c.post("/api/track", json={"stage": stage, "session_id": "s1"})
    assert r.status_code == 204
    assert len(calls) == 1 and calls[0][0][0] == stage


def test_client_stages_match_website_type():
    """The website's FunnelStage union is exactly what the browser may send."""
    assert app_mod.CLIENT_STAGES == {
        "page_view", "service_selected", "date_picked", "time_selected", "details",
        "submitted", "validation_error", "availability_error", "clinician_changed"}
