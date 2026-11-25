"""The team's answer through the assistant: Chris swipe-replies to a ping (or
texts "answer 004 ..."), the agent writes it up, sends it, takes the chat back
and shows her what it sent (owner, 24 Nov 2026)."""
import time

from wa_agent import agent, app as app_mod, config, staff, summary
from wa_agent.policy import AGENT, PAUSED, WAITING

from .fakes import final
from .payloads import echo, inbound
from .test_golive import CHRIS, CUSTOMER, env, names, post, with_staff  # noqa: F401 (fixtures)

ANSWER = "yes Sat 10am is fine with Dr Tan, no referral needed"
RELAYED = "Good news: Saturday at 10am works with Dr Tan, and you don't need a referral."


def swipe(text, ping_id, ts, msg_id="s1"):
    """Chris's swipe-reply to a ping: the inbound carries context.id."""
    body = inbound(wa_id=CHRIS, text=text, ts=ts, msg_id=msg_id)
    body["entry"][0]["changes"][0]["value"]["messages"][0]["context"] = {
        "from": "6583770401", "id": ping_id}
    return body


def handover(client, ts):
    """A customer asks something only the team can answer: holding reply,
    chat waiting, Chris pinged. Returns the ping's message id."""
    app_mod.claude.queue.append(final(reply="Yes, [confirm with Dr Tan]", intent="human_requested",
                                      escalate=True, reason="needs the team",
                                      note="can Dr Tan see her Sat 10am, referral?",
                                      holding="Let me check that with the team for you!"))
    post(client, inbound(text="Can Dr Tan see me Sat 10am? Do I need a referral?", ts=ts))
    assert app_mod.store.load(CUSTOMER).mode == WAITING
    ((_, _, _),) = app_mod.wa.templates
    return f"wamid.tpl{len(app_mod.wa.templates)}"


def to_customer():
    return [t for to, t in app_mod.wa.sent if to == CUSTOMER]


def last_to_chris():
    return [t for to, t in app_mod.wa.sent if to == CHRIS][-1]


def test_swipe_reply_sends_the_answer_and_takes_the_chat_back(env, with_staff):
    client, rec, _, _ = env
    now = int(time.time())
    ping = handover(client, now - 600)
    app_mod.claude.queue.append(final(reply=RELAYED, intent="other", note=""))
    post(client, swipe(ANSWER, ping, now))
    assert to_customer()[-1] == RELAYED
    st = app_mod.store.load(CUSTOMER)
    assert st.mode == AGENT and st.owner == "agent" and st.pending_for_chris == ""
    assert [h["role"] for h in st.history[-2:]] == ["team", "agent"]
    assert st.history[-2]["text"] == ANSWER
    assert last_to_chris().startswith("Sent to Mei (#001):") and RELAYED in last_to_chris()
    assert [f["reason"] for e, f in rec if e == "staff_answer"] == ["sent"]
    # The model was asked to pass the answer on, after the holding reply.
    last_turn = app_mod.claude.requests[-1]["messages"][-1]
    assert last_turn["role"] == "user" and ANSWER in last_turn["content"][0]["text"]
    # No longer waiting for Chris: status and the morning summary agree.
    assert summary.waiting_for_chris([st], now - 3600) == []
    # The customer's next message is the agent's again.
    app_mod.claude.queue.append(final())
    post(client, inbound(ts=now + 60, msg_id="wamid.c"))
    assert app_mod.wa.sent[-1][0] == CUSTOMER


def test_answer_by_code_resumes_a_chat_chris_already_wrote_in(env, with_staff):
    client, rec, _, _ = env
    now = int(time.time())
    app_mod.claude.queue.append(final())
    post(client, inbound(ts=now - 900, msg_id="wamid.a"))
    post(client, echo(ts=now - 800))
    st = app_mod.store.load(CUSTOMER)
    assert st.mode == PAUSED
    app_mod.claude.queue.append(final(reply=RELAYED, intent="other", note=""))
    post(client, inbound(wa_id=CHRIS, text=f"Answer {st.code}: {ANSWER}", ts=now, msg_id="s1"))
    assert to_customer()[-1] == RELAYED
    st = app_mod.store.load(CUSTOMER)
    assert st.mode == AGENT and not st.held


def test_partial_answer_keeps_the_rest_waiting(env, with_staff):
    client, rec, _, _ = env
    now = int(time.time())
    ping = handover(client, now - 600)
    app_mod.claude.queue.append(final(reply="Saturday 10am works! The team will confirm "
                                            "the referral question shortly.",
                                      intent="other", note="whether a referral is needed"))
    post(client, swipe("Sat 10am fine", ping, now))
    st = app_mod.store.load(CUSTOMER)
    assert st.mode == WAITING and st.pending_for_chris == "whether a referral is needed"
    assert "still waiting on: whether a referral is needed" in last_to_chris()
    assert summary.waiting_for_chris([st], now - 3600) == ["Mei (#001)"]


def test_not_an_answer_sends_nothing(env, with_staff):
    client, rec, _, _ = env
    now = int(time.time())
    ping = handover(client, now - 600)
    sent = len(to_customer())
    app_mod.claude.queue.append(final(reply="", intent="other", escalate=True,
                                      reason="that's a question for me, not an answer"))
    post(client, swipe("who is this again?", ping, now))
    assert len(to_customer()) == sent
    assert app_mod.store.load(CUSTOMER).mode == WAITING
    assert last_to_chris().startswith("I didn't send anything to Mei (#001): that's a question")
    assert ("staff_answer", {"reason": "refused:not_an_answer"}) in rec


def test_a_write_up_with_brackets_is_held(env, with_staff):
    client, _, _, _ = env
    now = int(time.time())
    ping = handover(client, now - 600)
    sent = len(to_customer())
    app_mod.claude.queue.append(final(reply="See you [day] at 10am", intent="other", note=""))
    post(client, swipe(ANSWER, ping, now))
    assert len(to_customer()) == sent
    assert "didn't pass the checks" in last_to_chris()


def test_closed_window_and_kill_switch_refuse_without_the_model(env, with_staff):
    client, rec, _, _ = env
    now = int(time.time())
    ping = handover(client, now - 2 * 86400)  # their last message: two days ago
    calls = len(app_mod.claude.requests)
    post(client, swipe(ANSWER, ping, now))
    assert "Business app message them now" in last_to_chris()
    app_mod.store.set_kill(True)
    post(client, swipe(ANSWER, ping, now, msg_id="s2"))
    assert "assistant is stopped" in last_to_chris()
    assert len(app_mod.claude.requests) == calls


def test_bare_command_swipe_replied_to_a_ping(env, with_staff):
    client, _, _, _ = env
    now = int(time.time())
    ping = handover(client, now - 600)
    sent = len(to_customer())
    post(client, swipe("Resume", ping, now))
    assert app_mod.store.load(CUSTOMER).mode == AGENT
    assert len(to_customer()) == sent  # resume still messages the customer nothing
    post(client, swipe("status", ping, now, msg_id="s2"))
    assert last_to_chris().startswith("Goji assistant: running")


def test_customer_writing_meanwhile_gets_a_fresh_write_up(env, with_staff, monkeypatch):
    client, _, _, _ = env
    now = int(time.time())
    ping = handover(client, now - 600)
    real, calls = agent.propose, []

    def propose(history, **kw):
        calls.append(history[-1]["text"])
        if len(calls) == 1:  # they write again while the first write-up is made
            with app_mod.locks(CUSTOMER):
                st = app_mod.store.load(CUSTOMER)
                app_mod.append_history(st, "customer", "also, is parking free?", time.time(), "m2")
                app_mod.store.save(st)
        return real(history, **kw)

    monkeypatch.setattr(agent, "propose", propose)
    app_mod.claude.queue.extend([final(reply="first", intent="other", note=""),
                                 final(reply=RELAYED, intent="other", note="")])
    post(client, swipe(ANSWER, ping, now))
    assert calls[1] == "also, is parking free?"
    assert to_customer()[-1] == RELAYED and "first" not in to_customer()


def test_unknown_code_and_empty_answer(env, with_staff):
    client, _, _, _ = env
    now = int(time.time())
    handover(client, now - 600)
    post(client, inbound(wa_id=CHRIS, text="answer 999 yes", ts=now, msg_id="s1"))
    assert "can't find chat #999" in last_to_chris()
    post(client, inbound(wa_id=CHRIS, text="answer 001", ts=now, msg_id="s2"))
    assert last_to_chris().startswith("What should I tell Mei (#001)?")


def test_only_pings_about_a_chat_can_be_answered(env, with_staff):
    app_mod._alert("demoted", customer="", wa_id=CUSTOMER, who="", staff_note="moved to drafts",
                   suggested_reply="", reason="demoted", last_message="")
    assert app_mod.wa.templates and app_mod.store.ping_chat("wamid.tpl1") == ""


def test_parse_answer():
    assert staff.parse_answer("ANSWER 004 yes, Sat 10am") == ("004", "yes, Sat 10am")
    assert staff.parse_answer("answer #4: Yes.\nSee you!") == ("004", "Yes.\nSee you!")
    assert staff.parse_answer("Answer chat 12 - no referral") == ("012", "no referral")
    assert staff.parse_answer("answer 4") == ("004", "")
    assert staff.parse_answer("the answer is 4") is None
    assert staff.bare_command("Resume.") == "resume"
    assert staff.bare_command("resume tomorrow ok") == ""


def test_relay_turn_labels_the_team_answer_and_closes_with_the_instruction():
    history = [{"role": "customer", "text": "Sat 10am?", "ts": 1, "id": "a"},
               {"role": "agent", "text": "Let me check!", "ts": 2, "id": "b"}]
    msgs = agent.build_messages(history, 3, team_answer=ANSWER)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert ANSWER in msgs[-1]["content"][0]["text"]
    history += [{"role": "team", "text": ANSWER, "ts": 4, "id": ""},
                {"role": "agent", "text": RELAYED, "ts": 4, "id": "c"},
                {"role": "customer", "text": "thanks!", "ts": 5, "id": "d"}]
    msgs = agent.build_messages(history, 6)
    assert "[The team's answer, which you passed on next]: " + ANSWER in msgs[1]["content"][0]["text"]
    assert "From the Goji team" not in msgs[-1]["content"][0]["text"]


def test_the_teams_answer_keeps_offered_times_open(env, with_staff):
    """Times offered before the handover are still the customer's to pick
    once the team's answer goes out ("which time suits?"), however long
    the team took (25 Nov 2026)."""
    client, _, _, _ = env
    now = int(time.time())
    ping = handover(client, now - 3 * 3600)
    st = app_mod.store.load(CUSTOMER)
    st.pending_booking = {"service": "physiotherapy", "date": "2026-11-26", "time": "",
                          "options": "2026-11-26 10:00, 2026-11-26 10:30",
                          "at": now - 3 * 3600}
    app_mod.store.save(st)
    app_mod.claude.queue.append(final(reply=RELAYED, intent="other", note=""))
    post(client, swipe(ANSWER, ping, now))
    kept = app_mod.store.load(CUSTOMER).pending_booking
    assert kept["options"] == "2026-11-26 10:00, 2026-11-26 10:30"
    assert kept["at"] >= now - 5
