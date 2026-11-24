"""The REST layer: literal (RAW) sheet writes, append-only, token refresh, and
query escaping. A stub session records requests; nothing reaches Google."""
from __future__ import annotations

import json

import pytest

from careers import vacancies
from careers.google_store import GoogleStore, StoreError, _q


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body or {}
        self.headers = {"content-type": "application/json"}
        self.content = json.dumps(self._body).encode()

    def json(self):
        return self._body


class Session:
    def __init__(self):
        self.calls = []
        self.token_calls = 0

    def post(self, url, **kw):
        self.token_calls += 1
        return Resp(200, {"access_token": "at", "expires_in": 3600})

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        return Resp(200, {"files": [], "values": [["Application ID", "GOJI-APP-2026-0001"]]})


def _store():
    return GoogleStore("cid", "csecret", "rtoken", session=Session())


def test_append_row_is_raw_and_insert_only():
    s = _store()
    s.append_row("sheet1", "Applicants", ['=IMPORTXML("http://x","//a")', "+1", "@SUM(A1)"])
    method, url, kw = s.s.calls[-1]
    assert method == "POST" and url.endswith(":append")
    assert kw["params"] == {"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"}
    assert kw["json"]["values"][0][0] == '=IMPORTXML("http://x","//a")'
    assert kw["headers"]["Authorization"] == "Bearer at"


def test_token_is_cached():
    s = _store()
    s.column_values("sheet1", "Applicants")
    s.column_values("sheet1", "Applicants")
    assert s.s.token_calls == 1


def test_missing_credentials_raise():
    with pytest.raises(StoreError):
        GoogleStore("", "", "", session=Session())


def test_query_values_are_escaped():
    assert _q("O'Brien\\x") == "O\\'Brien\\\\x"


def test_http_errors_become_store_errors():
    s = _store()
    s.s.request = lambda *a, **k: Resp(500, {"error": {"message": "backend"}})
    with pytest.raises(StoreError) as e:
        s.get_file("abc")
    assert e.value.retryable


def test_vacancies_parse_and_lookup(monkeypatch):
    payload = {"vacancies": [
        {"id": "physiotherapist", "title": "Physio", "active": True, "form": "physio",
         "driveFolder": "Physiotherapist", "minDaysPerWeek": 3},
        {"id": "clinical-lead", "title": "Clinical Lead", "active": False},
        {"id": "general", "title": "spoof", "active": False},
        {"title": "no id"},
    ]}
    roles = vacancies._parse(payload)
    assert set(roles) == {"physiotherapist", "clinical-lead"}
    assert roles["physiotherapist"].min_days == 3
    monkeypatch.setattr(vacancies, "all_vacancies", lambda: roles)
    assert vacancies.lookup("physiotherapist")[0].form == "physio"
    assert vacancies.lookup("clinical-lead") == (None, "closed")
    assert vacancies.lookup("nope") == (None, "unknown")
    assert vacancies.lookup("general")[0].is_general  # can't be closed from the site
