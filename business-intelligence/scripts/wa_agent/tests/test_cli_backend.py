import json
import subprocess
from types import SimpleNamespace as NS

from wa_agent import agent, cli_backend, config

H = [{"role": "customer", "text": "how much is pilates?", "ts": 1, "id": "m1"},
     {"role": "staff", "text": "Hi! Let me check", "ts": 2, "id": "e1"},
     {"role": "customer", "text": "thanks", "ts": 3, "id": "m2"}]


def stream(structured, *, tools=("booking_link",), is_error=False, cost=0.012):
    lines = [{"type": "system", "subtype": "init"}]
    for t in tools:
        lines.append({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": f"mcp__goji__{t}", "input": {}}]}})
    lines.append({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "StructuredOutput", "input": structured or {}}]}})
    lines.append({"type": "result", "subtype": "error" if is_error else "success",
                  "is_error": is_error, "structured_output": structured,
                  "duration_api_ms": 4200, "total_cost_usd": cost,
                  "usage": {"input_tokens": 10, "output_tokens": 200,
                            "cache_read_input_tokens": 30000},
                  "modelUsage": {"served-model": {}}})
    return "\n".join(json.dumps(x) for x in lines)


GOOD = {"reply": "Clinical Pilates is $120.", "intent": "pricing", "confidence": 0.9,
        "escalate": False, "escalation_reason": "", "staff_note": "pilates price"}


def runner_returning(stdout, code=0, seen=None):
    def run(cmd, **kw):
        if seen is not None:
            seen.update(cmd=cmd, kw=kw,
                        system=open(cmd[cmd.index("--system-prompt-file") + 1]).read(),
                        mcp=json.load(open(cmd[cmd.index("--mcp-config") + 1])))
        return NS(returncode=code, stdout=stdout, stderr="")
    return run


def test_command_is_isolated_and_constrained():
    seen = {}
    r = cli_backend.propose(H, wa_id="6591234567", now=1763431200,
                            runner=runner_returning(stream(GOOD), seen=seen))
    cmd = seen["cmd"]
    assert cmd[cmd.index("--tools") + 1] == ""                    # no built-in tools
    assert "--strict-mcp-config" in cmd
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    assert "--no-session-persistence" in cmd
    allowed = cmd[cmd.index("--allowedTools") + 1].split()
    assert all(a.startswith("mcp__goji__") for a in allowed) and len(allowed) == 5
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == agent.PROPOSAL_SCHEMA
    assert cmd[cmd.index("--model") + 1] == config.MODEL
    assert seen["kw"]["stdin"] == subprocess.DEVNULL
    # our instructions + KB replace Claude Code's system prompt
    assert seen["system"].startswith(agent.INSTRUCTIONS) and "$260" in seen["system"]
    # the MCP server gets the chat's own number
    assert seen["mcp"]["mcpServers"]["goji"]["env"]["WA_ID"] == "6591234567"
    prompt = cmd[cmd.index("-p") + 1]
    assert "Chris from Goji (a person): Hi! Let me check" in prompt
    assert prompt.index("thanks") < prompt.index("[context")
    assert r.proposal.reply == "Clinical Pilates is $120."


def test_result_is_parsed_into_timings_tools_and_cost():
    r = cli_backend.propose(H, wa_id="x", now=0, runner=runner_returning(stream(GOOD)))
    assert r.proposal.intent == "pricing" and not r.proposal.escalate
    assert r.tools_used == ["booking_link"]
    assert r.steps[0].ms == 4200
    assert r.cost_usd == 0.012 and r.cache_read_tokens == 30000
    assert r.model_served == "served-model"


def test_failures_escalate():
    r = cli_backend.propose(H, wa_id="x", now=0,
                            runner=runner_returning(stream(None, is_error=True), code=1))
    assert r.proposal.escalate and r.proposal.escalation_reason.startswith("cli_")

    def timeout(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1)
    r = cli_backend.propose(H, wa_id="x", now=0, runner=timeout)
    assert r.proposal.escalation_reason == "cli_timeout"


def test_backend_switch(monkeypatch):
    called = {}
    monkeypatch.setattr(config, "BACKEND", "cli")
    monkeypatch.setattr(cli_backend, "propose",
                        lambda h, **kw: called.update(kw) or "cli-result")
    assert agent.propose(H, wa_id="x", now=5) == "cli-result"
    assert called["wa_id"] == "x"
