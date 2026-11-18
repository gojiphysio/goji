from datetime import datetime

from wa_agent.policy import (AGENT, DRAFT, ESCALATE, HUMAN, PAUSED, SEND, SGT, SILENT,
                             ChatState, Proposal, apply_idle_handback, decide, gate,
                             human_replied_since, in_clinic_hours, on_human_message)

NOW = datetime(2026, 11, 18, 10, 0, tzinfo=SGT).timestamp()  # Wednesday 10am


def prop(**kw):
    base = dict(reply="hello", intent="faq", confidence=0.9, escalate=False)
    return Proposal(**{**base, **kw})


def test_auto_intent_with_confidence_sends():
    assert decide(prop()).action == SEND


def test_low_confidence_drafts_even_for_auto_intents():
    d = decide(prop(confidence=0.5))
    assert d.action == DRAFT and d.reason.startswith("low_confidence")


def test_model_escalation_wins_over_intent_policy():
    assert decide(prop(escalate=True, escalation_reason="asked for Chris")).action == ESCALATE


def test_escalate_intents_escalate_even_if_model_did_not():
    assert decide(prop(intent="human_requested")).action == ESCALATE
    assert decide(prop(intent="urgent", confidence=1.0)).action == ESCALATE


def test_draft_and_unknown_intents_draft():
    for intent in ("existing_appointment", "cancel", "billing", "clinical", "complaint",
                   "something_new"):
        assert decide(prop(intent=intent)).action == DRAFT, intent


def test_draft_intents_stay_drafts_even_if_the_model_escalates():
    # Chris asked for complaints, billing, clinical and cancelling as drafts she checks.
    assert decide(prop(intent="complaint", escalate=True)).action == DRAFT
    assert decide(prop(intent="urgent", escalate=True)).action == ESCALATE
    assert decide(prop(intent="faq", escalate=True)).action == ESCALATE   # unsure on an auto intent


def test_booking_and_rescheduling_send_on_their_own():
    assert decide(prop(intent="booking")).action == SEND
    assert decide(prop(intent="reschedule")).action == SEND


def test_empty_reply_never_sends():
    assert decide(prop(reply="  ")).action == DRAFT


def test_gate_blocks_in_order():
    s = ChatState(wa_id="6591234567")
    assert gate(s, NOW, kill_switch=True, always_human=frozenset()).reason == "kill_switch"
    assert gate(s, NOW, kill_switch=False,
                always_human=frozenset({"6591234567"})).reason == "always_human"
    s.mode = HUMAN
    assert gate(s, NOW, kill_switch=False, always_human=frozenset()).action == SILENT
    s.mode = PAUSED
    assert gate(s, NOW, kill_switch=False, always_human=frozenset()).reason == "paused"
    s.mode = AGENT
    assert gate(s, NOW, kill_switch=False, always_human=frozenset()) is None


def test_after_hours_mode_is_silent_while_clinic_is_open():
    s = ChatState(wa_id="x")
    assert gate(s, NOW, kill_switch=False, always_human=frozenset(),
                agent_hours="after_hours").reason == "clinic_hours"
    late = datetime(2026, 11, 18, 22, 0, tzinfo=SGT).timestamp()
    assert gate(s, late, kill_switch=False, always_human=frozenset(),
                agent_hours="after_hours") is None


def test_clinic_hours():
    assert in_clinic_hours(NOW)
    assert not in_clinic_hours(datetime(2026, 11, 22, 10, 0, tzinfo=SGT).timestamp())  # Sunday
    assert not in_clinic_hours(datetime(2026, 11, 18, 20, 0, tzinfo=SGT).timestamp())


def test_human_message_takes_over_and_idle_hands_back():
    s = ChatState(wa_id="x")
    assert on_human_message(s, NOW)
    assert s.mode == HUMAN
    assert not apply_idle_handback(s, NOW + 3600, idle_s=24 * 3600)
    assert apply_idle_handback(s, NOW + 24 * 3600, idle_s=24 * 3600)
    assert s.mode == AGENT and s.mode_reason == "idle_handback"


def test_unanswered_escalation_also_hands_back():
    s = ChatState(wa_id="x", mode=HUMAN, mode_since=NOW)  # no human ever replied
    assert apply_idle_handback(s, NOW + 25 * 3600, idle_s=24 * 3600)


def test_paused_never_times_out():
    s = ChatState(wa_id="x", mode=PAUSED, mode_since=NOW)
    assert not apply_idle_handback(s, NOW + 30 * 24 * 3600, idle_s=24 * 3600)


def test_presend_recheck():
    s = ChatState(wa_id="x")
    assert not human_replied_since(s, NOW)
    s.last_human_at = NOW + 5
    assert human_replied_since(s, NOW)
    s2 = ChatState(wa_id="y", mode=HUMAN)
    assert human_replied_since(s2, NOW)


def test_reply_content_guard():
    from wa_agent.policy import reply_problems
    ok = ("Book here: https://go.gojiphysio.com/wa-book?service=physiotherapy or call "
          "+65 8377 0401, email hello@gojiphysio.com. In an emergency call 995. "
          "It's $260 for 55 min, Mon-Sat 8am-8pm.")
    assert reply_problems(ok) == []
    assert reply_problems("Pay at https://evil.example/pay") == ["link:evil.example"]
    assert reply_problems("Email charles@example.com") == ["email"]
    assert reply_problems("Call Kristy on 9123 4567") == ["phone"]
    # seen in the first live test: the raw /book URL instead of the tracked go-link
    assert reply_problems("Book here: https://www.gojiphysio.com/book/") == ["untracked_booking_link"]


def test_reply_with_foreign_link_is_drafted_not_sent():
    d = decide(prop(reply="Pay here: https://evil.example/pay"))
    assert d.action == DRAFT and d.reason == "content:link:evil.example"


def test_acknowledgements():
    from wa_agent.policy import is_acknowledgement
    after_reply = [{"role": "agent", "text": "Here's the link"}, {"role": "customer", "text": "x"}]
    for t in ("ok", "Okay!", "thanks", "Thank you so much!!", "👍", "noted 🙏🏻", "ty"):
        assert is_acknowledgement(t, after_reply), t
    for t in ("ok can I book Friday?", "thanks, how much is pilates?", "Sunday?"):
        assert not is_acknowledgement(t, after_reply), t
    # a first-contact "thanks" still gets an answer
    assert not is_acknowledgement("thanks", [{"role": "customer", "text": "thanks"}])


def test_late_reschedule_goes_to_chris_and_early_one_sends():
    late = Proposal(reply="ok", intent="reschedule", confidence=0.95, escalate=False,
                    hours_to_appointment=5)
    early = Proposal(reply="ok", intent="reschedule", confidence=0.95, escalate=False,
                     hours_to_appointment=30)
    unknown = Proposal(reply="When is your appointment?", intent="reschedule",
                       confidence=0.95, escalate=False)
    assert decide(late) == decide(late).__class__(DRAFT, "late_change")
    assert decide(early).action == SEND
    assert decide(unknown).action == SEND   # the agent asks when it is first
