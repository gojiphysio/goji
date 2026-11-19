from wa_agent import agent, config

from .fakes import FakeClaude, final, tool_call

H = [{"role": "customer", "text": "Hi, how much is a postnatal check?", "ts": 1, "id": "m1"}]


def test_plain_answer():
    c = FakeClaude(final(reply="It's $260 for 55 minutes.", intent="pricing"))
    r = agent.propose(H, wa_id="x", client=c)
    assert r.proposal.reply == "It's $260 for 55 minutes."
    assert r.proposal.intent == "pricing" and not r.proposal.escalate
    assert [s.kind for s in r.steps] == ["model"]
    assert r.cache_read_tokens == 20000 and r.cost_usd > 0


def test_request_shape():
    c = FakeClaude(final())
    agent.propose(H, wa_id="x", client=c)
    req = c.requests[0]
    assert req["model"] == config.MODEL
    assert req["output_config"]["format"]["type"] == "json_schema"
    assert req["fallbacks"] == "default"
    # The knowledge base is the cached block; the turn's context comes after it.
    assert req["system"][-1]["cache_control"]["type"] == "ephemeral"
    assert "$260" in req["system"][-1]["text"]
    last = req["messages"][-1]["content"][0]["text"]
    assert last.startswith("Hi, how much") and "[context, not from the customer" in last


def test_tool_loop_runs_tools_and_times_them():
    c = FakeClaude(tool_call("booking_link", {"service": "physiotherapy"}),
                   final(reply="Book here: https://go.gojiphysio.com/wa-book?service=physiotherapy",
                         intent="booking"))
    r = agent.propose(H, wa_id="x", client=c)
    assert r.tools_used == ["booking_link"]
    tool_result = c.requests[1]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and not tool_result["is_error"]
    assert "wa-book" in tool_result["content"]


def test_refusal_escalates():
    r = agent.propose(H, wa_id="x", client=FakeClaude(final(stop="refusal")))
    assert r.proposal.escalate and r.proposal.escalation_reason == "stop_refusal"


def test_api_error_escalates_instead_of_raising():
    r = agent.propose(H, wa_id="x", client=FakeClaude(RuntimeError("overloaded")))
    assert r.proposal.escalate and r.proposal.reply  # customer still gets a holding reply


def test_endless_tools_escalate():
    calls = [tool_call("booking_link", {"service": "physiotherapy"}, tid=f"t{i}")
             for i in range(10)]
    r = agent.propose(H, wa_id="x", client=FakeClaude(*calls))
    assert r.proposal.escalation_reason == "too_many_tool_rounds"


def test_history_roles_merge_and_staff_label():
    hist = [
        {"role": "agent", "text": "orphan agent line", "ts": 0, "id": "a0"},
        {"role": "customer", "text": "hi", "ts": 1, "id": "m1"},
        {"role": "customer", "text": "are you open sunday?", "ts": 2, "id": "m2"},
        {"role": "staff", "text": "By appointment only!", "ts": 3, "id": "e1"},
        {"role": "customer", "text": "ok thanks", "ts": 4, "id": "m3"},
    ]
    msgs = agent.build_messages(hist, now=1763431200)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[0]["content"][0]["text"] == "hi\nare you open sunday?"
    assert msgs[1]["content"][0]["text"].startswith("[Chris from Goji wrote]")


def test_warm_up_shares_the_real_requests_cached_prefix():
    c = FakeClaude(final(), final())
    agent.propose(H, wa_id="x", client=c)
    agent.warm_cache(client=c)
    real, warm = c.requests
    for key in ("model", "system", "tools", "output_config", "betas", "fallbacks"):
        assert real[key] == warm[key], key
    assert warm["max_tokens"] == 1
