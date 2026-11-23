"""The scenario suite's checks themselves (no model): they must catch what
they claim to catch, or a green run means nothing."""
from wa_agent import agent
from wa_agent.eval import scenarios as sc
from wa_agent.policy import Proposal


def _p(reply, intent="faq", **kw):
    return Proposal(reply=reply, intent=intent, confidence=0.9, escalate=False, **kw)


def test_checks_catch_each_kind_of_failure():
    s = sc.Scenario("x", "g", ["hi"], sc.Expect(
        intents=("pricing",), decisions=("send",), must=(r"\$260",), must_not=(r"tummy gap",),
        max_questions=1, max_words=6, no_link=True))
    bad = _p("Hi! What? Why? The tummy gap... https://go.gojiphysio.com/wa-book?x=1 more words",
             intent="faq")
    fails = " | ".join(sc.check(s.expect, bad, "draft", prior_agent=True))
    for needle in ("intent faq", "decision draft", "missing", "has /tummy gap/",
                   "questions", "words", "greets again", "booking link"):
        assert needle in fails, needle
    good = _p("A session is $260.", intent="pricing")
    assert sc.check(s.expect, good, "send", prior_agent=False) == []


def test_every_scenario_has_a_customer_turn_last():
    for s in sc.SCENARIOS:
        assert isinstance(s.turns[-1], str), s.name
    assert len({s.name for s in sc.SCENARIOS}) == len(sc.SCENARIOS)


def test_draft_scenarios_are_met_by_the_stage_handover():
    e = sc.Expect(decisions=("draft",))
    p = _p("Chris will check this.", intent="cancel")
    assert sc.check(e, p, "escalate", prior_agent=False, stage=2) == []
    assert sc.check(e, p, "silent", prior_agent=False, stage=0) == []
    assert sc.check(e, p, "escalate", prior_agent=False, stage=None) != []


def test_judge_matches_the_service_at_stage_2():
    # A routine answer the model isn't sure of is a handover with the holding
    # reply at stage 2, not a draft: the customer hears "the team will get back".
    d = sc.judge(Proposal("A session is $260.", "pricing", 0.6, False), 2)
    assert (d.action, d.holding) == ("escalate", True)
    assert sc.judge(Proposal("A session is $260.", "pricing", 0.6, False), 2, 0.5).action == "send"
    assert sc.judge(Proposal("Noted.", "cancel", 0.95, False), 2).action == "escalate"


def _queue(monkeypatch, *proposals):
    seen, queue = [], list(proposals)

    def fake(history, **kw):
        seen.append(kw.get("pending_for_chris", ""))
        return agent.AgentResult(proposal=queue.pop(0))
    monkeypatch.setattr(agent, "propose", fake)
    return seen


def test_a_red_flag_silences_the_rest_of_the_conversation(monkeypatch):
    _queue(monkeypatch, Proposal("Call 995 now.", "urgent", 0.95, True, staff_note="bleeding"))
    s = sc.Scenario("x", "g", ["I'm bleeding heavily", "hello??"],
                    sc.Expect(silent=True), at={1: sc.Expect(decisions=("escalate",))})
    r = sc.run_one(s, stage=2)
    assert r.passed, r.failures
    assert [t["decision"] for t in r.turns] == ["escalate", "silent"]
    assert r.turns[1]["reason"] == "human_has_chat"


def test_a_handover_waits_and_the_next_turn_knows_it(monkeypatch):
    seen = _queue(monkeypatch,
                  Proposal("I'll pass this on.", "billing", 0.9, False, staff_note="double charge"),
                  Proposal("A session is $260.", "pricing", 0.9, False))
    s = sc.Scenario("x", "g", ["charged twice", "how much is a session?"],
                    sc.Expect(decisions=("send",)))
    r = sc.run_one(s, stage=2)
    assert r.passed, r.failures
    assert seen == ["", "double charge"]
    assert "team" in r.turns[0]["sent"] and r.turns[0]["sent"] != "I'll pass this on."  # holding, not the draft
    assert r.turns[1]["sweep"][0.9] == "send" and r.turns[1]["mode"] == "waiting"


def test_persistent_off_topic_goes_quiet_after_three(monkeypatch):
    _queue(monkeypatch, *[Proposal("Sorry, we can't help with that.", "off_topic", 0.9, False)] * 3)
    s = sc.Scenario("x", "g", ["poem", "poem pls", "capital of France?", "hello??"],
                    sc.Expect(silent=True))
    r = sc.run_one(s, stage=2)
    assert r.passed, r.failures
    assert [t["decision"] for t in r.turns] == ["send", "send", "send", "silent"]
    assert r.turns[3]["reason"] == "watchlist"



def test_every_scenario_regex_compiles():
    import re
    for s in sc.SCENARIOS:
        for e in [s.expect, *s.at.values()]:
            for rx in (*e.must, *e.must_not, *e.holding_must, *e.holding_must_not):
                re.compile(rx)
