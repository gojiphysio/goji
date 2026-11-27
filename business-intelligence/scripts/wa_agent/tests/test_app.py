"""The whole flow through the webhook, with fakes for Claude and WhatsApp.
Handlers run inline (no thread pool) and the pre-send hold is instant, so a
'person replies during the hold' is simulated by an echo inside _sleep."""
import base64
import hashlib
import hmac
import json
import time

import pytest

from wa_agent import app as app_mod
from wa_agent import config, events, notify
from wa_agent.policy import AGENT, HUMAN, PAUSED, WAITING
from wa_agent.state import MemoryStore
from wa_agent.whatsapp import parse_webhook

from .fakes import FakeClaude, FakeWhatsApp, final
from .payloads import echo, inbound, reaction, status

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
    assert app_mod.store.load(CUSTOMER).mode == PAUSED


def test_person_replies_during_debounce_so_model_is_never_called(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(app_mod, "_sleep", on_nth_sleep(1, chris_replies))
    post(client, inbound())
    assert app_mod.claude.requests == [] and app_mod.wa.sent == []
    assert ("silent", {"reason": "paused"}) in rec


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


def test_first_thanks_gets_one_warm_closer_then_silence(env):
    client, rec, _ = env
    app_mod.claude.queue.extend([final(), final(reply="You're welcome! Were you thinking of "
                                                     "coming in?", intent="greeting")])
    post(client, inbound())
    post(client, inbound(msg_id="wamid.in2", text="Thank you! 🙏"))
    assert len(app_mod.wa.sent) == 2 and "coming in" in app_mod.wa.sent[-1][1]
    post(client, inbound(msg_id="wamid.in3", text="ok thanks!"))
    assert len(app_mod.claude.requests) == 2 and len(app_mod.wa.sent) == 2   # loop ends
    assert ("silent", {"reason": "acknowledgement"}) in rec


@pytest.mark.parametrize("emoji", ["👍", "👍🏽", "❤️", "😊", "🙏", "😂", ""])
def test_positive_reaction_gets_no_reply_and_no_ping(env, emoji):
    client, rec, notes = env
    app_mod.claude.queue.append(final())
    post(client, inbound())
    sent, history = len(app_mod.wa.sent), len(app_mod.store.load(CUSTOMER).history)
    post(client, reaction(emoji=emoji))
    assert len(app_mod.claude.requests) == 1 and len(app_mod.wa.sent) == sent
    assert notes == [] and ("silent", {"reason": "reaction"}) in rec
    assert len(app_mod.store.load(CUSTOMER).history) == history


@pytest.mark.parametrize("emoji", ["👎", "😡", "😢", "😮", "🤔"])
def test_negative_or_neutral_reaction_pings_staff(env, emoji):
    client, rec, notes = env
    app_mod.claude.queue.append(final(reply="We open at 8am."))
    post(client, inbound())   # our reply is wamid.out1, the message reacted to
    post(client, reaction(emoji=emoji))
    post(client, reaction(emoji=emoji))   # Meta's retry: one ping only
    assert len(app_mod.claude.requests) == 1 and len(app_mod.wa.sent) == 1
    [(kind, kw)] = notes      # no staff number set: the email is the ping
    assert kind == "reaction" and kw["staff_note"] == f'reacted {emoji} to "We open at 8am"'
    assert ("escalated", {"reason": "reaction"}) in rec


def test_negative_reaction_in_chrises_chat_pings_nobody(env):
    client, rec, notes = env
    app_mod.claude.queue.append(final())
    post(client, inbound())
    post(client, echo())      # Chris has the chat now
    post(client, reaction(emoji="😡"))
    assert notes == [] and ("silent", {"reason": "reaction"}) in rec


def test_reaction_after_a_text_does_not_supersede_it(env, monkeypatch):
    client, rec, _ = env
    app_mod.claude.queue.append(final(reply="We open at 8am."))
    def react():
        ev = parse_webhook(reaction())[0]
        app_mod.handle_inbound(ev, ev.ts)
    monkeypatch.setattr(app_mod, "_sleep", on_nth_sleep(1, react))
    post(client, inbound())
    assert app_mod.wa.sent == [(CUSTOMER, "We open at 8am.")]


def test_staff_reaction_to_a_ping_gets_no_reply(env, monkeypatch):
    client, rec, notes = env
    monkeypatch.setattr(config, "STAFF", frozenset({"6591110000"}))
    post(client, reaction(wa_id="6591110000"))
    assert app_mod.wa.sent == [] and app_mod.claude.requests == [] and rec == []


def test_business_app_reaction_does_not_pause_the_chat(env):
    client, rec, _ = env
    app_mod.claude.queue.append(final())
    post(client, inbound())
    post(client, reaction(echoed=True))
    assert app_mod.store.load(CUSTOMER).mode == AGENT and "echo" not in names(rec)


def test_thanks_after_a_booking_needs_no_reply(env):
    client, rec, _ = env
    app_mod.claude.queue.append(final())
    post(client, inbound())
    state = app_mod.store.load(CUSTOMER)
    import time as _t
    state.booked = {"reference": "GOJI-1", "at": _t.time()}
    app_mod.store.save(state)
    post(client, inbound(msg_id="wamid.in2", text="thanks!"))
    assert len(app_mod.claude.requests) == 1


def test_after_chris_replies_agent_is_silent(env):
    client, rec, _ = env
    post(client, echo())
    post(client, inbound(msg_id="wamid.in2"))
    assert app_mod.wa.sent == []
    assert app_mod.claude.requests == []  # never even asked the model
    assert ("silent", {"reason": "paused"}) in rec


def test_escalation_sends_holding_reply_hands_over_and_notifies(env):
    client, rec, notes = env
    app_mod.claude.queue.append(final(reply="Hi Mei, Chris here. Sorry to hear that, when "
                                            "is a good time to call?",
                                      holding="I've passed this to Chris and she'll call you "
                                              "back today.",
                                      intent="human_requested", escalate=True,
                                      reason="complaint about a session"))
    post(client, inbound(text="I'd like to speak to Chris about my last session"))
    # The customer gets the holding reply; Chris gets the draft answer to send.
    assert app_mod.wa.sent == [(CUSTOMER, "I've passed this to Chris and she'll call you "
                                          "back today.")]
    assert app_mod.store.load(CUSTOMER).mode == WAITING
    assert notes[0][0] == "escalated"
    assert notes[0][1]["suggested_reply"].startswith("Hi Mei, Chris here")
    assert ("mode", {"mode_from": AGENT, "mode_to": WAITING,
                     "reason": "escalated:complaint about a session"}) in rec


def test_urgent_notifies_as_urgent(env):
    client, _, notes = env
    app_mod.claude.queue.append(final(reply="Please call 995 now.", intent="urgent",
                                      escalate=True, reason="bleeding"))
    post(client, inbound(text="I'm 30 weeks and bleeding a lot"))
    assert app_mod.wa.sent and notes[0][0] == "urgent"
    assert app_mod.wa.sent[-1][1] == "Please call 995 now."   # the safety reply goes out at once


def test_draft_sends_nothing_and_notifies(env):
    client, rec, notes = env
    app_mod.claude.queue.append(final(intent="billing"))
    post(client, inbound(text="can you resend my invoice?"))
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
    app_mod.claude.queue.append(final(reply="Draft text", intent="billing"))
    post(client, inbound(text="can you resend my invoice?"))
    assert len(app_mod.wa.sent) == 1 and "TEST MODE" in app_mod.wa.sent[0][1]
    assert [h["role"] for h in app_mod.store.load(CUSTOMER).history] == ["customer"]
    monkeypatch.setattr(config, "STATE_BACKEND", "firestore")
    app_mod.claude.queue.append(final(reply="Draft text", intent="billing"))
    post(client, inbound(msg_id="wamid.in2", text="and last month's too"))
    assert len(app_mod.wa.sent) == 1                      # never on a deployed service


def test_is_this_chris_answers_as_front_desk_without_emailing_chris(env):
    client, rec, notes = env
    app_mod.claude.queue.append(final(
        reply="Hi! This is Goji's front desk. I'll let Chris know you asked for her. "
              "Is there a message I can pass along?", intent="person_check"))
    post(client, inbound(text="Hi is this Chris"))
    assert len(app_mod.wa.sent) == 1 and "front desk" in app_mod.wa.sent[0][1]
    assert notes == []                                     # Chris hears only if they leave a message
    assert app_mod.store.load(CUSTOMER).mode == AGENT      # the agent keeps the chat


def test_a_routine_move_is_done_by_the_agent_without_emailing_chris(env, monkeypatch):
    client, rec, notes = env
    moved = []
    monkeypatch.setattr(app_mod.booking_client, "move", lambda m, wa_id, patient_id="":
                        moved.append(m) or {"ok": True, "reference": "GOJI-MV1", "dry_run": True,
                                            "clinician_name": "Kristy Ng", **{k: m[k] for k in
                                            ("old_date", "old_time", "new_date", "new_time")}})
    mv = {"old_date": "2026-11-25", "old_time": "10:00", "new_date": "2026-11-27",
          "new_time": "14:00"}
    app_mod.claude.queue.append(_final_with("Shall I move your Tue 10am to Thu 2pm?",
                                            intent="reschedule", move=mv))
    post(client, inbound(text="can I move Tuesday's appointment to Thursday 2pm?"))
    assert moved == [] and app_mod.store.load(CUSTOMER).pending_move["new_time"] == "14:00"
    app_mod.claude.queue.append(_final_with("Moving it now!", intent="reschedule", move=mv,
                                            confirm_move=True))
    post(client, inbound(msg_id="wamid.in2", text="yes"))
    assert len(moved) == 1
    assert app_mod.wa.sent[-1][1].startswith(
        "Done! Your appointment has moved from Wed 25 Nov, 10:00am to Fri 27 Nov, 2:00pm with Kristy")
    assert notes == []
    assert ("moved", {"intent": "reschedule", "reason": "dry_run"}) in rec


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
    assert state.mode == PAUSED and state.pending_for_chris == ""
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
    assert "patient record: a patient record is linked to this number (" in turn
    assert "record first name Sarah" in turn
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


def test_a_document_is_read_into_the_chat_without_an_email(env):
    client, _, notes = env
    app_mod.wa.media = (b"Referral: 12yo with scoliosis, please assess", "text/plain")
    body = inbound(kind="document")
    body["entry"][0]["changes"][0]["value"]["messages"][0]["document"].update(
        {"filename": "referral.txt", "mime_type": "text/plain"})
    app_mod.claude.queue.append(final(reply="Thanks for sending the referral!",
                                      intent="service_fit"))
    post(client, body)
    stored = app_mod.store.load(CUSTOMER).history[0]["text"]
    assert "[sent a document: referral.txt]" in stored and "scoliosis" in stored
    assert notes == []                    # read and used: nothing for the team to do


def _photo(msg_id="wamid.in1", ts=1763431200):
    body = inbound(kind="image", msg_id=msg_id, ts=ts)
    body["entry"][0]["changes"][0]["value"]["messages"][0]["image"]["mime_type"] = "image/jpeg"
    return body


def test_the_model_sees_the_photo(env):
    client, _, notes = env
    app_mod.wa.media = (b"\xff\xd8jpeg", "image/jpeg")
    app_mod.claude.queue.append(final(reply="Thanks for sending Dr Lim's referral!",
                                      intent="service_fit"))
    post(client, _photo())
    [req] = app_mod.claude.requests
    [img] = [b for m in req["messages"] for b in m["content"] if b["type"] == "image"]
    assert img["source"] == {"type": "base64", "media_type": "image/jpeg",
                             "data": base64.b64encode(b"\xff\xd8jpeg").decode()}
    line = app_mod.store.load(CUSTOMER).history[0]
    assert line["text"] == "[sent a photo]" and line["media"] == {"id": "media1",
                                                                  "mime": "image/jpeg"}
    assert notes == []                    # used it: no ping


def test_a_photo_it_cant_use_pings_staff(env, monkeypatch):
    # 25 Nov 2026: the agent told a customer "the team will take a look" at her
    # referral photos and nobody was told.
    client, rec, notes = env
    monkeypatch.setattr(config, "STAFF", frozenset({"6591110000"}))
    app_mod.store.note_staff_inbound("6591110000", time.time() - 60)  # her 24h window
    app_mod.wa.download_media = lambda media_id: (_ for _ in ()).throw(OSError("expired"))
    app_mod.claude.queue.append(final(reply="Thanks! The team will take a look.",
                                      intent="media_received"))
    post(client, _photo())
    req = app_mod.claude.requests[0]
    assert not [b for m in req["messages"] for b in m["content"] if b["type"] == "image"]
    [to_customer] = [s for s in app_mod.wa.sent if s[0] == CUSTOMER]
    assert to_customer[1] == "Thanks! The team will take a look."
    [ping] = [s for s in app_mod.wa.sent if s[0] == "6591110000"]
    assert "sent something I couldn't use*" in ping[1]
    assert notes == []                    # the WhatsApp ping, no email
    assert app_mod.store.load(CUSTOMER).mode == AGENT   # the agent keeps the chat


def test_photos_sent_together_get_one_ping(env):
    client, _, notes = env
    for i in range(2):
        app_mod.claude.queue.append(final(reply="Thanks! The team will take a look.",
                                          intent="media_received"))
        post(client, _photo(msg_id=f"wamid.img{i}", ts=1763431200 + 60 * i))
    assert len([s for s in app_mod.wa.sent if s[0] == CUSTOMER]) == 2
    assert [k for k, _ in notes] == ["media"]


def test_a_text_message_pings_nobody(env):
    client, _, notes = env
    app_mod.claude.queue.append(final(reply="We open at 8am."))
    post(client, inbound())
    assert notes == []


# --- direct booking -----------------------------------------------------------

import json as _json

BOOK = {"service": "physiotherapy", "date": "2026-11-26", "time": "10:00", "options": "", "for_whom": "self", "booked_by": "", "patient_age": "",
        "clinician": "Kristy", "physio_focus": "", "variant": "", "format": "clinic",
        "full_name": "Charles Tan", "email": "", "address": "", "notes": ""}


def _final_with(reply, intent="booking", **extra):
    r = final(reply=reply, intent=intent)
    body = _json.loads(r.content[0].text)
    body.update(extra)
    r.content[0].text = _json.dumps(body)
    return r


def test_booking_needs_a_yes_in_a_later_message(env, monkeypatch):
    client, rec, _ = env
    calls = []
    monkeypatch.setattr(app_mod.booking_client, "book", lambda b, wa_id, patient_id="": calls.append({**b, "_pid": patient_id}) or
                        {"ok": True, "reference": "GOJI-AB12CD", "clinician_name": "Kristy Ng",
                         "service": "Physiotherapy", "date": b["date"], "time": b["time"],
                         "dry_run": True})
    app_mod.claude.queue.append(_final_with(
        "Shall I book Thu 26 Nov, 10:00am with Kristy for Charles Tan?", booking=BOOK))
    post(client, inbound(text="book me Thursday 10am with Kristy, I'm Charles Tan"))
    assert calls == [] and app_mod.store.load(CUSTOMER).pending_booking["time"] == "10:00"
    app_mod.claude.queue.append(_final_with("Booking that now!", booking=BOOK,
                                            confirm_booking=True))
    post(client, inbound(msg_id="wamid.in2", text="yes please"))
    assert len(calls) == 1 and calls[0]["full_name"] == "Charles Tan"
    sent = app_mod.wa.sent[-1][1]
    assert sent.startswith("All booked! Thu 26 Nov, 10:00am with Kristy (ref GOJI-AB12CD)")
    assert "dry run" in sent
    state = app_mod.store.load(CUSTOMER)
    assert state.booked["reference"] == "GOJI-AB12CD" and state.pending_booking == {}
    assert state.patient_at == 0.0          # look the number up again: it may be a patient now
    assert ("booked", {"intent": "booking", "reason": "dry_run"}) in rec


def _age_pending_booking(seconds):
    state = app_mod.store.load(CUSTOMER)
    state.pending_booking = {**state.pending_booking,
                             "at": state.pending_booking["at"] - seconds}
    app_mod.store.save(state)


def test_a_pick_hours_after_the_offer_still_books(env, monkeypatch):
    """25 Nov 2026: a customer picked a time 32 minutes after it was offered
    (waiting on the team's answer) and the 30-minute window had closed. The
    offer now stays open for a day; goji-booking checks the slot live."""
    client, rec, _ = env
    calls = []
    monkeypatch.setattr(app_mod.booking_client, "book", lambda b, wa_id, patient_id="": calls.append(b) or
                        {"ok": True, "reference": "GOJI-AB12CD", "clinician_name": "Kristy Ng",
                         "service": "Physiotherapy", "date": b["date"], "time": b["time"],
                         "dry_run": True})
    app_mod.claude.queue.append(_final_with(
        "Shall I book Thu 26 Nov, 10:00am with Kristy for Charles Tan?", booking=BOOK))
    post(client, inbound(text="book me Thursday 10am with Kristy, I'm Charles Tan"))
    _age_pending_booking(2 * 3600)
    app_mod.claude.queue.append(_final_with("Booking that now!", booking=BOOK,
                                            confirm_booking=True))
    post(client, inbound(msg_id="wamid.in2", text="yes please"))
    assert len(calls) == 1
    assert app_mod.store.load(CUSTOMER).booked["reference"] == "GOJI-AB12CD"


def test_a_yes_more_than_a_day_after_the_offer_does_not_book(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(app_mod.booking_client, "book",
                        lambda b, wa_id, patient_id="": pytest.fail("booked a day-old offer"))
    app_mod.claude.queue.append(_final_with(
        "Shall I book Thu 26 Nov, 10:00am with Kristy for Charles Tan?", booking=BOOK))
    post(client, inbound(text="book me Thursday 10am with Kristy, I'm Charles Tan"))
    _age_pending_booking(25 * 3600)
    app_mod.claude.queue.append(_final_with("Booking that now!", booking=BOOK,
                                            confirm_booking=True))
    post(client, inbound(msg_id="wamid.in2", text="yes please"))
    assert ("book_skipped", {"reason": "no_pending_booking"}) in rec


def test_the_model_cannot_book_in_the_same_turn_it_states_the_details(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(app_mod.booking_client, "book",
                        lambda b, wa_id, patient_id="": pytest.fail("booked without a confirmation"))
    app_mod.claude.queue.append(_final_with("Booked!", booking=BOOK, confirm_booking=True))
    post(client, inbound(text="book me Thursday 10am"))
    assert ("book_skipped", {"reason": "no_pending_booking"}) in rec


def test_a_taken_slot_gets_an_apology_and_tells_chris(env, monkeypatch):
    client, rec, notes = env
    def taken(b, wa_id, patient_id=""):
        raise app_mod.booking_client.BookingFailed("gone", "slot_taken")
    monkeypatch.setattr(app_mod.booking_client, "book", taken)
    app_mod.claude.queue.append(_final_with("Shall I book it?", booking=BOOK))
    post(client, inbound(text="book Thursday 10am"))
    app_mod.claude.queue.append(_final_with("Booking!", booking=BOOK, confirm_booking=True))
    post(client, inbound(msg_id="wamid.in2", text="yes"))
    assert app_mod.wa.sent[-1][1].startswith("Sorry, that time was just taken!")
    assert notes[-1][0] == "escalated"


def test_a_website_booking_is_acknowledged_in_the_chat(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(config, "INTERNAL_TOKEN", "t")
    body = {"phone": "+6591234567", "reference": "GOJI-ZZ99", "service": "Physiotherapy",
            "date": "2026-11-26", "time": "15:30", "clinician_name": "Claire Ng",
            "source": "web"}
    assert client.post("/internal/booking-confirmed", json=body).status_code == 403
    import time as _t
    app_mod.claude.queue.append(final())
    post(client, inbound(ts=int(_t.time())))     # an active chat
    r = client.post("/internal/booking-confirmed", json=body, headers={"X-Internal-Token": "t"})
    assert r.get_json() == {"matched": True, "acknowledged": True}
    assert app_mod.wa.sent[-1][1].startswith(
        "Thanks for booking! You're all set for Thu 26 Nov, 3:30pm with Claire")
    assert app_mod.store.load(CUSTOMER).booked["reference"] == "GOJI-ZZ99"
    unknown = client.post("/internal/booking-confirmed", json={**body, "phone": "+6580000000"},
                          headers={"X-Internal-Token": "t"})
    assert unknown.get_json() == {"matched": False, "template_sent": False}


def _late_cancel_draft(reply="No worries! As it's your first late change, we'll waive the fee."):
    r = final(reply=reply, intent="cancel")
    r.content[0].text = r.content[0].text.replace('"staff_note"', '"hours_to_appointment": 3, "staff_note"')
    return r


def test_waiver_tag_writes_are_off_until_plato_saves_them():
    assert config.PLATO_TAG_WRITES is False   # 19 Nov 2026: Plato dropped the write


def test_sending_the_waiver_draft_as_is_tags_the_patient_in_plato(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(config, "PLATO_TAG_WRITES", True)
    monkeypatch.setattr(app_mod.tools, "patient_context", lambda wa_id: {
        "returning": True, "first_name": "Sam", "patients_on_number": 1,
        "patient_ids": ["p1"], "waiver_used": False, "next_appointment": None})
    tagged = []
    monkeypatch.setattr(app_mod.booking_client, "tag_patient",
                        lambda pid: tagged.append(pid) or {"ok": True, "added": True})
    app_mod.claude.queue.append(_late_cancel_draft())
    post(client, inbound(text="sorry can't make it today"))
    post(client, echo(text="No worries! As it's your first late change, we'll waive the fee."))
    assert tagged == ["p1"]
    assert ("patient_tagged", {"reason": "added"}) in rec


def test_a_shared_number_asks_chris_to_tag_the_right_patient(env, monkeypatch):
    client, rec, notes = env
    monkeypatch.setattr(app_mod.tools, "patient_context", lambda wa_id: {
        "returning": True, "first_name": "Mum", "patients_on_number": 2,
        "patient_ids": ["p1", "p2"], "waiver_used": False, "next_appointment": None})
    monkeypatch.setattr(app_mod.booking_client, "tag_patient",
                        lambda pid: pytest.fail("tagged on a shared number"))
    app_mod.claude.queue.append(_late_cancel_draft())
    post(client, inbound(text="sorry can't make it today"))
    post(client, echo(text="No worries! As it's your first late change, we'll waive the fee."))
    assert ("patient_tag_skipped", {"reason": "several_patients_on_number"}) in rec
    assert notes[-1][0] == "fyi"


def test_the_plato_tag_means_no_waiver_is_offered(env, monkeypatch):
    client, _, _ = env
    monkeypatch.setattr(app_mod.tools, "patient_context", lambda wa_id: {
        "returning": True, "first_name": "Sam", "patients_on_number": 1,
        "patient_ids": ["p1"], "waiver_used": True, "next_appointment": None})
    app_mod.claude.queue.append(final(intent="faq"))
    post(client, inbound(text="hi"))
    turn = app_mod.claude.requests[0]["messages"][-1]["content"][0]["text"]
    assert "waiver already used (tagged in Plato)" in turn
    assert "first-time waiver applies" not in turn


def test_picking_an_offered_time_moves_it_without_asking_again(env, monkeypatch):
    client, rec, _ = env
    moved = []
    monkeypatch.setattr(app_mod.booking_client, "move", lambda m, wa_id, patient_id="":
                        moved.append(m) or {"ok": True, "reference": "GOJI-MV2", "dry_run": True,
                                            "clinician_name": "Kristy", **{k: m[k] for k in
                                            ("old_date", "old_time", "new_date", "new_time")}})
    offer = {"old_date": "2026-11-25", "old_time": "10:00", "new_date": "", "new_time": "",
             "options": "2026-11-27 14:00, 2026-11-28 09:00"}
    app_mod.claude.queue.append(_final_with("I can do Thu 2pm or Fri 9am, which works?",
                                            intent="reschedule", move=offer))
    post(client, inbound(text="can I move Tuesday's appointment?"))
    pick = {**offer, "new_date": "2026-11-28", "new_time": "09:00"}
    app_mod.claude.queue.append(_final_with("Moving it!", intent="reschedule", move=pick,
                                            confirm_move=True))
    post(client, inbound(msg_id="wamid.in2", text="Fri 9am pls"))
    assert moved and moved[0]["new_time"] == "09:00"
    assert app_mod.wa.sent[-1][1].startswith("Done!")


def test_a_time_that_was_never_offered_is_not_moved(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(app_mod.booking_client, "move",
                        lambda *a, **k: pytest.fail("moved to a time nobody offered"))
    offer = {"old_date": "2026-11-25", "old_time": "10:00", "new_date": "", "new_time": "",
             "options": "2026-11-27 14:00"}
    app_mod.claude.queue.append(_final_with("Thu 2pm works?", intent="reschedule", move=offer))
    post(client, inbound(text="move Tuesday?"))
    app_mod.claude.queue.append(_final_with("Moving!", intent="reschedule", confirm_move=True,
                                            move={**offer, "new_date": "2026-11-29",
                                                  "new_time": "11:00"}))
    post(client, inbound(msg_id="wamid.in2", text="sat 11 instead"))
    assert ("move_skipped", {"reason": "time_not_offered"}) in rec


def test_picking_an_offered_booking_time_books_it(env, monkeypatch):
    client, rec, _ = env
    calls = []
    monkeypatch.setattr(app_mod.booking_client, "book", lambda b, wa_id, patient_id="": calls.append({**b, "_pid": patient_id}) or
                        {"ok": True, "reference": "GOJI-B3", "clinician_name": "Kristy",
                         "service": "Physiotherapy", "date": b["date"], "time": b["time"],
                         "dry_run": True})
    offer = {**BOOK, "date": "", "time": "", "options": "2026-11-26 10:00, 2026-11-26 11:00"}
    app_mod.claude.queue.append(_final_with("Thu 10am or 11am, Charles?", booking=offer))
    post(client, inbound(text="any thursday morning? I'm Charles Tan"))
    app_mod.claude.queue.append(_final_with("Booking!", confirm_booking=True,
                                            booking={**offer, "date": "2026-11-26",
                                                     "time": "11:00"}))
    post(client, inbound(msg_id="wamid.in2", text="11 please"))
    assert calls and calls[0]["time"] == "11:00" and calls[0]["full_name"] == "Charles Tan"


def _booker(calls, refuse=None):
    """A fake booking_client.book: records each call; `refuse` maps an email to
    the BookingFailed it raises."""
    def book(b, wa_id, patient_id=""):
        calls.append({**b, "_pid": patient_id})
        if refuse and b.get("email") in refuse:
            raise app_mod.booking_client.BookingFailed(*refuse[b["email"]])
        return {"ok": True, "reference": "GOJI-E1", "clinician_name": "Kristy",
                "service": "Physiotherapy", "date": b["date"], "time": b["time"]}
    return book


def _offer_then_pick(client, email_with_pick):
    offer = {**BOOK, "date": "", "time": "", "options": "2026-11-26 10:00, 2026-11-26 11:00"}
    app_mod.claude.queue.append(_final_with("Thu 10am or 11am, Charles?", booking=offer))
    post(client, inbound(text="any thursday morning? I'm Charles Tan"))
    app_mod.claude.queue.append(_final_with("Booking!", confirm_booking=True, booking={
        **offer, "date": "2026-11-26", "time": "11:00", "email": email_with_pick}))
    post(client, inbound(msg_id="wamid.in2", text="11 please, " + email_with_pick))


def test_an_email_given_with_the_pick_goes_to_the_booking(env, monkeypatch):
    client, rec, _ = env
    calls = []
    monkeypatch.setattr(app_mod.booking_client, "book", _booker(calls))
    _offer_then_pick(client, "charles@example.com")
    assert calls[0]["email"] == "charles@example.com"
    assert "confirmation email is on its way" in app_mod.wa.sent[-1][1]


def test_a_returning_patient_is_booked_with_the_email_on_file(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(app_mod.tools, "patient_context", lambda wa_id: {
        "returning": True, "first_name": "Charles", "patients_on_number": 1,
        "patient_ids": ["CHARLES"],
        "records": [{"id": "CHARLES", "name": "Charles Tan", "email": "ct@example.com"}]})
    calls = []
    monkeypatch.setattr(app_mod.booking_client, "book", _booker(calls))
    app_mod.claude.queue.append(_final_with("Shall I book it?", booking=BOOK))
    post(client, inbound(text="book me Thursday 10am"))
    assert "an email is on file" in str(app_mod.claude.requests[-1])
    assert "ct@example.com" not in str(app_mod.claude.requests[-1])     # the model never sees it
    app_mod.claude.queue.append(_final_with("Booking!", booking=BOOK, confirm_booking=True))
    post(client, inbound(msg_id="wamid.in2", text="yes"))
    assert calls[0]["email"] == "ct@example.com" and calls[0]["_pid"] == "CHARLES"


def test_a_mistyped_email_is_asked_again_and_the_answer_books(env, monkeypatch):
    client, rec, notes = env
    calls = []
    typo = ("bad_email", "That email looks like a typo — did you mean charles@gmail.com? "
                         "Please correct it so we can send your confirmation.")
    monkeypatch.setattr(app_mod.booking_client, "book",
                        _booker(calls, refuse={"charles@gmail.con": (typo[1], typo[0])}))
    _offer_then_pick(client, "charles@gmail.con")
    assert "did you mean charles@gmail.com?" in app_mod.wa.sent[-1][1]
    assert ("book_skipped", {"reason": "email_check"}) in rec and not notes   # Chris not told
    kept = app_mod.store.load(CUSTOMER).pending_booking
    assert (kept["date"], kept["time"], kept["email"]) == ("2026-11-26", "11:00", "")
    app_mod.claude.queue.append(_final_with("Booking!", confirm_booking=True, booking={
        **BOOK, "date": "2026-11-26", "time": "11:00", "email": "charles@gmail.com"}))
    post(client, inbound(msg_id="wamid.in3", text="yes sorry"))
    assert calls[-1]["email"] == "charles@gmail.com"
    assert app_mod.wa.sent[-1][1].startswith("All booked!")


def test_an_email_that_isnt_one_is_asked_again_before_booking(env, monkeypatch):
    client, rec, _ = env
    calls = []
    monkeypatch.setattr(app_mod.booking_client, "book", _booker(calls))
    _offer_then_pick(client, "charles at gmail")
    assert calls == [] and "doesn't look quite right" in app_mod.wa.sent[-1][1]


def test_booking_for_a_new_family_member_uses_the_texters_email(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(app_mod.tools, "patient_context", lambda wa_id: {
        "returning": True, "first_name": "Charles", "patients_on_number": 1,
        "patient_ids": ["CHARLES"],
        "records": [{"id": "CHARLES", "name": "Charles Tan", "email": "ct@example.com"}]})
    calls = []
    monkeypatch.setattr(app_mod.booking_client, "book", _booker(calls))
    wife = {**BOOK, "full_name": "Mei Tan", "for_whom": "wife", "booked_by": "Charles"}
    app_mod.claude.queue.append(_final_with("Shall I book it for Mei?", booking=wife))
    post(client, inbound(text="book my wife Mei Tan in Thursday 10am"))
    app_mod.claude.queue.append(_final_with("Booking!", booking=wife, confirm_booking=True))
    post(client, inbound(msg_id="wamid.in2", text="yes"))
    assert calls[0]["_pid"] == "" and calls[0]["email"] == "ct@example.com"
    # Unless they give another one: theirs wins.
    app_mod.store.save(app_mod.store.load(CUSTOMER).__class__(wa_id=CUSTOMER))
    app_mod.claude.queue.append(_final_with("Shall I book it for Mei?", booking=wife))
    post(client, inbound(msg_id="wamid.in3", text="book my wife Mei Tan in Thursday 10am"))
    app_mod.claude.queue.append(_final_with("Booking!", confirm_booking=True,
                                            booking={**wife, "email": "mei@example.com"}))
    post(client, inbound(msg_id="wamid.in4", text="yes, send it to mei@example.com"))
    assert calls[-1]["email"] == "mei@example.com"


def test_a_bad_email_on_file_books_without_it(env, monkeypatch):
    client, rec, notes = env
    monkeypatch.setattr(app_mod.tools, "patient_context", lambda wa_id: {
        "returning": True, "first_name": "Charles", "patients_on_number": 1,
        "patient_ids": ["CHARLES"],
        "records": [{"id": "CHARLES", "name": "Charles Tan", "email": "ct@gmail.con"}]})
    calls = []
    monkeypatch.setattr(app_mod.booking_client, "book",
                        _booker(calls, refuse={"ct@gmail.con": ("did you mean ct@gmail.com?",
                                                                "bad_email")}))
    app_mod.claude.queue.append(_final_with("Shall I book it?", booking=BOOK))
    post(client, inbound(text="book me Thursday 10am"))
    app_mod.claude.queue.append(_final_with("Booking!", booking=BOOK, confirm_booking=True))
    post(client, inbound(msg_id="wamid.in2", text="yes"))
    assert [c["email"] for c in calls] == ["ct@gmail.con", ""]
    assert app_mod.wa.sent[-1][1].startswith("All booked!") and not notes


def test_a_name_sent_after_picking_a_time_books_it(env, monkeypatch):
    # Picked an offered time, was asked their name, sent it: the name comes in
    # the confirming message, for the same time already pending.
    client, rec, notes = env
    calls = []
    monkeypatch.setattr(app_mod.booking_client, "book", lambda b, wa_id, patient_id="": calls.append(dict(b)) or
                        {"ok": True, "reference": "GOJI-N4", "clinician_name": "Kristy",
                         "service": "Physiotherapy", "date": b["date"], "time": b["time"],
                         "dry_run": True})
    picked = {**BOOK, "full_name": "", "options": "2026-11-26 10:00"}
    app_mod.claude.queue.append(_final_with("Lovely! Could I have your full name?",
                                            booking=picked))
    post(client, inbound(text="10am tomorrow"))
    assert calls == [] and app_mod.store.load(CUSTOMER).pending_booking["full_name"] == ""
    app_mod.claude.queue.append(_final_with("Booking you in now.", confirm_booking=True,
                                            booking={**picked, "full_name": "Charles Tan"}))
    post(client, inbound(msg_id="wamid.in2", text="Charles Tan"))
    assert len(calls) == 1 and calls[0]["full_name"] == "Charles Tan"
    assert calls[0]["time"] == "10:00"
    assert app_mod.wa.sent[-1][1].startswith("All booked!")
    assert notes == []


def test_a_confirmed_booking_that_cant_be_made_holds_and_tells_chris(env, monkeypatch):
    client, rec, notes = env
    monkeypatch.setattr(app_mod.booking_client, "book",
                        lambda b, wa_id, patient_id="": pytest.fail("booked without a name"))
    picked = {**BOOK, "full_name": "", "options": "2026-11-26 10:00"}
    app_mod.claude.queue.append(_final_with("Could I have your full name?", booking=picked))
    post(client, inbound(text="10am tomorrow"))
    for i in (2, 3):     # asked for the name once, then it's the team's
        app_mod.claude.queue.append(_final_with("Booking you in now.", confirm_booking=True,
                                                booking=picked))
        post(client, inbound(msg_id=f"wamid.in{i}", text="just book it please"))
    assert ("book_skipped", {"reason": "details_asked"}) in rec
    assert ("book_skipped", {"reason": "details_missing"}) in rec
    assert app_mod.wa.sent[-1][1] == app_mod.BOOK_HELD_REPLY      # never "booking you in now"
    assert notes[-1][0] == "escalated"


def test_no_closer_for_someone_already_in_a_longer_conversation(env):
    client, rec, _ = env
    import time as _t
    now = int(_t.time())
    app_mod.claude.queue.extend([final(), final(), final()])
    for i, text in enumerate(["hours?", "and prices?", "do you do pilates?"]):
        post(client, inbound(msg_id=f"wamid.l{i}", text=text, ts=now - 300 + i))
    asked = len(app_mod.claude.requests)
    post(client, inbound(msg_id="wamid.l9", text="ok thanks!", ts=now))
    assert len(app_mod.claude.requests) == asked                 # no nudge, no model call
    assert ("silent", {"reason": "acknowledgement"}) in rec


def test_a_reply_goes_out_as_bubbles_with_typing_between(env, monkeypatch):
    client, rec, notes = env
    monkeypatch.setattr(config, "MAX_BUBBLES", 3)
    monkeypatch.setattr(config, "SPLIT_MIN_WORDS", 0)
    app_mod.claude.queue.append(final(
        reply="Hey! How can I address you?\n<break>\nCongrats on your newborn ❤️\n<break>\n"
              "Our postpartum session is 55 minutes.", intent="service_fit"))
    post(client, inbound(text="hi, I just had a baby"))
    assert [t for _, t in app_mod.wa.sent] == ["Hey! How can I address you?",
                                              "Congrats on your newborn ❤️",
                                              "Our postpartum session is 55 minutes."]
    assert app_mod.wa.typing.count("wamid.in1") == 3        # once before, once per later bubble
    stored = app_mod.store.load(CUSTOMER).history[-1]["text"]
    assert "<break>" not in stored and stored.count("\n\n") == 2


def test_booking_for_a_wife_never_lands_on_the_husbands_record(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(app_mod.tools, "patient_context", lambda wa_id: {
        "returning": True, "first_name": "Charles", "patients_on_number": 1,
        "patient_ids": ["CHARLES"], "records": [{"id": "CHARLES", "name": "Charles Tan"}]})
    calls = []
    monkeypatch.setattr(app_mod.booking_client, "book", lambda b, wa_id, patient_id="":
                        calls.append((b, patient_id)) or
                        {"ok": True, "reference": "GOJI-W1", "clinician_name": "Kristy",
                         "date": b["date"], "time": b["time"], "dry_run": True})
    wife = {**BOOK, "full_name": "Mei Tan", "for_whom": "wife", "booked_by": "Charles",
            "patient_age": ""}
    app_mod.claude.queue.append(_final_with("Shall I book it for Mei?", booking=wife))
    post(client, inbound(text="book my wife Mei Tan in for postnatal physio Thursday 10am"))
    app_mod.claude.queue.append(_final_with("Booking!", booking=wife, confirm_booking=True))
    post(client, inbound(msg_id="wamid.in2", text="yes"))
    assert calls and calls[0][1] == ""                    # a new record in Mei's name
    assert app_mod.wa.sent[-1][1].startswith("All booked!")
    assert "Mei" not in app_mod.wa.sent[-1][1]


def test_reset_from_whatsapp_starts_the_chat_fresh_for_testers_only(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(config, "STATE_BACKEND", "memory")
    app_mod.claude.queue.append(final(reply="Chris will get back to you.", intent="human_requested",
                                      escalate=True, reason="x"))
    post(client, inbound(text="can Chris call me?"))
    assert app_mod.store.load(CUSTOMER).mode == WAITING
    post(client, inbound(msg_id="wamid.r1", text="/reset"))
    state = app_mod.store.load(CUSTOMER)
    assert state.mode == AGENT and state.history == [] and state.pending_for_chris == ""
    assert "Reset done" in app_mod.wa.sent[-1][1]
    assert len(app_mod.claude.requests) == 1                     # no model call for /reset
    # deployed: only listed testers
    monkeypatch.setattr(config, "STATE_BACKEND", "firestore")
    monkeypatch.setattr(config, "GO_LIVE", 1.0)   # deployed runs answer only once live
    monkeypatch.setattr(config, "TESTERS", frozenset())
    app_mod.claude.queue.append(final())
    post(client, inbound(msg_id="wamid.r2", text="/reset"))
    assert len(app_mod.claude.requests) == 2                     # treated as a normal message


def test_turbo_toggles_the_hold_for_testers(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(config, "STATE_BACKEND", "memory")
    monkeypatch.setattr(config, "PRE_SEND_HOLD_S", 20.0)
    monkeypatch.setattr(config, "DEBOUNCE_S", 6.0)
    post(client, inbound(text="/turbo on"))
    assert config.PRE_SEND_HOLD_S == 0.0 and config.DEBOUNCE_S == 1.5
    assert "Turbo on" in app_mod.wa.sent[-1][1] and app_mod.claude.requests == []
    post(client, inbound(msg_id="wamid.t2", text="/turbo off"))
    assert config.PRE_SEND_HOLD_S == app_mod._NORMAL["hold"]


def test_website_booking_from_a_new_number_gets_the_confirmation_template(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(config, "INTERNAL_TOKEN", "t")
    monkeypatch.setattr(config, "CONFIRMATIONS", True)
    sent = []
    app_mod.wa.send_template = lambda wa_id, name, params, language="en": sent.append((wa_id, name, params)) or "wamid.tpl1"
    r = client.post("/internal/booking-confirmed", headers={"X-Internal-Token": "t"},
                    json={"phone": "+6590001111", "reference": "GOJI-1", "service": "Physiotherapy",
                          "date": "2026-11-26", "time": "10:00", "clinician_name": "Kristy Ng",
                          "source": "web", "first_name": "Sam", "send_template": True})
    assert r.get_json() == {"matched": False, "template_sent": True}
    assert sent == [("6590001111", "goji_appointment_confirmed",
                     ["Sam", "physiotherapy", "Thu 26 Nov, 10:00am", "Kristy"])]
    assert app_mod.store.load("6590001111").booked["reference"] == "GOJI-1"


@pytest.mark.parametrize("flag", [None, False, "true"])
def test_confirmation_template_waits_for_goji_booking_to_ask(env, monkeypatch, flag):
    """goji-booking sets send_template: true only once its confirmation email
    is live, so both channels go live together. Anything else sends nothing."""
    client, rec, _ = env
    monkeypatch.setattr(config, "INTERNAL_TOKEN", "t")
    monkeypatch.setattr(config, "CONFIRMATIONS", True)
    app_mod.wa.send_template = lambda *a, **k: pytest.fail("sent without the go-ahead")
    body = {"phone": "+6590001111", "reference": "GOJI-1", "date": "2026-11-26",
            "time": "10:00", "source": "staff"}
    if flag is not None:
        body["send_template"] = flag
    r = client.post("/internal/booking-confirmed", headers={"X-Internal-Token": "t"}, json=body)
    assert r.get_json() == {"matched": False, "template_sent": False}


def test_front_desk_booking_gets_the_template_too(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(config, "INTERNAL_TOKEN", "t")
    monkeypatch.setattr(config, "CONFIRMATIONS", True)
    sent = []
    app_mod.wa.send_template = lambda wa_id, name, params, language="en": sent.append(name) or "wamid.tpl2"
    r = client.post("/internal/booking-confirmed", headers={"X-Internal-Token": "t"},
                    json={"phone": "+6590002222", "reference": "GOJI-2", "service": "Pilates",
                          "date": "2026-11-27", "time": "09:00", "clinician_name": "Claire Ng",
                          "source": "staff", "first_name": "Ann", "send_template": True})
    assert r.get_json()["template_sent"] and sent == ["goji_appointment_confirmed"]


def test_confirmation_template_is_off_until_enabled(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(config, "INTERNAL_TOKEN", "t")
    monkeypatch.setattr(config, "CONFIRMATIONS", False)
    app_mod.wa.send_template = lambda *a, **k: pytest.fail("sent while off")
    r = client.post("/internal/booking-confirmed", headers={"X-Internal-Token": "t"},
                    json={"phone": "+6590001111", "reference": "GOJI-1", "date": "2026-11-26",
                          "time": "10:00", "source": "web", "send_template": True})
    assert r.get_json() == {"matched": False, "template_sent": False}


def test_reminder_confirm_tap_is_thanked_without_the_model(env):
    client, rec, _ = env
    body = inbound(kind="button")
    body["entry"][0]["changes"][0]["value"]["messages"][0]["button"] = {"text": "Confirm",
                                                                       "payload": "Confirm"}
    post(client, body)
    assert app_mod.wa.sent[-1][1].startswith("Thanks for confirming!")
    assert app_mod.claude.requests == []
    assert ("reminder_confirmed", {"reason": "button"}) in rec


def test_reminder_confirm_tap_marks_plato_confirmed(env, monkeypatch):
    client, rec, _ = env
    calls = []
    monkeypatch.setattr(app_mod.booking_client, "confirm",
                        lambda aid, wa_id: calls.append((aid, wa_id)) or {"ok": True,
                                                                          "already": False})
    body = inbound(kind="button")
    msg = body["entry"][0]["changes"][0]["value"]["messages"][0]
    msg["button"] = {"text": "Confirm", "payload": "reminder_confirm:abc123"}
    post(client, body)
    assert calls == [("abc123", msg["from"])]
    assert any(e[0] == "reminder_confirmed_in_plato" for e in rec)


def test_reminder_confirm_tap_without_payload_writes_nothing(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(app_mod.booking_client, "confirm",
                        lambda *a, **k: pytest.fail("no appointment id to confirm"))
    body = inbound(kind="button")
    body["entry"][0]["changes"][0]["value"]["messages"][0]["button"] = {"text": "Confirm",
                                                                       "payload": "Confirm"}
    post(client, body)
    assert app_mod.wa.sent[-1][1].startswith("Thanks for confirming!")


def test_plato_confirm_failure_is_recorded_not_raised(env, monkeypatch):
    client, rec, _ = env

    def boom(aid, wa_id):
        raise app_mod.booking_client.BookingFailed("nope", "not_found")
    monkeypatch.setattr(app_mod.booking_client, "confirm", boom)
    body = inbound(kind="button")
    body["entry"][0]["changes"][0]["value"]["messages"][0]["button"] = {
        "text": "Confirm", "payload": "reminder_confirm:abc123"}
    post(client, body)
    assert ("reminder_confirm_failed", {"reason": "not_found"}) in rec


def test_secret_link_url_handshake_and_post(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(config, "WA_WEBHOOK_URL_TOKEN", "s3cret-link")
    ok = client.get("/webhook/s3cret-link?hub.mode=subscribe&hub.verify_token=verify-me"
                    "&hub.challenge=1158201444")
    assert ok.status_code == 200 and ok.data == b"1158201444"
    assert ok.headers["Content-Type"].startswith("text/plain")
    assert client.get("/webhook/wrong?hub.mode=subscribe&hub.verify_token=verify-me"
                      "&hub.challenge=1").status_code == 403
    assert client.get("/webhook/s3cret-link?hub.mode=subscribe&hub.verify_token=nope"
                      "&hub.challenge=1").status_code == 403
    app_mod.claude.queue.append(final())
    assert client.post("/webhook/s3cret-link", json=inbound()).status_code == 200
    assert client.post("/webhook/wrong", json=inbound()).status_code == 403


def test_secret_link_off_when_unset(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(config, "WA_WEBHOOK_URL_TOKEN", "")
    assert client.get("/webhook/anything?hub.mode=subscribe&hub.verify_token=verify-me"
                      "&hub.challenge=1").status_code == 403



def test_a_handed_over_complaint_gets_the_agents_specific_holding_reply(env, monkeypatch):
    client, _, notes = env
    monkeypatch.setattr(config, "STAGE", 2)
    body = json.loads(final(reply="So sorry. We'll give you a free session.",
                            intent="complaint").content[0].text)
    body["holding_reply"] = "I'm so sorry about the wait. I've passed this to the team and " \
                            "they'll get back to you today."
    resp = final(); resp.content[0].text = json.dumps(body)
    app_mod.claude.queue.append(resp)
    post(client, inbound(text="I waited 30 minutes yesterday, not happy"))
    assert app_mod.wa.sent[-1][1].startswith("I'm so sorry about the wait")
    assert "free session" not in app_mod.wa.sent[-1][1]
    assert notes and "free session" in notes[0][1]["suggested_reply"]   # Chris sees the draft


def test_no_record_is_looked_up_again_soon_but_a_patient_stays_cached(env, monkeypatch):
    # A number with no record can become a patient minutes later; a 6-hour
    # "no record" made the agent hand over a booking it had just made itself.
    client, _, _ = env
    answers = [{"returning": False},
               {"returning": True, "first_name": "Sarah", "patients_on_number": 1}]
    calls = []
    monkeypatch.setattr(app_mod.tools, "patient_context",
                        lambda wa_id: calls.append(wa_id) or answers[len(calls) - 1])
    app_mod.claude.queue.extend([final(), final(), final(), final()])
    post(client, inbound())
    post(client, inbound(msg_id="wamid.in2", text="hello?"))
    assert len(calls) == 1                                   # cached for a few minutes
    state = app_mod.store.load(CUSTOMER)
    state.patient_at -= app_mod.NO_RECORD_CACHE_S + 1
    app_mod.store.save(state)
    post(client, inbound(msg_id="wamid.in3", text="it's me"))
    assert len(calls) == 2                                   # now a patient
    state = app_mod.store.load(CUSTOMER)
    state.patient_at -= app_mod.NO_RECORD_CACHE_S + 1        # well inside 6 hours
    app_mod.store.save(state)
    post(client, inbound(msg_id="wamid.in4", text="thanks"))
    assert len(calls) == 2


# --- cancelling ---------------------------------------------------------------------

CANCEL = {"date": "2026-11-27", "time": "15:00"}


def _stub_cancel(monkeypatch, calls, fail=""):
    def cancel(c, wa_id, patient_id=""):
        calls.append(c)
        if fail:
            raise app_mod.booking_client.BookingFailed("no", fail)
        return {"ok": True, "reference": "GOJI-CX1", "dry_run": False,
                "clinician_name": "Kristy Ng", "service": "Physiotherapy", **c}
    monkeypatch.setattr(app_mod.booking_client, "cancel", cancel)


def test_a_cancel_with_notice_is_done_straight_away(env, monkeypatch):
    client, rec, notes = env
    calls = []
    _stub_cancel(monkeypatch, calls)
    app_mod.claude.queue.append(_final_with(
        "Hope all's well! If you don't mind me asking, what came up? Whenever you're ready, "
        "I'm happy to find you another time 😊", intent="cancel", cancel=CANCEL,
        hours_to_appointment=72))
    post(client, inbound(text="please cancel my appointment with Kristy"))
    assert calls == [CANCEL]                                 # no "shall I?" round trip
    text = app_mod.wa.sent[-1][1]
    assert text.startswith("Done, I've cancelled your appointment on Fri 27 Nov, 3:00pm "
                           "with Kristy (ref GOJI-CX1).")
    assert "what came up" in text and "another time" in text
    assert notes == []                                       # Chris isn't emailed
    assert ("cancelled", {"intent": "cancel", "reason": "agent"}) in rec
    assert app_mod.store.load(CUSTOMER).outcomes[-1]["outcome"] == "cancelled"


def test_a_reason_given_up_front_gets_the_models_follow_up(env, monkeypatch):
    client, _, _ = env
    _stub_cancel(monkeypatch, [])
    app_mod.claude.queue.append(_final_with(
        "Hope you feel better soon! Once you're up to it, I'm happy to find you a new time.",
        intent="cancel", cancel=CANCEL, hours_to_appointment=72))
    post(client, inbound(text="pls cancel friday, down with flu"))
    text = app_mod.wa.sent[-1][1]
    assert text.startswith("Done, I've cancelled") and "feel better soon" in text
    assert "what came up" not in text


def test_a_follow_up_that_repeats_the_cancellation_gives_way_to_the_default(env, monkeypatch):
    client, _, _ = env
    _stub_cancel(monkeypatch, [])
    app_mod.claude.queue.append(_final_with("All cancelled for you!", intent="cancel",
                                            cancel=CANCEL, hours_to_appointment=72))
    post(client, inbound(text="cancel friday"))
    text = app_mod.wa.sent[-1][1]
    assert text.count("cancelled") == 1 and "what came up" in text


def test_not_sure_which_one_asks_and_cancels_nothing(env, monkeypatch):
    client, rec, _ = env
    calls = []
    _stub_cancel(monkeypatch, calls)
    app_mod.claude.queue.append(_final_with(
        "Sure! Is that Wed 25 Nov, 10:00am or Fri 27 Nov, 3:00pm?", intent="cancel",
        cancel={"date": "", "time": ""}, hours_to_appointment=72))
    post(client, inbound(text="cancel my appointment"))
    assert calls == [] and app_mod.wa.sent[-1][1].startswith("Sure! Is that")


def test_a_failed_cancel_tells_chris_and_the_customer(env, monkeypatch):
    client, rec, notes = env
    calls = []
    _stub_cancel(monkeypatch, calls, fail="late_change")
    app_mod.claude.queue.append(_final_with("Hope all's well!", intent="cancel", cancel=CANCEL))
    post(client, inbound(text="cancel friday pls"))
    assert calls and notes and notes[-1][0] == "escalated"
    assert "within 24 hours" in app_mod.wa.sent[-1][1]


FORM_TOKEN = "4b1e9c0d2a7f4e3b8c6d5a4f3e2d1c0b.a1b2c3d4e5f6a7b8c9d0"


def _confirm_body(**kw):
    return {"phone": "+6590003333", "reference": "GOJI-3", "service": "Physiotherapy",
            "date": "2026-11-27", "time": "19:00", "clinician_name": "Kristy Ng",
            "source": "web", "first_name": "Mei", "send_template": True, **kw}


def test_owed_form_uses_the_form_template_once_approved(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(config, "INTERNAL_TOKEN", "t")
    monkeypatch.setattr(config, "CONFIRMATIONS", True)
    monkeypatch.setattr(config, "CONFIRM_FORM_TEMPLATE", "goji_appointment_confirmed_form")
    sent = []
    app_mod.wa.send_template = lambda wa_id, name, params, language="en", url_buttons=None: \
        sent.append((name, url_buttons)) or "wamid.f1"
    client.post("/internal/booking-confirmed", headers={"X-Internal-Token": "t"},
                json=_confirm_body(form_token=FORM_TOKEN))
    assert sent == [("goji_appointment_confirmed_form", {0: FORM_TOKEN})]


@pytest.mark.parametrize("form_template, token", [
    ("", FORM_TOKEN),                                   # form template not approved yet
    ("goji_appointment_confirmed_form", ""),            # nothing owed
    ("goji_appointment_confirmed_form", "../evil"),     # not a token
])
def test_plain_template_otherwise(env, monkeypatch, form_template, token):
    client, rec, _ = env
    monkeypatch.setattr(config, "INTERNAL_TOKEN", "t")
    monkeypatch.setattr(config, "CONFIRMATIONS", True)
    monkeypatch.setattr(config, "CONFIRM_FORM_TEMPLATE", form_template)
    sent = []
    app_mod.wa.send_template = lambda wa_id, name, params, language="en", url_buttons=None: \
        sent.append((name, url_buttons)) or "wamid.f2"
    client.post("/internal/booking-confirmed", headers={"X-Internal-Token": "t"},
                json=_confirm_body(form_token=token))
    assert sent == [("goji_appointment_confirmed", None)]


def test_send_template_url_button_payload():
    from wa_agent.whatsapp import WhatsAppClient
    posted = []
    c = WhatsAppClient.__new__(WhatsAppClient)
    c._post = lambda body: posted.append(body) or {"messages": [{"id": "x"}]}
    c.send_template("6591234567", "goji_appointment_confirmed_form", ["a", "b", "c", "d"],
                    url_buttons={0: FORM_TOKEN})
    comps = posted[0]["template"]["components"]
    assert comps[1] == {"type": "button", "sub_type": "url", "index": "0",
                        "parameters": [{"type": "text", "text": FORM_TOKEN}]}
def _offer(clinician, options, text):
    return _final_with(text, booking={**BOOK, "date": "", "time": "", "clinician": clinician,
                                      "options": options})


def test_a_time_from_an_earlier_offer_books_with_its_clinician(env, monkeypatch):
    """26 Nov 2026: Claire's times were offered, then Kristy's; the customer
    picked 'Monday 5:00 with Claire' from the first list and wasn't booked
    (time_not_offered): only the latest list counted."""
    client, rec, notes = env
    calls = []
    monkeypatch.setattr(app_mod.booking_client, "book", _booker(calls))
    app_mod.claude.queue.append(_offer(
        "Claire", "2026-11-30 17:00 Claire, 2026-11-30 18:00 Claire",
        "After Saturday noon:\n* Mon 30 Nov, 5:00pm with Claire\n"
        "* Mon 30 Nov, 6:00pm with Claire\n\nWhich suits you?"))
    post(client, inbound(text="after sat noon please, I'm Charles Tan"))
    app_mod.claude.queue.append(_offer(
        "Kristy", "2026-12-01 08:00 Kristy, 2026-12-01 08:30 Kristy",
        "Kristy's next open times:\n* Tue 1 Dec, 8:00am\n* Tue 1 Dec, 8:30am\n\n"
        "Which suits you?"))
    post(client, inbound(msg_id="wamid.in2", text="and Kristy?"))
    app_mod.claude.queue.append(_final_with("Booking!", confirm_booking=True, booking={
        **BOOK, "date": "2026-11-30", "time": "17:00", "clinician": "Claire",
        "options": ""}))
    post(client, inbound(msg_id="wamid.in3", text="Please book Monday 5:00 with Claire."))
    assert len(calls) == 1
    assert (calls[0]["date"], calls[0]["time"], calls[0]["clinician"]) == \
        ("2026-11-30", "17:00", "Claire")
    assert ("book_skipped", {"reason": "time_not_offered"}) not in rec
    assert notes == []


def test_offers_for_another_service_dont_carry_over(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(app_mod.booking_client, "book",
                        lambda b, wa_id, patient_id="": pytest.fail("booked a pilates time"))
    app_mod.claude.queue.append(_final_with("Pilates?\n* Mon 30 Nov, 5:00pm", booking={
        **BOOK, "service": "clinical-pilates", "date": "", "time": "",
        "options": "2026-11-30 17:00 Claire"}))
    post(client, inbound(text="pilates times?"))
    app_mod.claude.queue.append(_offer("Kristy", "2026-12-01 08:00 Kristy",
                                       "Physio:\n* Tue 1 Dec, 8:00am"))
    post(client, inbound(msg_id="wamid.in2", text="actually physio"))
    app_mod.claude.queue.append(_final_with("Booking!", confirm_booking=True, booking={
        **BOOK, "date": "2026-11-30", "time": "17:00", "clinician": "Claire"}))
    post(client, inbound(msg_id="wamid.in3", text="mon 5pm"))
    assert ("book_skipped", {"reason": "time_not_offered"}) in rec


def test_a_pick_without_a_name_asks_for_it_and_the_answer_books(env, monkeypatch):
    client, rec, notes = env
    calls = []
    monkeypatch.setattr(app_mod.booking_client, "book", _booker(calls))
    nameless = {**BOOK, "full_name": ""}
    app_mod.claude.queue.append(_final_with("Times:\n* Mon 30 Nov, 5:00pm with Claire", booking={
        **nameless, "date": "", "time": "", "clinician": "Claire",
        "options": "2026-11-30 17:00 Claire"}))
    post(client, inbound(text="times?"))
    app_mod.claude.queue.append(_final_with("Booking you in now.", confirm_booking=True,
                                            booking={**nameless, "date": "2026-11-30",
                                                     "time": "17:00", "clinician": "Claire"}))
    post(client, inbound(msg_id="wamid.in2", text="Monday 5 with Claire"))
    assert calls == [] and notes == []
    assert app_mod.wa.sent[-1][1] == ("Lovely! Could I have your full name? Then I'll book "
                                      "Mon 30 Nov, 5:00pm with Claire for you.")
    app_mod.claude.queue.append(_final_with("Booking you in now.", confirm_booking=True,
                                            booking={**nameless, "date": "2026-11-30",
                                                     "time": "17:00", "clinician": "Claire",
                                                     "full_name": "Ami Tan"}))
    post(client, inbound(msg_id="wamid.in3", text="Ami Tan"))
    assert len(calls) == 1 and calls[0]["full_name"] == "Ami Tan"
    assert calls[0]["clinician"] == "Claire" and calls[0]["time"] == "17:00"


def _book_with_terms(client, team: bool):
    if team:
        state = app_mod.store.load(CUSTOMER)
        app_mod.append_history(state, "team", "Can do, bill to FM, $190 for 40 min",
                               time.time())
        app_mod.store.save(state)
    terms = {**BOOK, "variant": "40min", "arranged": "Bill to FM, $190 for 40 min"}
    app_mod.claude.queue.append(_final_with("Shall I book Thu 26 Nov, 10:00am with Kristy?",
                                            booking=terms))
    post(client, inbound(text="thursday 10am with kristy please"))
    app_mod.claude.queue.append(_final_with("Booking!", confirm_booking=True, booking=terms))
    post(client, inbound(msg_id="wamid.in2", text="yes"))


def test_terms_the_team_agreed_go_on_the_booking(env, monkeypatch):
    client, rec, _ = env
    calls = []
    monkeypatch.setattr(app_mod.booking_client, "book", _booker(calls))
    _book_with_terms(client, team=True)
    assert calls[0]["arranged"] == "Bill to FM, $190 for 40 min"
    assert calls[0]["variant"] == "40min"


def test_terms_with_no_one_from_the_clinic_in_the_chat_are_dropped(env, monkeypatch):
    client, rec, _ = env
    calls = []
    monkeypatch.setattr(app_mod.booking_client, "book", _booker(calls))
    _book_with_terms(client, team=False)
    assert calls and calls[0]["arranged"] == ""


def test_the_first_times_offered_come_with_the_booking_link(env, monkeypatch):
    client, rec, _ = env
    first = ("Here are the next open times:\n* Today, 2:00pm with Kristy\n"
             "* Fri 27 Nov, 2:00pm with Kristy\n\nWhich suits you? And could I have your "
             "full name and email for the booking?")
    app_mod.claude.queue.append(_offer("", "2026-11-26 14:00 Kristy, 2026-11-27 14:00 Kristy",
                                       first))
    post(client, inbound(text="yes please, a time"))
    sent = "\n".join(t for _, t in app_mod.wa.sent)
    assert "Or book any open time yourself here: https://go.gojiphysio.com/wa-book?" \
           "service=physiotherapy" in sent
    assert sent.rstrip().endswith("full name and email for the booking?")   # question last
    count = len(app_mod.wa.sent)
    app_mod.claude.queue.append(_offer("", "2026-11-28 16:00 Claire",
                                       "After Saturday noon:\n* Sat 28 Nov, 4:00pm\n\n"
                                       "Which suits you?"))
    post(client, inbound(msg_id="wamid.in2", text="after sat noon?"))
    assert not any("go.gojiphysio.com" in t for _, t in app_mod.wa.sent[count:])
