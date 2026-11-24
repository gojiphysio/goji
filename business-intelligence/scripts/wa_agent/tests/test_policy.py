from datetime import datetime

from wa_agent.policy import (AGENT, DRAFT, ESCALATE, HUMAN, PAUSED, SEND, SGT, SILENT,
                             ChatState, Proposal, apply_idle_handback, decide, gate,
                             human_replied_since, in_clinic_hours, is_acknowledgement, on_human_message)

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
    for intent in ("cancel", "billing", "clinical", "complaint", "something_new"):
        assert decide(prop(intent=intent)).action == DRAFT, intent


def test_draft_intents_stay_drafts_even_if_the_model_escalates():
    # Chris asked for complaints, billing, clinical and cancelling as drafts she checks.
    assert decide(prop(intent="complaint", escalate=True)).action == DRAFT
    assert decide(prop(intent="urgent", escalate=True)).action == ESCALATE
    assert decide(prop(intent="faq", escalate=True)).action == ESCALATE   # unsure on an auto intent


def test_booking_and_rescheduling_send_on_their_own():
    assert decide(prop(intent="booking")).action == SEND
    assert decide(prop(intent="existing_appointment")).action == SEND
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


def test_human_message_pauses_until_resumed():
    """Chris, 19 Nov 2026: once a person writes, the agent is fully silent
    until she resumes the chat; no idle hand-back."""
    s = ChatState(wa_id="x", owner="agent")
    assert on_human_message(s, NOW)
    assert s.mode == PAUSED and s.owner == ""
    assert not apply_idle_handback(s, NOW + 90 * 24 * 3600, idle_s=24 * 3600)
    assert s.mode == PAUSED


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


def test_multi_word_acknowledgements_need_no_reply():
    h = [{"role": "agent"}, {"role": "customer"}]
    for t in ("ok thanks!", "Noted, thank you 🙏", "see you then!"):
        assert is_acknowledgement(t, h), t
    for t in ("ok but what about sat?", "thanks, can I also ask about price"):
        assert not is_acknowledgement(t, h), t


def test_a_short_clarifying_question_sends_even_below_the_confidence_bar():
    q = Proposal(reply="No worries! Just to check, is your current appointment today at 3pm?",
                 intent="reschedule", confidence=0.6, escalate=False)
    assert decide(q).action == SEND and decide(q).reason.startswith("clarifying_question")
    priced = Proposal(reply="It's $260, would you like to book?", intent="pricing",
                      confidence=0.6, escalate=False)
    assert decide(priced).action == DRAFT            # a fact in it: still drafted
    two = Proposal(reply="Is it today? And at 3pm?", intent="reschedule", confidence=0.6,
                   escalate=False)
    assert decide(two).action == DRAFT               # more than one question
    unsure = Proposal(reply="Is it today?", intent="reschedule", confidence=0.3, escalate=False)
    assert decide(unsure).action == DRAFT            # very unsure: still drafted
    cancel = Proposal(reply="Which appointment?", intent="cancel", confidence=0.6, escalate=False)
    assert decide(cancel).action == DRAFT            # draft-for-Chris intents stay drafts


def test_bubbles_split_and_cap_at_three():
    from wa_agent.policy import as_one_message, split_bubbles
    assert split_bubbles("one") == ["one"]
    assert split_bubbles("a\n<break>\nb") == ["a\n\nb"]                  # off by default
    assert split_bubbles("a\n<break>\nb\n<break>\n\n<break>\nc", 3) == ["a", "b", "c"]
    assert split_bubbles("a<break>b<break>c<break>d", 3) == ["a", "b", "c\n\nd"]
    assert as_one_message("a\n<break>\nb") == "a\n\nb"


# --- off-topic: answered, never handed to Chris, watch-listed when it persists

def test_off_topic_sends_whatever_the_confidence_or_escalate_flag():
    from wa_agent import config
    from wa_agent.policy import apply_stage
    junk = prop(intent="off_topic", confidence=0.3, escalate=True, reply="Sorry, wrong number!")
    d = decide(junk)
    assert (d.action, d.reason) == (SEND, "off_topic")
    for stage in config.STAGES:  # no stage turns it into a handover or leaves it
        d = apply_stage(decide(junk, intent_policy=config.stage_policy(stage)), junk, stage)
        assert d.action == SEND, stage
    # even if repeated rescues demoted it, it never becomes a draft (a ping)
    assert decide(junk, intent_policy={"off_topic": "draft"}).action == SEND


def test_off_topic_reply_with_a_foreign_link_is_dropped_not_handed_over():
    d = decide(prop(intent="off_topic", reply="Pay here: http://bit.ly/x"))
    assert (d.action, d.reason) == (SILENT, "off_topic_unsafe_reply")


def test_three_off_topic_in_a_row_puts_the_chat_on_the_watch_list():
    from wa_agent.policy import WATCHLIST, note_off_topic
    s = ChatState(wa_id="65")
    assert not note_off_topic(s, "off_topic", NOW, limit=3)
    assert not note_off_topic(s, "faq", NOW, limit=3)          # a real question resets it
    assert s.off_topic_strikes == 0
    assert [note_off_topic(s, "off_topic", NOW, limit=3) for _ in range(3)] == [False, False, True]
    assert (s.mode, s.mode_reason) == (PAUSED, WATCHLIST)
    assert gate(s, NOW, kill_switch=False).reason == WATCHLIST



# --- holding replies: the model's own, specific one; the generic line as fallback

def test_holding_reply_uses_the_models_own_when_it_is_clean():
    from wa_agent.policy import holding_reply
    p = prop(intent="complaint", reply="We'll refund you $50.",
             holding_reply="So sorry about the wait yesterday, Jamie. I've passed this to the "
                           "team and they'll get back to you today.")
    assert holding_reply(p, NOW).startswith("So sorry about the wait")


def test_holding_reply_falls_back_to_the_generic_line_timed_to_clinic_hours():
    from wa_agent.policy import GENERIC_HOLDING, holding_reply
    night = datetime(2026, 11, 18, 22, 0, tzinfo=SGT).timestamp()
    assert holding_reply(prop(holding_reply=""), NOW) == GENERIC_HOLDING[True]
    assert holding_reply(prop(holding_reply=""), night).endswith("when we open.")
    bad = prop(holding_reply="Pay here http://bit.ly/x and we'll sort it")
    assert holding_reply(bad, NOW) == GENERIC_HOLDING[True]
    assert holding_reply(prop(holding_reply="word " * 120), NOW) == GENERIC_HOLDING[True]
    assert holding_reply(prop(holding_reply="Fine", failed=True), NOW) == GENERIC_HOLDING[True]



def test_a_handover_never_sends_the_draft_meant_for_chris():
    from wa_agent.policy import Decision, customer_message
    p = prop(intent="other", escalate=True, reply="Happy to discuss a partnership! What do "
             "you have in mind?", holding_reply="Thanks! I've passed this to the team and "
             "they'll get back to you today.")
    assert customer_message(Decision(ESCALATE, "x"), p, NOW).startswith("Thanks! I've passed")
    red = prop(intent="urgent", escalate=True, reply="Please call 995 now.", holding_reply="")
    assert customer_message(Decision(ESCALATE, "x"), red, NOW) == "Please call 995 now."
    assert customer_message(Decision(SEND, "x"), prop(reply="A session is $260."), NOW) \
        == "A session is $260."



def test_a_reply_with_a_placeholder_for_chris_never_reaches_the_customer():
    from wa_agent.policy import Decision, customer_message, reply_problems
    assert reply_problems("Yes, we can issue an MC [confirm] by [time].") == ["placeholder"]
    assert reply_problems("A session is $260 (55 min).") == []
    d = decide(prop(intent="faq", reply="Returning patients get [discount] off."))
    assert d.action == DRAFT and "placeholder" in d.reason
    held = prop(intent="other", escalate=True, reply="x",
                holding_reply="We'll send the MC by [time].")
    assert "[" not in customer_message(Decision(ESCALATE, "x"), held, NOW)



def test_a_guessed_page_link_is_held(monkeypatch):
    from wa_agent import kb
    from wa_agent.policy import reply_problems
    monkeypatch.setattr(kb, "_paths", frozenset({"/", "/services/clinical-pilates/"}))
    assert reply_problems("More: https://www.gojiphysio.com/services/clinical-pilates/") == []
    assert reply_problems("See https://www.gojiphysio.com/services/clinical-pilates.") == []
    assert reply_problems("See https://www.gojiphysio.com/services/yoga/") == ["unknown_page"]



def test_the_patient_record_makes_a_late_change_late_even_if_the_model_missed_it():
    from wa_agent.policy import check_late_change
    today_3pm = {"date": "2026-11-18", "time": "15:00"}          # NOW is 10am that day
    p = prop(intent="reschedule", reply="Fee applies, sorry.", hours_to_appointment=-1)
    check_late_change(p, today_3pm, NOW)
    assert p.hours_to_appointment == 5 and decide(p).reason == "late_change"
    later = prop(intent="reschedule", hours_to_appointment=2)
    check_late_change(later, {"date": "2026-11-25", "time": "10:00"}, NOW)
    assert later.hours_to_appointment == 2                         # the sooner one wins
    faq = prop(intent="faq", hours_to_appointment=-1)
    check_late_change(faq, today_3pm, NOW)
    assert faq.hours_to_appointment == -1


def test_priority_is_sent_and_never_drafted():
    # Getting worse: the reply goes out (app.py pings staff as it does),
    # whatever the confidence or the escalate flag.
    assert decide(prop(intent="priority")).action == SEND
    assert decide(prop(intent="priority", confidence=0.4)).action == SEND
    assert decide(prop(intent="priority", escalate=True)).action == SEND
    # A reply that can't go out is still a handover now, never a draft.
    d = decide(prop(intent="priority", reply="We have a slot at [time]."))
    assert d.action == ESCALATE and d.holding
    assert decide(prop(intent="priority", reply="  ")).action == ESCALATE
    assert decide(prop(intent="priority", failed=True)).action == ESCALATE


def test_priority_reply_always_tells_them_the_team_knows():
    from wa_agent.policy import Decision, TEAM_LINE, customer_message
    p = prop(intent="priority", reply="Sorry to hear it's getting harder to walk, Sam. The "
             "earliest times are tomorrow:\n* Wed 25 Nov, 9:00am")
    out = customer_message(Decision(SEND, "x"), p, NOW)
    assert out.startswith("Sorry to hear it's getting harder to walk, Sam.\n\n" + TEAM_LINE)
    assert out.endswith("The earliest times are tomorrow:\n* Wed 25 Nov, 9:00am")
    said = prop(intent="priority", reply="Sorry to hear that.\n\nI've let our team know.")
    assert customer_message(Decision(SEND, "x"), said, NOW) == said.reply
    plain = prop(intent="faq", reply="Sorry to hear that. We open at 8am.")
    assert customer_message(Decision(SEND, "x"), plain, NOW) == plain.reply
