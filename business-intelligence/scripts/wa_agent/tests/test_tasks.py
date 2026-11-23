"""Scale to zero: the webhook queues events on Cloud Tasks and the work runs
inside /tasks/run; cache warms ride the same queue."""
import hashlib
import hmac
import json
import time

import pytest

from wa_agent import app as app_mod
from wa_agent import config, events, notify, tasks
from wa_agent.state import MemoryStore
from wa_agent.whatsapp import HistoryChunk, Inbound

from .fakes import FakeClaude, FakeWhatsApp, final
from .payloads import inbound

CUSTOMER = "6591234567"


@pytest.fixture
def env(monkeypatch):
    rec, queued = [], []
    monkeypatch.setattr(app_mod, "store", MemoryStore())
    monkeypatch.setattr(app_mod, "wa", FakeWhatsApp())
    monkeypatch.setattr(app_mod, "claude", FakeClaude())
    monkeypatch.setattr(app_mod, "_sleep", lambda s: None)
    monkeypatch.setattr(events, "record", lambda e, w, **f: rec.append((e, f)) or {})
    monkeypatch.setattr(notify, "send", lambda kind, **kw: None)
    monkeypatch.setattr(config, "TASKS_QUEUE", "projects/p/locations/l/queues/q")
    monkeypatch.setattr(config, "PUBLIC_URL", "https://svc.example")
    monkeypatch.setattr(tasks, "enqueue",
                        lambda body, **kw: queued.append((json.loads(body), kw)) or True)
    ran = []
    monkeypatch.setattr(app_mod, "_submit", lambda fn, *a: ran.append(fn.__name__))
    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        yield c, rec, queued, ran


def post(client, body):
    raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
    return client.post("/webhook", data=raw, content_type="application/json",
                       headers={"X-Hub-Signature-256": sig})


def run(client, payload: dict):
    body = json.dumps(payload, sort_keys=True).encode()
    return client.post("/tasks/run", data=body, content_type="application/json",
                       headers={tasks.SIGNATURE_HEADER: tasks.sign(body)})


def test_webhook_queues_instead_of_working(env):
    client, rec, queued, ran = env
    assert post(client, inbound(ts=int(time.time()))).status_code == 200
    ((payload, _),) = queued
    assert payload["kind"] == "inbound" and payload["event"]["wa_id"] == CUSTOMER
    assert ran == [] and app_mod.claude.requests == []


def test_queue_failure_falls_back_to_a_thread(env, monkeypatch):
    client, rec, queued, ran = env
    monkeypatch.setattr(tasks, "enqueue", lambda body, **kw: False)
    post(client, inbound(ts=int(time.time())))
    assert ran == ["_run_event"]


def test_task_runs_the_turn_inside_the_request(env):
    client, rec, queued, ran = env
    app_mod.claude.queue.append(final())
    ev = Inbound(wa_id=CUSTOMER, msg_id="wamid.t1", ts=time.time(), text="hours?", name="Mei")
    body = json.loads(tasks.encode("inbound", ev, received=time.time()))
    assert run(client, body).status_code == 200
    assert app_mod.wa.sent and app_mod.wa.sent[0][0] == CUSTOMER
    assert any(p["kind"] == "warm" for p, _ in queued) or not config.KEEP_WARM \
        or config.BACKEND != "api"


def test_task_signature_required(env):
    client, rec, queued, ran = env
    body = tasks.encode("warm")
    assert client.post("/tasks/run", data=body).status_code == 403
    assert client.post("/tasks/run", data=body,
                       headers={tasks.SIGNATURE_HEADER: "0" * 64}).status_code == 403


def test_history_chunk_round_trips(env, monkeypatch):
    client, rec, queued, ran = env
    seen = []
    monkeypatch.setattr(app_mod, "handle_history", lambda ev: seen.append(ev))
    chunk = HistoryChunk(threads={CUSTOMER: (1.0, 2.0)}, progress=100)
    run(client, json.loads(tasks.encode("history", chunk, received=1.0)))
    assert seen[0].threads[CUSTOMER] == [1.0, 2.0] and seen[0].progress == 100


def test_warm_task_warms_and_chains(env, monkeypatch):
    client, rec, queued, ran = env
    monkeypatch.setattr(config, "BACKEND", "api")
    monkeypatch.setattr(config, "KEEP_WARM", True)
    monkeypatch.setattr(app_mod.agent, "last_call_at", 0.0)
    monkeypatch.setattr(app_mod.agent, "warm_cache", lambda m: {"cost_usd": 0.006})
    from datetime import datetime
    noon = datetime(2026, 11, 20, 12, 0, tzinfo=app_mod.SGT).timestamp()
    monkeypatch.setattr(app_mod.time, "time", lambda: noon)
    run(client, json.loads(tasks.encode("warm")))
    assert ("warm", {"cost_usd": 0.006}) in rec
    ((payload, kw),) = queued
    assert payload["kind"] == "warm" and kw["delay_s"] == config.WARM_EVERY_S
    assert kw["name"] == tasks.warm_name(noon)


def test_no_warm_scheduled_after_hours(env, monkeypatch):
    client, rec, queued, ran = env
    monkeypatch.setattr(config, "BACKEND", "api")
    monkeypatch.setattr(config, "KEEP_WARM", True)
    from datetime import datetime
    late = datetime(2026, 11, 20, 21, 40, tzinfo=app_mod.SGT).timestamp()
    monkeypatch.setattr(app_mod.time, "time", lambda: late)
    app_mod._schedule_warm()
    assert queued == []


def test_warm_names_share_a_slot():
    a, b = tasks.warm_name(10_000.0), tasks.warm_name(10_000.0 + 1)
    assert a == b and a.startswith("warm-")


def test_signature_uses_the_admin_token(monkeypatch):
    body = b'{"kind":"warm"}'
    assert tasks.valid(body, tasks.sign(body))
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    assert not tasks.valid(body, tasks.sign(body))
