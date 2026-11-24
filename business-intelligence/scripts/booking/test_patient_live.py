"""Fresh patient contacts: Plato's patient webhook and patients created by
/internal/book both land in marts.patient_contact_live at once, so the
WhatsApp assistant recognises a patient before the nightly ingest."""
from __future__ import annotations

import pytest

from booking import app as app_mod
from booking import patient_live

TOKEN = "t0k"
PATH = f"/plato/webhook/{patient_live.webhook_token(TOKEN)}"


class FakeBQ:
    def __init__(self):
        self.rows, self.kw = [], {}

    def insert_rows_json(self, table, rows, **kw):
        self.rows += [(table, r) for r in rows]
        self.kw = kw
        return []


class FakePlato:
    db = "gojihealth"

    def __init__(self):
        self.gets, self.posts = [], []
        self.patients = {"p1": {"_id": "p1", "name": "  Sarah   Tan ", "handphone": "+65 9123 4567"},
                         "p2": {"_id": "p2", "name": {"first": "Wei", "last": "Lim"},
                                "mobile": {"number": "81234567"}},
                         "p3": {"_id": "p3", "name": "No Phone"}}

    def get(self, path, **kw):
        self.gets.append((path, kw))
        return self.patients[path.rsplit("/", 1)[-1]]

    def post(self, path, payload):
        self.posts.append((path, payload))
        return {}


@pytest.fixture(autouse=True)
def _fresh_read_allowance():
    patient_live._reads.clear()
    yield
    patient_live._reads.clear()


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


def test_a_patient_upsert_is_read_back_from_plato_and_recorded(setup):
    c, plato, bq = setup
    r = _deliver(c, {"event": "patient:upsert", "object_type": "patient", "object_id": "p1"},
                 {"event": "patient:upsert", "object_type": "patient", "object_id": "p1"})
    assert r.status_code == 200
    assert [g[0] for g in plato.gets] == ["/patient/p1"]        # duplicates read once
    assert plato.gets[0][1]["bulk"] is True                     # booking form keeps priority
    (table, row), = bq.rows
    assert table.endswith("marts.patient_contact_live")
    assert {k: row[k] for k in ("patient_id", "full_name", "phone", "source")} == {
        "patient_id": "p1", "full_name": "Sarah Tan", "phone": "+65 9123 4567",
        "source": "plato_webhook"}


def test_a_merge_refreshes_the_surviving_record(setup):
    c, plato, bq = setup
    _deliver(c, {"event": "patient:merge", "from_id": "p9", "to_id": "p2"})
    assert [g[0] for g in plato.gets] == ["/patient/p2"]
    assert bq.rows[0][1]["full_name"] == "Wei Lim" and bq.rows[0][1]["phone"] == "81234567"


def test_a_patient_without_a_number_is_skipped(setup):
    c, _, bq = setup
    assert _deliver(c, {"event": "patient:upsert", "object_id": "p3"}).status_code == 200
    assert bq.rows == []


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
    assert plato.gets == [] and bq.rows == []


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


def test_a_large_batch_is_capped():
    events = [{"db": "d", "event": "patient:upsert", "object_id": f"p{i}"} for i in range(100)]
    ids, _ = patient_live.patient_ids({"events": events}, "d")
    assert len(ids) == patient_live.MAX_PATIENTS_PER_DELIVERY


def test_webhook_token_is_derived_and_not_the_internal_token():
    t = patient_live.webhook_token(TOKEN)
    assert len(t) == 32 and TOKEN not in t and t == patient_live.webhook_token(TOKEN)
    assert patient_live.webhook_token("") == ""


def test_insert_failure_never_raises():
    class Broken:
        def insert_rows_json(self, *_):
            raise RuntimeError("bq down")
    assert patient_live.record(Broken(), "t", [{"patient_id": "p1"}]) == 0


def test_plato_reads_are_capped_per_minute_and_never_retried(setup, monkeypatch):
    # The availability snapshot pages Plato from the same bulk share; a burst
    # of staff edits must not starve it. Over the cap waits for the nightly run.
    c, plato, bq = setup
    monkeypatch.setattr(patient_live, "READS_PER_MIN", 2)
    _deliver(c, *[{"event": "patient:upsert", "object_id": p} for p in ("p1", "p2", "p3")])
    assert [g[0] for g in plato.gets] == ["/patient/p1", "/patient/p2"]
    assert all(g[1]["_retries"] == 0 and g[1]["max_wait_s"] <= 5 for g in plato.gets)
    assert patient_live._take_read(now=10**9)               # the minute has passed


def test_the_insert_is_time_bounded(setup):
    # /internal/book waits on this write; the assistant gives up after 30s.
    c, _, bq = setup
    _deliver(c, {"event": "patient:upsert", "object_id": "p1"})
    assert bq.kw["timeout"] <= 5 and bq.kw["retry"] is not None


def test_a_delivery_without_a_json_content_type_is_still_read(setup):
    c, plato, _ = setup
    body = '{"events": [{"db": "gojihealth", "event": "patient:upsert", "object_id": "p1"}]}'
    assert c.post(PATH, data=body, content_type="text/plain").status_code == 200
    assert [g[0] for g in plato.gets] == ["/patient/p1"]
