"""Patient contacts kept current between nightly rebuilds: Plato's patient
webhook (staff actions) and /internal/book (patients we create) both update
marts.dim_patient_contact at once, so the WhatsApp assistant recognises a
patient the same day."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from booking import app as app_mod
from booking import patient_contacts as pc

TOKEN = "t0k"
PATH = f"/plato/webhook/{pc.webhook_token(TOKEN)}"


class FakeBQ:
    def __init__(self, fail=False):
        self.writes, self.waits, self.fail = [], [], fail

    def query(self, sql, job_config=None):
        if self.fail:
            raise RuntimeError("bigquery down")
        params = {p.name: p.value for p in job_config.query_parameters}
        assert sql.lstrip().startswith("MERGE") and "dim_patient_contact" in sql
        self.writes.append(params)
        bq = self

        class Job:
            def result(self, timeout=None):
                bq.waits.append(timeout)
        return Job()


class FakePlato:
    def __init__(self):
        self.gets, self.posts = [], []
        self.patients = {
            "p1": {"_id": "p1", "name": "  Sarah   Tan ", "handphone": "+65 9123 4567",
                   "email": "sarah@example.com"},
            "p2": {"_id": "p2", "name": {"first": "Wei", "last": "Lim"},
                   "mobile": {"number": "81234567"}, "email": "n/a"},
            "p3": {"_id": "p3", "name": "No Phone"}}

    def get(self, path, **kw):
        # Like Plato: GET /patient/{id} is a one-item list, not the record.
        self.gets.append((path, kw))
        return [self.patients[path.rsplit("/", 1)[-1]]]

    def post(self, path, payload):
        self.posts.append((path, payload))
        return {}


@pytest.fixture(autouse=True)
def _fresh_read_allowance():
    pc._reads.clear()
    yield
    pc._reads.clear()


@pytest.fixture
def setup(monkeypatch):
    bq, plato = FakeBQ(), FakePlato()
    monkeypatch.setattr(app_mod, "INTERNAL_TOKEN", TOKEN)
    monkeypatch.setattr(app_mod, "bq", lambda: bq)
    monkeypatch.setattr(app_mod, "plato", lambda: plato)
    monkeypatch.setattr(app_mod, "_run_webhook_work", lambda fn: fn())
    return app_mod.app.test_client(), plato, bq


def _deliver(c, *events, path=PATH):
    return c.post(path, json={"events": [{"db": "gojihealth", "on": 1, **e} for e in events]})


def test_a_patient_upsert_is_read_back_from_plato_and_written(setup):
    c, plato, bq = setup
    r = _deliver(c, {"event": "patient:upsert", "object_type": "patient", "object_id": "p1"},
                 {"event": "patient:upsert", "object_type": "patient", "object_id": "p1"})
    assert r.status_code == 200
    assert [g[0] for g in plato.gets] == ["/patient/p1"]        # duplicates read once
    assert plato.gets[0][1]["bulk"] is True                     # booking form keeps priority
    assert bq.writes == [{"patient_id": "p1", "full_name": "Sarah Tan",
                          "phone": "+65 9123 4567", "email": "sarah@example.com"}]


def test_a_merge_refreshes_the_surviving_record(setup):
    c, plato, bq = setup
    _deliver(c, {"event": "patient:merge", "from_id": "p9", "to_id": "p2"})
    assert [g[0] for g in plato.gets] == ["/patient/p2"]
    assert bq.writes == [{"patient_id": "p2", "full_name": "Wei Lim", "phone": "81234567",
                          "email": None}]


def test_a_patient_without_a_number_is_still_written_as_plato_has_it(setup):
    # The table mirrors Plato, as the nightly rebuild does: a removed number
    # must stop matching.
    c, _, bq = setup
    _deliver(c, {"event": "patient:upsert", "object_id": "p3"})
    assert bq.writes == [{"patient_id": "p3", "full_name": "No Phone", "phone": None,
                          "email": None}]


def test_rows_match_what_the_nightly_job_builds():
    spec = importlib.util.spec_from_file_location(
        "plato_patients_main",
        Path(__file__).resolve().parent.parent / "ingestion/plato_patients/main.py")
    nightly = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nightly)
    for p in FakePlato().patients.values():
        name = p["name"]
        raw = f"{name['first']} {name['last']}".strip() if isinstance(name, dict) else name
        assert pc.from_plato(p["_id"], p) == {
            "patient_id": p["_id"], "full_name": nightly.full_name(raw),
            "phone": nightly.extract_phone(p), "email": nightly.extract_email(p)}


def test_registration_token_is_activated(setup):
    c, plato, _ = setup
    _deliver(c, {"event": "webhook:token", "token": "eyJabc"})
    assert plato.posts == [("webhook/activate", {"token": "eyJabc"})]


def test_wrong_path_token_or_no_internal_token_is_not_found(setup, monkeypatch):
    c, plato, bq = setup
    assert _deliver(c, {"event": "patient:upsert", "object_id": "p1"},
                    path="/plato/webhook/guess").status_code == 404
    monkeypatch.setattr(app_mod, "INTERNAL_TOKEN", "")
    assert _deliver(c, {"event": "patient:upsert", "object_id": "p1"}).status_code == 404
    assert plato.gets == [] and bq.writes == []


def test_other_databases_events_and_junk_are_ignored(setup):
    c, plato, _ = setup
    assert c.post(PATH, json={"events": [{"db": "elsewhere", "event": "patient:upsert",
                                          "object_id": "p1"},
                                         {"db": "gojihealth", "event": "appointment:upsert",
                                          "object_id": "a1"},
                                         {"db": "gojihealth", "event": "patient:upsert",
                                          "object_id": "../x"}]}).status_code == 200
    assert c.post(PATH, data="not json").status_code == 200    # Plato drops a failing webhook
    assert plato.gets == []


def test_a_delivery_without_a_json_content_type_is_still_read(setup):
    c, plato, _ = setup
    body = '{"events": [{"db": "gojihealth", "event": "patient:upsert", "object_id": "p1"}]}'
    assert c.post(PATH, data=body, content_type="text/plain").status_code == 200
    assert [g[0] for g in plato.gets] == ["/patient/p1"]


def test_plato_reads_are_capped_per_minute_and_never_retried(setup, monkeypatch):
    # The availability snapshot pages Plato from the same bulk share; a burst
    # of staff edits must not starve it. Over the cap waits for the nightly run.
    c, plato, _ = setup
    monkeypatch.setattr(pc, "READS_PER_MIN", 2)
    _deliver(c, *[{"event": "patient:upsert", "object_id": p} for p in ("p1", "p2", "p3")])
    assert [g[0] for g in plato.gets] == ["/patient/p1", "/patient/p2"]
    assert all(g[1]["_retries"] == 0 and g[1]["max_wait_s"] <= 5 for g in plato.gets)
    assert pc._take_read(now=10**9)                         # the minute has passed


def test_a_large_batch_is_capped():
    events = [{"db": "d", "event": "patient:upsert", "object_id": f"p{i}"} for i in range(100)]
    ids, _ = pc.patient_ids({"events": events}, "d")
    assert len(ids) == pc.MAX_PATIENTS_PER_DELIVERY


def test_the_write_wait_is_bounded_and_a_failure_never_raises(setup):
    # /internal/book waits on this write; the assistant gives up after 30s.
    c, _, bq = setup
    _deliver(c, {"event": "patient:upsert", "object_id": "p1"})
    assert bq.waits == [pc.WRITE_WAIT_S] and pc.WRITE_WAIT_S <= 5
    assert pc.upsert(FakeBQ(fail=True), "t", {"patient_id": "p1"}) is False


def test_webhook_token_is_derived_and_not_the_internal_token():
    t = pc.webhook_token(TOKEN)
    assert len(t) == 32 and TOKEN not in t and t == pc.webhook_token(TOKEN)
    assert pc.webhook_token("") == ""


def test_an_unexpected_patient_response_is_skipped_not_written(setup):
    c, plato, bq = setup
    plato.get = lambda path, **kw: []
    assert _deliver(c, {"event": "patient:upsert", "object_id": "p1"}).status_code == 200
    assert bq.writes == []


# --- catch-up: patients the webhook never told us about ------------------------

TABLE = "goji-bi.marts.dim_patient_contact"


class ListPlato:
    """GET /patient?modified_since=... pages, 20 a page like Plato."""

    def __init__(self, patients, fail=None):
        self.patients, self.fail, self.calls = patients, fail, []

    def get(self, path, params=None, **kw):
        self.calls.append((path, dict(params or {}), kw))
        if self.fail:
            raise self.fail
        page = params["current_page"]
        return self.patients[(page - 1) * 20: page * 20]


@pytest.fixture
def fresh_cursor(monkeypatch):
    monkeypatch.setattr(pc, "_caught_up_to", None)
    monkeypatch.setattr(pc, "_written_edit", {})


def _patient(pid, edited="2026-11-25 16:33:25", **kw):
    return {"_id": pid, "name": "Mei Tan", "telephone": "+6582823628",
            "last_edited": edited, "created_by": "terminal", **kw}


def test_catch_up_writes_patients_the_webhook_missed(fresh_cursor):
    """25 Nov 2026: a self-registered patient, a staff edit and our own API
    writes all changed in Plato and none fired the webhook."""
    plato, bq = ListPlato([_patient("t1"), _patient("s1", created_by="Claire.ng")]), FakeBQ()
    out = pc.catch_up(plato, bq, TABLE, now=1_800_000_000)
    assert out == {"written": 2, "unchanged": 0, "failed": 0}
    assert [w["patient_id"] for w in bq.writes] == ["t1", "s1"]
    assert bq.writes[0]["phone"] == "+6582823628" and bq.writes[0]["full_name"] == "Mei Tan"
    (path, params, kw), = plato.calls
    assert path == "patient" and params["modified_since"] == 1_800_000_000 - pc.CATCH_UP_FIRST_LOOKBACK_S
    assert kw["bulk"] is True and kw["_retries"] == 0


def test_the_next_pass_overlaps_and_skips_rows_already_written(fresh_cursor):
    plato, bq = ListPlato([_patient("t1")]), FakeBQ()
    pc.catch_up(plato, bq, TABLE, now=1000.0)
    out = pc.catch_up(plato, bq, TABLE, now=1300.0)
    assert plato.calls[1][1]["modified_since"] == 1000 - pc.CATCH_UP_OVERLAP_S
    assert out == {"written": 0, "unchanged": 1, "failed": 0} and len(bq.writes) == 1
    plato.patients = [_patient("t1", edited="2026-11-25 17:00:00")]
    assert pc.catch_up(plato, bq, TABLE, now=1600.0)["written"] == 1


def test_a_full_page_reads_the_next_one(fresh_cursor):
    plato, bq = ListPlato([_patient(f"p{i}") for i in range(25)]), FakeBQ()
    assert pc.catch_up(plato, bq, TABLE, now=1000.0)["written"] == 25
    assert [c[1]["current_page"] for c in plato.calls] == [1, 2]
    assert pc._caught_up_to == 1000.0


def test_too_many_pages_keep_the_cursor(fresh_cursor):
    plato, bq = ListPlato([_patient(f"p{i}") for i in range(20 * pc.CATCH_UP_MAX_PAGES)]), FakeBQ()
    pc.catch_up(plato, bq, TABLE, now=1000.0)
    assert len(plato.calls) == pc.CATCH_UP_MAX_PAGES and pc._caught_up_to is None


def test_a_failed_write_keeps_the_cursor_so_the_next_pass_retries(fresh_cursor):
    plato = ListPlato([_patient("t1")])
    assert pc.catch_up(plato, FakeBQ(fail=True), TABLE, now=1000.0)["failed"] == 1
    assert pc._caught_up_to is None
    bq = FakeBQ()
    assert pc.catch_up(plato, bq, TABLE, now=1300.0)["written"] == 1


def test_a_plato_error_propagates_and_keeps_the_cursor(fresh_cursor):
    with pytest.raises(RuntimeError):
        pc.catch_up(ListPlato([], fail=RuntimeError("429")), FakeBQ(), TABLE, now=1000.0)
    assert pc._caught_up_to is None
