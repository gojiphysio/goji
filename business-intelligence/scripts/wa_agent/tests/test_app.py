"""The whole flow through the webhook, with fakes for Claude and WhatsApp.
Handlers run inline (no thread pool) and the pre-send hold is instant, so a
'person replies during the hold' is simulated by an echo inside _sleep."""
import hashlib
import hmac
import json

import pytest

from wa_agent import app as app_mod
from wa_agent import config, events, notify
from wa_agent.policy import AGENT, HUMAN, WAITING
from wa_agent.state import MemoryStore
from wa_agent.whatsapp import parse_webhook

from .fakes import FakeClaude, FakeWhatsApp, final
from .payloads import echo, inbound, status

CUSTOMER = "6591234567"


@pytest.fixture
def env(monkeypatch):
    rec, notes = [], []
    monkeypatch.setattr(app_mod, "store", MemoryStore())
    monkeypatch.setattr(app_mod, "wa", FakeWhatsApp())
    monkeypatch.setattr(app_mod, "claude", FakeClaude())
    monkeypatch.setattr(app_mod, "_submit", lambda fn, *a: fn(*a))
    monkeypatch.setattr(app_mod, "_sleep", lambda s: None)
    monkeypatch.setattr(events, "record", lambda e, w, **f: rec.append((e, f)) or {})
    monkeypatch.setattr(notify, "send", lambda kind, **kw: notes.append((kind, kw)))
    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        yield c, rec, notes


def post(client, body):
    raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
    return client.post("/webhook", data=raw, content_type="application/json",
                       headers={"X-Hub-Signature-256": sig})


def names(rec):
    return [e for e, _ in rec]


def test_handshake():
    with app_mod.app.test_client() as c:
        ok = c.get("/webhook?hub.mode=subscribe&hub.verify_token=verify-me&hub.challenge=42")
        assert ok.status_code == 200 and ok.data == b"42"
        assert c.get("/webhook?hub.mode=subscribe&hub.verify_token=nope&hub.challenge=1"
                     ).status_code == 403


def test_unsigned_webhook_rejected(env):
    client, rec, _ = env
    r = client.post("/webhook", json=inbound())
    assert r.status_code == 403 and rec == []


def test_faq_is_answered(env):
    client, rec, _ = env
    app_mod.claude.queue.append(final())
    assert post(client, inbound()).status_code == 200
    assert app_mod.wa.sent == [(CUSTOMER, "Hi! We're open Mon-Sat 8am-8pm.")]
    assert app_mod.wa.typing == ["wamid.in1"]
    assert names(rec) == ["inbound", "proposal", "sent"]
    state = app_mod.store.load(CUSTOMER)
    assert [h["role"] for h in state.history] == ["customer", "agent"]


def test_duplicate_delivery_is_handled_once(env):
    client, rec, _ = env
    app_mod.claude.queue.append(final())
    post(client, inbound())
    post(client, inbound())
    assert len(app_mod.wa.sent) == 1


def on_nth_sleep(n, action):
    """_sleep stand-in that runs `action` on its nth call. Call 1 is the
    debounce, call 2 the pre-send hold."""
    calls = {"n": 0}

    def sleep(_):
        calls["n"] += 1
        if calls["n"] == n:
            action()
    return sleep


def chris_replies():
    # Nested Flask requests can't run inside a request, so "meanwhile" events
    # go straight to the handlers the webhook would have dispatched.
    app_mod.handle_echo(parse_webhook(echo())[0])


def customer_adds(text="also, do you take Medisave?"):
    def act():
        ev = parse_webhook(inbound(msg_id="wamid.in2", text=text, ts=1763431205))[0]
        app_mod.handle_inbound(ev, ev.ts)
    return act


def test_person_replies_during_hold_so_agent_stays_quiet(env, monkeypatch):
    client, rec, _ = env
    app_mod.claude.queue.append(final())
    monkeypatch.setattr(app_mod, "_sleep", on_nth_sleep(2, chris_replies))
    post(client, inbound())
    assert app_mod.wa.sent == []
    assert ("superseded", {"reason": "human_replied"}) in rec
    assert app_mod.store.load(CUSTOMER).mode == HUMAN


def test_person_replies_during_debounce_so_model_is_never_called(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(app_mod, "_sleep", on_nth_sleep(1, chris_replies))
    post(client, inbound())
    assert app_mod.claude.requests == [] and app_mod.wa.sent == []
    assert ("silent", {"reason": "human_has_chat"}) in rec


def test_burst_of_messages_costs_one_model_call(env, monkeypatch):
    client, rec, _ = env
    app_mod.claude.queue.append(final(reply="Yes, and here's the price."))
    monkeypatch.setattr(app_mod, "_sleep", on_nth_sleep(1, customer_adds()))
    post(client, inbound(text="hi, quick question"))
    assert len(app_mod.claude.requests) == 1
    assert app_mod.wa.sent == [(CUSTOMER, "Yes, and here's the price.")]
    assert ("superseded", {"reason": "debounced"}) in rec
    # the one call saw both lines
    last = app_mod.claude.requests[0]["messages"][-1]["content"][0]["text"]
    assert "hi, quick question\nalso, do you take Medisave?" in last


def test_newer_message_during_hold_supersedes_older_run(env, monkeypatch):
    client, rec, _ = env
    app_mod.claude.queue.extend([final(reply="first"), final(reply="second")])
    monkeypatch.setattr(app_mod, "_sleep", on_nth_sleep(2, customer_adds()))
    post(client, inbound())
    assert app_mod.wa.sent == [(CUSTOMER, "second")]  # one reply, to both lines
    assert ("superseded", {"reason": "newer_customer_message"}) in rec


def test_thanks_after_our_reply_needs_no_model_call(env):
    client, rec, _ = env
    app_mod.claude.queue.append(final())
    post(client, inbound())
    post(client, inbound(msg_id="wamid.in2", text="Thank you! 🙏"))
    assert len(app_mod.claude.requests) == 1 and len(app_mod.wa.sent) == 1
    assert ("silent", {"reason": "acknowledgement"}) in rec


def test_after_chris_replies_agent_is_silent(env):
    client, rec, _ = env
    post(client, echo())
    post(client, inbound(msg_id="wamid.in2"))
    assert app_mod.wa.sent == []
    assert app_mod.claude.requests == []  # never even asked the model
    assert ("silent", {"reason": "human_has_chat"}) in rec


def test_escalation_sends_holding_reply_hands_over_and_notifies(env):
    client, rec, notes = env
    app_mod.claude.queue.append(final(reply="I'll get Chris to call you back today.",
                                      intent="human_requested", escalate=True,
                                      reason="complaint about a session"))
    post(client, inbound(text="I'd like to speak to Chris about my last session"))
    assert app_mod.wa.sent == [(CUSTOMER, "I'll get Chris to call you back today.")]
    assert app_mod.store.load(CUSTOMER).mode == WAITING
    assert notes[0][0] == "escalated"
    assert ("mode", {"mode_from": AGENT, "mode_to": WAITING,
                     "reason": "escalated:complaint about a session"}) in rec


def test_urgent_notifies_as_urgent(env):
    client, _, notes = env
    app_mod.claude.queue.append(final(reply="Please call 995 now.", intent="urgent",
                                      escalate=True, reason="bleeding"))
    post(client, inbound(text="I'm 30 weeks and bleeding a lot"))
    assert app_mod.wa.sent and notes[0][0] == "urgent"


def test_draft_sends_nothing_and_notifies(env):
    client, rec, notes = env
    app_mod.claude.queue.append(final(intent="cancel"))
    post(client, inbound(text="please cancel my Friday 3pm"))
    assert app_mod.wa.sent == [] and notes[0][0] == "drafted"
    assert app_mod.store.load(CUSTOMER).mode == AGENT


def test_kill_switch_blocks_everything(env):
    client, rec, _ = env
    h = {"X-Admin-Token": "admin-token"}
    assert client.post("/admin/kill", json={"on": True}, headers=h).status_code == 200
    post(client, inbound())
    assert app_mod.wa.sent == [] and ("silent", {"reason": "kill_switch"}) in rec


def test_admin_takeover_handback_and_auth(env):
    client, _, _ = env
    assert client.post(f"/admin/chats/{CUSTOMER}/takeover").status_code == 403
    h = {"X-Admin-Token": "admin-token"}
    assert client.post(f"/admin/chats/{CUSTOMER}/takeover", headers=h).json["mode"] == HUMAN
    assert client.post(f"/admin/chats/{CUSTOMER}/handback", headers=h).json["mode"] == AGENT
    app_mod.claude.queue.append(final())
    post(client, inbound())
    assert len(app_mod.wa.sent) == 1


def test_send_failure_notifies_staff(env, monkeypatch):
    client, rec, notes = env
    monkeypatch.setattr(app_mod, "wa", FakeWhatsApp(fail=True))
    app_mod.claude.queue.append(final())
    post(client, inbound())
    assert "send_failed" in names(rec) and notes[0][0] == "escalated"


def test_status_is_logged_without_text(env):
    client, rec, _ = env
    post(client, status())
    assert rec == [("status", {"wa_msg_id": "wamid.out1", "status": "delivered",
                               "status_ts": 1763431230.0})]


def test_url_token_route(env, monkeypatch):
    client, _, _ = env
    assert client.post("/webhook/anything", json=inbound()).status_code == 403  # disabled
    monkeypatch.setattr(config, "WA_WEBHOOK_URL_TOKEN", "s3cret-long-token")
    assert client.post("/webhook/wrong", json=inbound()).status_code == 403
    app_mod.claude.queue.append(final())
    assert client.post("/webhook/s3cret-long-token", json=inbound()).status_code == 200
    assert len(app_mod.wa.sent) == 1


# --- learning signals ---------------------------------------------------------

def test_chris_sending_the_draft_is_scored_on_her_reply(env):
    client, rec, _ = env
    app_mod.claude.queue.append(final(reply="Sure, I've cancelled Friday 3pm.", intent="cancel"))
    post(client, inbound(text="please cancel Friday 3pm"))
    post(client, echo(text="Sure, I've cancelled Friday 3pm."))
    ev = dict(rec)["echo"]
    assert ev["intent"] == "cancel" and ev["draft_outcome"] == "sent_unchanged"
    assert "rescue" not in ev


def test_chris_stepping_into_an_auto_chat_is_a_rescue(env):
    client, rec, _ = env
    app_mod.claude.queue.append(final(intent="pricing"))
    post(client, inbound())
    post(client, echo(text="Sorry, that's not right, let me explain"))
    ev = dict(rec)["echo"]
    assert ev == {**ev, "rescue": True, "intent": "pricing"}


def test_echo_after_escalation_is_a_planned_handover_not_a_rescue(env):
    client, rec, _ = env
    app_mod.claude.queue.append(final(reply="Chris will get back to you today.",
                                      intent="human_requested", escalate=True, reason="wants Chris"))
    post(client, inbound(text="Can Chris call me?"))
    post(client, echo())
    assert "rescue" not in dict(rec)["echo"]


def test_repeated_rescues_demote_the_intent_to_draft(env):
    client, rec, notes = env
    for i in range(3):
        app_mod.claude.queue.append(final(intent="pricing"))
        post(client, inbound(msg_id=f"wamid.in{i}"))
        post(client, echo(msg_id=f"wamid.echo{i}"))
        app_mod.store.save(app_mod.store.load(CUSTOMER).__class__(wa_id=CUSTOMER))  # hand back
    assert ("autonomy", {"intent": "pricing",
                         "reason": "demoted:3_rescues_in_last_20"}) in rec
    assert any(k == "demoted" for k, _ in notes)
    sent_before = len(app_mod.wa.sent)
    app_mod.claude.queue.append(final(intent="pricing"))
    post(client, inbound(msg_id="wamid.in9"))
    assert len(app_mod.wa.sent) == sent_before            # now drafted, not sent
    assert rec[-1][0] == "drafted"


def test_feedback_link_records_a_rating(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(config, "FEEDBACK_SECRET", "k")
    from wa_agent import learning
    sig = learning.feedback_sig("0123456789abcdef", 1700, "down")
    assert client.get(f"/feedback?c=0123456789abcdef&t=1700&r=down&s={sig}").status_code == 200
    assert ("feedback", {"key": "0123456789abcdef", "rating": "down"}) in rec
    assert client.get("/feedback?c=0123456789abcdef&t=1700&r=up&s=" + sig).status_code == 403


def test_test_mode_shows_drafts_to_the_tester_only_locally(env, monkeypatch):
    client, _, _ = env
    monkeypatch.setattr(config, "TEST_SHOW_DRAFTS", True)
    monkeypatch.setattr(config, "STATE_BACKEND", "memory")
    app_mod.claude.queue.append(final(reply="Draft text", intent="cancel"))
    post(client, inbound(text="please cancel Friday 3pm"))
    assert len(app_mod.wa.sent) == 1 and "TEST MODE" in app_mod.wa.sent[0][1]
    assert [h["role"] for h in app_mod.store.load(CUSTOMER).history] == ["customer"]
    monkeypatch.setattr(config, "STATE_BACKEND", "firestore")
    app_mod.claude.queue.append(final(reply="Draft text", intent="cancel"))
    post(client, inbound(msg_id="wamid.in2", text="and Saturday's too"))
    assert len(app_mod.wa.sent) == 1                      # never on a deployed service


def test_is_this_chris_answers_as_front_desk_and_sends_chris_an_fyi(env):
    client, rec, notes = env
    app_mod.claude.queue.append(final(
        reply="Hi! This is Goji's front desk. I'll let Chris know you asked for her. "
              "Is there a message I can pass along?", intent="person_check"))
    post(client, inbound(text="Hi is this Chris"))
    assert len(app_mod.wa.sent) == 1 and "front desk" in app_mod.wa.sent[0][1]
    assert [k for k, _ in notes] == ["fyi"]
    assert app_mod.store.load(CUSTOMER).mode == AGENT      # the agent keeps the chat


def test_rescheduling_replies_and_tells_chris_to_move_it(env):
    client, _, notes = env
    app_mod.claude.queue.append(final(reply="Sure! Thu 10am or Fri 2pm are open. "
                                            "The team will move it and confirm.",
                                      intent="reschedule"))
    post(client, inbound(text="can I move my Tuesday appointment?"))
    assert len(app_mod.wa.sent) == 1 and [k for k, _ in notes] == ["reschedule"]
    assert app_mod.store.load(CUSTOMER).mode == AGENT


# --- waiting for Chris ------------------------------------------------------------

def _hand_over(client, note="wants a 4:30pm slot with Cheryl"):
    app_mod.claude.queue.append(final(reply="Chris will get back to you today.",
                                      intent="availability", escalate=True,
                                      reason="no 4:30pm slot", note=note))
    post(client, inbound(msg_id="wamid.h1", text="any 4:30pm with Cheryl?"))


def test_after_handover_the_agent_keeps_answering_other_questions(env):
    client, rec, _ = env
    _hand_over(client)
    app_mod.claude.queue.append(final(reply="We're open Mon-Sat 8am-8pm.", intent="location_hours"))
    post(client, inbound(msg_id="wamid.h2", text="what are your hours?"))
    assert app_mod.wa.sent[-1] == (CUSTOMER, "We're open Mon-Sat 8am-8pm.")
    assert app_mod.store.load(CUSTOMER).mode == WAITING
    # the model is told what's pending, so it won't answer that topic
    last_turn = app_mod.claude.requests[-1]["messages"][-1]["content"][0]["text"]
    assert "waiting for Chris on: wants a 4:30pm slot with Cheryl" in last_turn


def test_once_chris_replies_the_agent_steps_out(env):
    client, rec, _ = env
    _hand_over(client)
    post(client, echo(text="Hi! Cheryl can do 4:30pm on Friday"))
    state = app_mod.store.load(CUSTOMER)
    assert state.mode == HUMAN and state.pending_for_chris == ""
    sent = len(app_mod.wa.sent)
    post(client, inbound(msg_id="wamid.h3", text="great, thanks! also what are your hours?"))
    assert len(app_mod.wa.sent) == sent
    assert "rescue" not in dict(rec)["echo"]          # a planned handover, not a rescue


def test_a_second_topic_for_chris_adds_to_the_pending_list(env):
    client, _, notes = env
    _hand_over(client)
    app_mod.claude.queue.append(final(reply="I've passed that on to Chris too.",
                                      intent="human_requested", escalate=True,
                                      reason="invoice", note="wants an invoice resent"))
    post(client, inbound(msg_id="wamid.h4", text="also can Chris resend my invoice?"))
    state = app_mod.store.load(CUSTOMER)
    assert state.mode == WAITING
    assert state.pending_for_chris == "wants a 4:30pm slot with Cheryl; wants an invoice resent"
    assert [k for k, _ in notes] == ["escalated", "escalated"]


def test_red_flags_and_sensitive_topics_go_fully_quiet(env):
    client, _, notes = env
    app_mod.claude.queue.append(final(reply="I'm so sorry. Chris will reach out to you.",
                                      intent="sensitive", escalate=True, reason="loss"))
    post(client, inbound(text="I lost the baby last week"))
    assert app_mod.store.load(CUSTOMER).mode == HUMAN and notes[0][0] == "sensitive"


def test_waiting_hands_back_after_a_quiet_day(env):
    from wa_agent.policy import apply_idle_handback
    state = app_mod.store.load(CUSTOMER)
    state.mode, state.mode_since, state.pending_for_chris = WAITING, 0.0, "x"
    assert apply_idle_handback(state, 10**9)
    assert state.mode == AGENT and state.pending_for_chris == ""


def test_returning_patient_context_reaches_the_model_and_is_cached(env, monkeypatch):
    client, rec, _ = env
    calls = []
    monkeypatch.setattr(app_mod.tools, "patient_context",
                        lambda wa_id: calls.append(wa_id) or
                        {"returning": True, "first_name": "Sarah", "patients_on_number": 1,
                         "next_appointment": None, "last_visit": "2026-10-02"})
    app_mod.claude.queue.extend([final(), final()])
    post(client, inbound())
    post(client, inbound(msg_id="wamid.in2", text="and Saturdays?"))
    turn = app_mod.claude.requests[0]["messages"][-1]["content"][0]["text"]
    assert "patient record: returning patient; record first name Sarah" in turn
    assert calls == [CUSTOMER]                              # looked up once, then cached
    assert ("patient_lookup", {"reason": "returning"}) in rec


def test_late_changes_are_remembered_so_the_waiver_is_offered_once(env):
    client, rec, _ = env
    late = lambda: final(reply="draft", intent="cancel")
    app_mod.claude.queue.append(late())
    app_mod.claude.queue[-1].content[0].text = app_mod.claude.queue[-1].content[0].text.replace(
        '"staff_note"', '"hours_to_appointment": 3, "staff_note"')
    post(client, inbound(text="sorry can't make it today"))
    first_turn = app_mod.claude.requests[0]["messages"][-1]["content"][0]["text"]
    assert "first-time waiver applies" in first_turn
    assert any(e == "late_change" for e, _ in rec)
    app_mod.claude.queue.append(final(reply="ok", intent="faq"))
    post(client, inbound(msg_id="wamid.in2", text="another question"))
    second_turn = app_mod.claude.requests[1]["messages"][-1]["content"][0]["text"]
    assert "1 earlier late change(s) on record" in second_turn
