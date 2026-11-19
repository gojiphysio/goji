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
    assert notes == []                    # Chris sees the file in the app; no email


def test_a_photo_is_left_for_the_team(env):
    client, _, notes = env
    app_mod.claude.queue.append(final(reply="Thanks! The team will take a look.",
                                      intent="media_received"))
    post(client, inbound(kind="image"))
    assert app_mod.store.load(CUSTOMER).history[0]["text"] == "[sent a photo]"
    assert app_mod.wa.sent[-1][1] == "Thanks! The team will take a look."
    assert notes == []


# --- direct booking -----------------------------------------------------------

import json as _json

BOOK = {"service": "physiotherapy", "date": "2026-11-26", "time": "10:00", "options": "",
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
    monkeypatch.setattr(app_mod.booking_client, "book", lambda b, wa_id: calls.append(b) or
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
    assert sent.startswith("You're booked, Charles! Thu 26 Nov, 10:00am with Kristy (ref GOJI-AB12CD)")
    assert "dry run" in sent
    state = app_mod.store.load(CUSTOMER)
    assert state.booked["reference"] == "GOJI-AB12CD" and state.pending_booking == {}
    assert ("booked", {"intent": "booking", "reason": "dry_run"}) in rec


def test_the_model_cannot_book_in_the_same_turn_it_states_the_details(env, monkeypatch):
    client, rec, _ = env
    monkeypatch.setattr(app_mod.booking_client, "book",
                        lambda b, wa_id: pytest.fail("booked without a confirmation"))
    app_mod.claude.queue.append(_final_with("Booked!", booking=BOOK, confirm_booking=True))
    post(client, inbound(text="book me Thursday 10am"))
    assert ("book_skipped", {"reason": "no_pending_booking"}) in rec


def test_a_taken_slot_gets_an_apology_and_tells_chris(env, monkeypatch):
    client, rec, notes = env
    def taken(b, wa_id):
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
    assert unknown.get_json() == {"matched": False}


def _late_cancel_draft(reply="No worries! As it's your first late change, we'll waive the fee."):
    r = final(reply=reply, intent="cancel")
    r.content[0].text = r.content[0].text.replace('"staff_note"', '"hours_to_appointment": 3, "staff_note"')
    return r


def test_sending_the_waiver_draft_as_is_tags_the_patient_in_plato(env, monkeypatch):
    client, rec, _ = env
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
    monkeypatch.setattr(app_mod.booking_client, "book", lambda b, wa_id: calls.append(b) or
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
