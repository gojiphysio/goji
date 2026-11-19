"""Go-live features: the go-live cut-off, history import, pause on Chris's
reply and resume by chat code, rollout stages and contact scope, staff pings and commands, the morning summary,
kill-switch gaps, the hash salt and PDPA forget."""
import hashlib
import hmac
import json
import time

import pytest

from wa_agent import app as app_mod
from wa_agent import config, events, notify, staff, state as state_mod, summary
from wa_agent.policy import (AGENT, DRAFT, ESCALATE, HUMAN, PAUSED, SEND, SILENT, WAITING,
                             ChatState, Decision, Proposal, apply_stage, gate, out_of_scope,
                             pre_golive_chat)
from wa_agent.state import MemoryStore, note_outcome
from wa_agent.whatsapp import parse_webhook

from .fakes import FakeClaude, FakeWhatsApp, final
from .payloads import echo, inbound

CUSTOMER = "6591234567"
CHRIS = "6591110000"
DAY = 86400


class FakeWA(FakeWhatsApp):
    def __init__(self, fail=False, template_fail=False):
        super().__init__(fail)
        self.templates = []
        self.template_fail = template_fail

    def send_template(self, wa_id, name, params, language="en"):
        if self.template_fail:
            raise RuntimeError("template failed")
        self.templates.append((wa_id, name, params))
        return f"wamid.tpl{len(self.templates)}"


@pytest.fixture
def env(monkeypatch):
    rec, notes, plain = [], [], []
    monkeypatch.setattr(app_mod, "store", MemoryStore())
    monkeypatch.setattr(app_mod, "wa", FakeWA())
    monkeypatch.setattr(app_mod, "claude", FakeClaude())
    monkeypatch.setattr(app_mod, "_submit", lambda fn, *a: fn(*a))
    monkeypatch.setattr(app_mod, "_sleep", lambda s: None)
    monkeypatch.setattr(events, "record", lambda e, w, **f: rec.append((e, f)) or {})
    monkeypatch.setattr(notify, "send", lambda kind, **kw: notes.append((kind, kw)))
    monkeypatch.setattr(notify, "send_plain", lambda subj, body: plain.append((subj, body)))
    monkeypatch.setattr(config, "STAFF", frozenset())
    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        yield c, rec, notes, plain


def post(client, body):
    raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
    return client.post("/webhook", data=raw, content_type="application/json",
                       headers={"X-Hub-Signature-256": sig})


ADMIN = {"X-Admin-Token": "admin-token"}


def names(rec):
    return [e for e, _ in rec]


def silent_reasons(rec):
    return [f.get("reason") for e, f in rec if e == "silent"]


# --- go-live cut-off, pause on reply, resume ------------------------------------

GO = 1_800_000_000.0


@pytest.mark.parametrize("owner,days_before,held", [
    ("", 10, True),       # Chris's chat 10 days before go-live: hers
    ("", 29, True),
    ("", 31, False),      # quiet for over 30 days before go-live: the agent's
    ("", None, False),    # first contact after go-live (no earlier message)
    ("agent", 10, False), # the agent already took it
])
def test_pre_golive_chat(owner, days_before, held):
    st = ChatState(wa_id=CUSTOMER, owner=owner)
    prior = GO - days_before * DAY if days_before is not None else 0.0
    assert pre_golive_chat(st, prior, GO, 30) is held


def test_cut_off_only_looks_before_go_live():
    st = ChatState(wa_id=CUSTOMER)
    assert not pre_golive_chat(st, GO + 3600, GO, 30)   # a chat that started after go-live
    assert not pre_golive_chat(st, GO - DAY, 0, 30)     # go-live not set


def test_lookback_is_thirty_days():
    assert config.GOLIVE_LOOKBACK_DAYS == 30


def test_gate_order():
    st = ChatState(wa_id=CUSTOMER)
    assert gate(st, GO, kill_switch=True, not_live=True).reason == "kill_switch"
    assert gate(st, GO, kill_switch=False, not_live=True, pre_golive=True).reason == "not_live"
    assert gate(st, GO, kill_switch=False, pre_golive=True).reason == "pre_golive_chat"
    assert gate(st, GO, kill_switch=False, scope_out=True).reason == "out_of_scope"


def test_chris_chat_at_go_live_pauses_and_stays_hers(env):
    client, rec, _, _ = env
    now = time.time()
    app_mod.store.set_go_live(now - DAY)
    st = ChatState(wa_id=CUSTOMER, last_customer_at=now - 5 * DAY, last_staff_at=now - 4 * DAY)
    app_mod.store.save(st)                       # e.g. from the history import
    app_mod.claude.queue.append(final())
    post(client, inbound(ts=int(now)))
    assert silent_reasons(rec)[-1] == "pre_golive_chat"
    st = app_mod.store.load(CUSTOMER)
    assert st.mode == PAUSED and st.code
    # Months later it is still hers until she resumes it.
    post(client, inbound(ts=int(now + 60 * DAY), msg_id="wamid.later"))
    assert silent_reasons(rec)[-1] == "paused" and app_mod.wa.sent == []


def test_new_chat_after_go_live_is_the_agents(env):
    client, rec, _, _ = env
    app_mod.store.set_go_live(time.time() - DAY)
    app_mod.claude.queue.append(final())
    post(client, inbound(ts=int(time.time())))
    assert len(app_mod.wa.sent) == 1 and app_mod.store.load(CUSTOMER).owner == "agent"


def test_deployed_run_is_silent_until_go_live(env, monkeypatch):
    client, rec, _, _ = env
    monkeypatch.setattr(config, "STATE_BACKEND", "firestore")
    monkeypatch.setattr(config, "GO_LIVE", 0.0)
    app_mod.claude.queue.extend([final(), final()])
    post(client, inbound(ts=int(time.time()) - 3600))
    assert silent_reasons(rec)[-1] == "not_live" and app_mod.wa.sent == []
    assert app_mod.store.load(CUSTOMER).last_customer_at > 0      # times still recorded
    r = client.post("/admin/go-live", json={}, headers=ADMIN)
    assert r.json["go_live"] > 0
    # That chat had a message before go-live: Chris's. A new number: the agent's.
    post(client, inbound(ts=int(time.time()), msg_id="wamid.2"))
    assert silent_reasons(rec)[-1] == "pre_golive_chat"
    post(client, inbound(wa_id="6590000009", ts=int(time.time()), msg_id="wamid.3"))
    assert len(app_mod.wa.sent) == 1


def test_go_live_route_validates(env):
    client, _, _, _ = env
    assert client.post("/admin/go-live", json={}).status_code == 403
    assert client.post("/admin/go-live", json={"at": "soon"}, headers=ADMIN).status_code == 400
    assert client.post("/admin/go-live", json={"at": None}, headers=ADMIN).json["go_live"] == 0
    assert client.post("/admin/go-live", json={"at": GO}, headers=ADMIN).json["go_live"] == GO


def test_chris_writing_pauses_with_no_idle_handback(env):
    client, rec, _, _ = env
    now = int(time.time())
    app_mod.claude.queue.append(final())
    post(client, inbound(ts=now - 3 * DAY, msg_id="wamid.a"))
    post(client, echo(ts=now - 3 * DAY + 60))
    st = app_mod.store.load(CUSTOMER)
    assert st.mode == PAUSED and st.owner == ""
    app_mod.claude.queue.append(final())
    post(client, inbound(ts=now, msg_id="wamid.b"))   # three days later: still hers
    assert silent_reasons(rec)[-1] == "paused" and len(app_mod.wa.sent) == 1


def test_first_message_claims_chat_so_burst_passes(env):
    client, rec, _, _ = env
    now = int(time.time())
    app_mod.claude.queue.extend([final(), final()])
    post(client, inbound(ts=now - 5, msg_id="wamid.a"))
    assert app_mod.store.load(CUSTOMER).owner == "agent"
    post(client, inbound(ts=now, msg_id="wamid.b", text="and Saturdays?"))
    assert len(app_mod.wa.sent) == 2


@pytest.fixture
def with_staff(monkeypatch):
    monkeypatch.setattr(config, "STAFF", frozenset({CHRIS}))


def test_staff_resume_by_code_sends_the_customer_nothing(env, with_staff):
    client, rec, _, _ = env
    now = int(time.time())
    app_mod.claude.queue.append(final())
    post(client, inbound(ts=now - 600, msg_id="wamid.a"))
    post(client, echo(ts=now - 500))
    code = app_mod.store.load(CUSTOMER).code
    sent_before = list(app_mod.wa.sent)
    post(client, inbound(wa_id=CHRIS, text=f"Resume chat #{int(code)}", ts=now, msg_id="s1"))
    st = app_mod.store.load(CUSTOMER)
    assert st.mode == AGENT and st.owner == "agent"
    new = app_mod.wa.sent[len(sent_before):]
    assert [to for to, _ in new] == [CHRIS]               # nothing to the customer
    assert f"#{code}" in new[0][1] and "next message" in new[0][1]
    app_mod.claude.queue.append(final())
    post(client, inbound(ts=now + 60, msg_id="wamid.c"))  # the customer's next message
    assert app_mod.wa.sent[-1][0] == CUSTOMER


def test_staff_pause_and_unknown_code(env, with_staff):
    client, rec, _, _ = env
    now = int(time.time())
    app_mod.claude.queue.append(final())
    post(client, inbound(ts=now - 600, msg_id="wamid.a"))
    code = app_mod.store.load(CUSTOMER).code
    post(client, inbound(wa_id=CHRIS, text=f"pause {code}", ts=now, msg_id="s1"))
    assert app_mod.store.load(CUSTOMER).mode == PAUSED
    post(client, inbound(wa_id=CHRIS, text="resume 999", ts=now, msg_id="s2"))
    assert "can't find chat #999" in app_mod.wa.sent[-1][1]


def test_chat_codes_are_unique_and_padded():
    st = MemoryStore()
    assert [st.next_code() for _ in range(3)] == ["001", "002", "003"]
    assert state_mod.parse_code("chat #4") == "004" and state_mod.parse_code("x") == ""


# --- history import ------------------------------------------------------------------

def history_body(threads, progress=100, errors=None):
    h = {"metadata": {"phase": 0, "chunk_order": 1, "progress": progress},
         "threads": threads}
    if errors:
        h = {"errors": errors}
    return {"entry": [{"changes": [{"field": "history", "value": {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "6583770401", "phone_number_id": "pnid"},
        "history": [h]}}]}]}


def test_parse_history_keeps_timestamps_only():
    body = history_body([{"id": CUSTOMER, "messages": [
        {"from": CUSTOMER, "id": "m1", "timestamp": "1000", "type": "text",
         "text": {"body": "secret text"}},
        {"from": "6583770401", "to": CUSTOMER, "id": "m2", "timestamp": "2000", "type": "text"},
    ]}], progress=40)
    (chunk,) = parse_webhook(body)
    assert chunk.threads == {CUSTOMER: (1000.0, 2000.0)}
    assert chunk.progress == 40 and not chunk.declined
    assert "secret" not in repr(chunk)


def test_parse_history_declined():
    (chunk,) = parse_webhook(history_body([], errors=[{"code": 2593109}]))
    assert chunk.declined and chunk.error_code == 2593109


def test_history_import_feeds_the_cut_off(env):
    client, rec, _, _ = env
    now = time.time()
    post(client, history_body([{"id": CUSTOMER, "messages": [
        {"from": CUSTOMER, "id": "m1", "timestamp": str(int(now - 5 * DAY)), "type": "text"},
        {"from": "6583770401", "to": CUSTOMER, "id": "m2",
         "timestamp": str(int(now - 4 * DAY)), "type": "text"}]}]))
    st = app_mod.store.load(CUSTOMER)
    assert st.last_staff_at == int(now - 4 * DAY) and st.history == []
    assert app_mod.store.get_history_imported()
    app_mod.store.set_go_live(now - DAY)
    app_mod.claude.queue.append(final())
    post(client, inbound(ts=int(now)))
    assert silent_reasons(rec)[-1] == "pre_golive_chat"


# --- rollout stages and contact scope ---------------------------------------------

def test_stage_presets():
    s0, s1, s2, s3 = (config.stage_policy(i) for i in range(4))
    assert config.stage_policy(None) == config.INTENT_POLICY
    assert s0["pricing"] == "auto" and s0["booking"] == "auto"
    assert s0["billing"] == config.LEAVE and s0["reschedule"] == config.LEAVE
    assert s0["urgent"] == "escalate"
    assert s1["billing"] == "escalate" and s1["reschedule"] == "escalate"
    assert s2["reschedule"] == "auto" and s2["existing_appointment"] == "auto"
    assert "draft" not in set(s3.values()) and s3["cancel"] == "escalate"


def P(intent, **kw):
    return Proposal(reply="", intent=intent, confidence=0.9, escalate=kw.pop("escalate", False),
                    **kw)


def test_apply_stage():
    d = Decision(DRAFT, "intent:billing")
    assert apply_stage(d, P("billing"), None) is d
    assert apply_stage(d, P("billing"), 0).action == SILENT
    up = apply_stage(d, P("billing"), 1)
    assert up.action == ESCALATE and up.holding
    urgent = Decision(ESCALATE, "model_escalated")
    assert apply_stage(urgent, P("urgent", escalate=True), 0).action == ESCALATE
    failed = P("other", escalate=True, failed=True)
    assert apply_stage(Decision(ESCALATE, "x"), failed, 0).action == ESCALATE
    assert apply_stage(Decision(ESCALATE, "x"), P("human_requested", escalate=True), 0).action == SILENT


def test_stage0_leaves_billing_to_chris_silently(env):
    client, rec, notes, _ = env
    app_mod.store.save_rollout({"stage": 0})
    app_mod.claude.queue.append(final(reply="Let me check that charge", intent="billing"))
    post(client, inbound(text="I was charged twice", ts=int(time.time())))
    assert app_mod.wa.sent == [] and notes == []
    assert silent_reasons(rec)[-1] == "stage_leave"
    assert app_mod.store.load(CUSTOMER).outcomes[-1]["outcome"] == "left"


def test_stage3_cancel_sends_holding_reply_not_the_models(env):
    client, rec, notes, _ = env
    app_mod.store.save_rollout({"stage": 3})
    app_mod.claude.queue.append(final(reply="Done, I've cancelled it!", intent="cancel"))
    post(client, inbound(text="please cancel tomorrow", ts=int(time.time())))
    (_, text), = app_mod.wa.sent
    assert "cancelled" not in text and "team" in text
    assert notes[0][0] == "escalated"
    assert app_mod.store.load(CUSTOMER).outcomes[-1]["outcome"] == "handed over"


def test_out_of_scope():
    st = ChatState(wa_id=CUSTOMER)
    assert not out_of_scope("quiet", st, True, {"returning": True})
    assert out_of_scope("new_only", st, True, {})
    assert out_of_scope("new_only", st, False, {"returning": True})
    assert not out_of_scope("new_only", st, False, {})
    assert not out_of_scope("new_only", ChatState(wa_id=CUSTOMER, owner="agent"), True, {})


def test_new_only_skips_returning_patients(env, monkeypatch):
    client, rec, _, _ = env
    app_mod.store.save_rollout({"contact_scope": "new_only"})
    monkeypatch.setattr(app_mod.tools, "patient_context", lambda w: {"returning": True})
    post(client, inbound(ts=int(time.time())))
    assert silent_reasons(rec)[-1] == "out_of_scope"


def test_rollout_admin_routes(env):
    client, _, _, _ = env
    assert client.get("/admin/rollout").status_code == 403
    r = client.post("/admin/rollout", json={"stage": 1, "contact_scope": "new_only"},
                    headers=ADMIN)
    assert r.json["stage"] == 1 and r.json["contact_scope"] == "new_only"
    assert client.post("/admin/rollout", json={"stage": 7}, headers=ADMIN).status_code == 400
    assert client.post("/admin/rollout", json={"stage": True}, headers=ADMIN).status_code == 400
    assert client.post("/admin/rollout", json={"nope": 1}, headers=ADMIN).status_code == 400
    r = client.post("/admin/rollout", json={"stage": None}, headers=ADMIN)
    assert r.json["stage"] == config.STAGE and r.json["saved"] == {"contact_scope": "new_only"}
    assert client.get("/admin/rollout", headers=ADMIN).json["contact_scope"] == "new_only"


def test_resolve_rollout_ignores_bad_values():
    r = config.resolve_rollout({"stage": "2", "contact_scope": "x", "hours": "never"})
    assert r == config.resolve_rollout({})


# --- staff ------------------------------------------------------------------------

def test_staff_helpers():
    assert staff.label("Mei Ling Tan", CUSTOMER) == "Mei"
    assert staff.label("", CUSTOMER) == "the customer ending 4567"
    assert "[number]" in staff.redact("call me on +65 9123 4567")
    assert "4567" not in staff.redact("call me on +65 9123 4567")
    who, reason = staff.template_params("Mei (#004)", "x" * 400)
    assert who == "Mei (#004)" and len(reason) <= staff.PARAM_MAX
    assert "\n" not in staff.template_params("Mei", "a\nb")[1]
    assert staff.template_params("", "")[1]
    assert staff.parse_command("Stop!") == ("stop", "")
    assert staff.parse_command("STATUS please") == ("status", "")
    assert staff.parse_command("hello") == ("help", "")
    assert staff.parse_command("resume 004") == ("resume", "004")
    assert staff.parse_command("Resume chat #12") == ("resume", "012")
    assert staff.parse_command("resume") == ("help", "")
    assert staff.label("Mei", CUSTOMER, "004") == "Mei (#004)"


def test_staff_message_is_never_a_customer(env, with_staff):
    client, rec, notes, _ = env
    post(client, inbound(wa_id=CHRIS, text="hi", ts=int(time.time())))
    assert "inbound" not in names(rec) and "proposal" not in names(rec)
    assert app_mod.claude.requests == []
    assert app_mod.wa.sent == [(CHRIS, staff.WELCOME)]      # first contact: the walkthrough
    post(client, inbound(wa_id=CHRIS, text="hello", ts=int(time.time()), msg_id="s9"))
    assert app_mod.wa.sent[-1] == (CHRIS, staff.HELP)       # after that, the short help
    assert staff.window_open(app_mod.store.get_staff_windows()[CHRIS], time.time())


def test_staff_stop_start_and_status(env, with_staff):
    client, rec, _, _ = env
    now = int(time.time())
    post(client, inbound(wa_id=CHRIS, text="stop", ts=now, msg_id="s1"))
    assert app_mod.store.get_kill()        # a command works even before the walkthrough
    post(client, inbound(ts=now, msg_id="c1"))   # a customer: kill switch holds
    assert silent_reasons(rec)[-1] == "kill_switch"
    post(client, inbound(wa_id=CHRIS, text="status", ts=now, msg_id="s2"))
    assert "STOPPED" in app_mod.wa.sent[-1][1]
    post(client, inbound(wa_id=CHRIS, text="start", ts=now, msg_id="s3"))
    assert not app_mod.store.get_kill()
    post(client, inbound(wa_id=CHRIS, text="start", ts=now, msg_id="s3"))  # de-duped
    assert len([m for m in app_mod.wa.sent if m[0] == CHRIS]) == 3


def test_handover_pings_staff_by_template_outside_window(env, with_staff):
    client, rec, notes, _ = env
    app_mod.claude.queue.append(final(reply="I'll get the team to call you", intent="human_requested",
                                      escalate=True, reason="asked for a person",
                                      note="wants to speak to someone about 98765432"))
    post(client, inbound(text="can I speak to a person", ts=int(time.time())))
    ((to, name, (who, reason)),) = app_mod.wa.templates
    assert to == CHRIS and name == config.STAFF_TEMPLATE == "goji_staff_alert_v2"
    assert who == "Mei (#001)" and "98765432" not in reason and "[number]" in reason
    assert notes == []  # pinged, so no email for an ordinary handover


def test_ping_is_free_text_inside_window_and_urgent_still_emails(env, with_staff):
    client, rec, notes, _ = env
    app_mod.store.note_staff_inbound(CHRIS, time.time() - 60)
    app_mod.claude.queue.append(final(reply="Please call 995", intent="urgent", escalate=True,
                                      reason="red flag", note="chest pain"))
    post(client, inbound(text="chest pain", ts=int(time.time())))
    assert (CHRIS, staff.ping_text("Mei (#001)", "chest pain")) in app_mod.wa.sent
    assert app_mod.wa.templates == []
    assert [k for k, _ in notes] == ["urgent"]


def test_failed_ping_falls_back_to_email(env, with_staff, monkeypatch):
    client, rec, notes, _ = env
    monkeypatch.setattr(app_mod, "wa", FakeWA(template_fail=True))
    app_mod.claude.queue.append(final(reply="I'll get the team", intent="human_requested",
                                      escalate=True))
    post(client, inbound(ts=int(time.time())))
    assert [k for k, _ in notes] == ["escalated"]
    assert "staff_ping_failed" in names(rec)


def test_no_staff_numbers_means_email(env):
    client, rec, notes, _ = env
    app_mod.claude.queue.append(final(reply="I'll get the team", intent="human_requested",
                                      escalate=True))
    post(client, inbound(ts=int(time.time())))
    assert [k for k, _ in notes] == ["escalated"]


def test_echo_to_a_staff_number_is_ignored(env, with_staff):
    client, rec, _, _ = env
    post(client, echo(wa_id=CHRIS))
    assert app_mod.store.load(CHRIS).owner == ""


# --- morning summary --------------------------------------------------------------

def test_summary_build():
    now = 1_800_000_000.0
    a = ChatState(wa_id="6500000001", name="Amy Lee")
    note_outcome(a, "pricing", "answered", now - 3600)
    b = ChatState(wa_id="6500000002", name="", mode=WAITING, mode_since=now - 600,
                  pending_for_chris="weekend 4:30pm with Cheryl")
    note_outcome(b, "availability", "handed over", now - 600)
    c = ChatState(wa_id="6500000003", name="Cat")
    note_outcome(c, "booking", "failed", now - 100)
    old = ChatState(wa_id="6500000004", name="Old")
    note_outcome(old, "pricing", "answered", now - 3 * DAY)
    s = summary.build([a, b, c, old], now)
    assert (s["answered"], s["left"], s["failed"]) == (1, 1, 1)
    assert "Amy" in s["body"] and "ending 0002" in s["body"] and "Cheryl" in s["body"]
    assert "Old" not in s["body"] and "6500000002" not in s["body"]
    assert "Lee" not in s["body"]


def test_summary_quiet_day():
    s = summary.build([], 1_800_000_000.0)
    assert "quiet" in s["body"].lower() and s["answered"] == 0


def test_left_for_chris_clears_once_she_replies():
    now = 1_800_000_000.0
    st = ChatState(wa_id=CUSTOMER)
    note_outcome(st, "billing", "left", now - 600)
    assert summary.left_for_chris(st, now - DAY)
    st.last_staff_at = now - 60
    assert not summary.left_for_chris(st, now - DAY)


def test_morning_summary_route(env, with_staff):
    client, rec, _, plain = env
    assert client.post("/internal/morning-summary").status_code == 403
    app_mod.claude.queue.append(final())
    post(client, inbound(ts=int(time.time())))
    app_mod.store.note_staff_inbound(CHRIS, time.time() - 60)
    r = client.post("/internal/morning-summary", headers=ADMIN)
    assert r.json["answered"] == 1 and r.json["staff_pinged"] == 1
    (subj, body), = plain
    assert "morning summary" in subj and "Mei" in body
    assert app_mod.wa.sent[-1][0] == CHRIS and "1 chat(s) answered" in app_mod.wa.sent[-1][1]


# --- kill-switch gaps -------------------------------------------------------------

def test_reminder_confirm_respects_kill_switch(env):
    client, rec, _, _ = env
    app_mod.store.set_kill(True)
    post(client, inbound(kind="button", text="Confirm", ts=int(time.time())))
    assert app_mod.wa.sent == []
    assert silent_reasons(rec)[-1] == "kill_switch"


def booking_body(**kw):
    return {"phone": CUSTOMER, "reference": "GJ1", "date": "2026-11-24", "time": "10:00",
            "service": "Physiotherapy", "clinician_name": "Kristy Lim", "first_name": "Mei",
            "source": "web", **kw}


def test_booking_confirmed_sends_nothing_with_kill_switch(env, monkeypatch):
    client, rec, _, _ = env
    monkeypatch.setattr(config, "INTERNAL_TOKEN", "tok")
    monkeypatch.setattr(config, "CONFIRMATIONS", True)
    app_mod.store.set_kill(True)
    r = client.post("/internal/booking-confirmed", json=booking_body(),
                    headers={"X-Internal-Token": "tok"})
    assert r.json["template_sent"] is False and app_mod.wa.templates == []


def test_booking_confirmed_stays_out_of_chris_chat(env, monkeypatch):
    client, rec, _, _ = env
    monkeypatch.setattr(config, "INTERNAL_TOKEN", "tok")
    now = int(time.time())
    post(client, echo(ts=now - 3600))
    st = app_mod.store.load(CUSTOMER)
    st.history.append({"role": "customer", "text": "hi", "ts": now - 600, "id": "x"})
    st.last_customer_at = now - 600
    assert st.mode == PAUSED          # Chris wrote: hers until she resumes it
    app_mod.store.save(st)
    r = client.post("/internal/booking-confirmed", json=booking_body(),
                    headers={"X-Internal-Token": "tok"})
    assert r.json == {"matched": True, "acknowledged": False}
    assert app_mod.wa.sent == []
    assert app_mod.store.load(CUSTOMER).booked["reference"] == "GJ1"


# --- hash salt --------------------------------------------------------------------

def test_default_salt_refused_on_a_deployed_run(monkeypatch):
    monkeypatch.setattr(events, "_SALT", events.DEFAULT_SALT)
    monkeypatch.setattr(config, "STATE_BACKEND", "firestore")
    monkeypatch.setattr(config, "LOG_EVENTS", False)
    assert not events.salt_ok() and not events.check_salt()
    assert events.safe_chat_key(CUSTOMER) is None
    assert events.record("inbound", CUSTOMER)["chat_key"] is None


def test_default_salt_fine_locally_and_real_salt_fine_deployed(monkeypatch):
    monkeypatch.setattr(config, "LOG_EVENTS", False)
    monkeypatch.setattr(events, "_SALT", events.DEFAULT_SALT)
    monkeypatch.setattr(config, "STATE_BACKEND", "memory")
    assert events.record("inbound", CUSTOMER)["chat_key"] == events.chat_key(CUSTOMER)
    monkeypatch.setattr(events, "_SALT", "a-real-secret")
    monkeypatch.setattr(config, "STATE_BACKEND", "firestore")
    assert events.safe_chat_key(CUSTOMER) == events.chat_key(CUSTOMER)


# --- forget -----------------------------------------------------------------------

def test_forget_deletes_chat_and_late_changes(env):
    client, rec, _, _ = env
    app_mod.claude.queue.append(final())
    post(client, inbound(ts=int(time.time())))
    key = events.chat_key(CUSTOMER)
    app_mod.store.add_late_change(key, {"at": 1, "kind": "reschedule", "hours": 3})
    assert client.post(f"/admin/chats/{CUSTOMER}/forget").status_code == 403
    r = client.post(f"/admin/chats/{CUSTOMER}/forget", headers=ADMIN)
    assert r.json["forgotten"]
    assert app_mod.store.load(CUSTOMER).history == []
    assert app_mod.store.get_late_changes(key) == []
    assert "forgotten" in names(rec)


def test_summary_lists_paused_chats_with_resume_hint():
    now = 1_800_000_000.0
    p1 = ChatState(wa_id="6500000011", name="Ann", code="004", mode=PAUSED, mode_since=now - DAY)
    p2 = ChatState(wa_id="6500000012", name="", code="007", mode=PAUSED, mode_since=now - 9 * DAY)
    s = summary.build([], now, paused=[p1, p2])
    assert s["paused"] == 2
    assert "ending 0012 (#007)" in s["body"] and "Ann (#004)" in s["body"]
    assert s["body"].index("#007") < s["body"].index("#004")      # oldest first
    assert "RESUME 004" in s["body"] and "RESUME" in s["line"]


def test_welcome_covers_the_walkthrough():
    for must in ("RESUME 004", "PAUSE", "STOP", "START", "STATUS", "7:30", "go quiet"):
        assert must in staff.WELCOME
    assert len(staff.WELCOME) < 4096                       # one WhatsApp message
