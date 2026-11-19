"""The scenario suite's checks themselves (no model): they must catch what
they claim to catch, or a green run means nothing."""
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
    fails = " | ".join(sc.check(s, bad, "draft", prior_agent=True))
    for needle in ("intent faq", "decision draft", "missing", "has /tummy gap/",
                   "questions", "words", "greets again", "booking link"):
        assert needle in fails, needle
    good = _p("A session is $260.", intent="pricing")
    assert sc.check(s, good, "send", prior_agent=False) == []


def test_every_scenario_has_a_customer_turn_last():
    for s in sc.SCENARIOS:
        assert isinstance(s.turns[-1], str), s.name
    assert len({s.name for s in sc.SCENARIOS}) == len(sc.SCENARIOS)
