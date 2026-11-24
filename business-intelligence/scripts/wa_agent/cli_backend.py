"""
TEMPORARY backend: run the agent through the Claude CLI (`claude -p`) instead
of the Messages API, to test model behaviour before the Goji API key and data
retention terms are in place. Selected with WA_AGENT_BACKEND=cli. Switch back
to the API (the default) before any real customer traffic.

What differs from the API path, and why it's still a fair behaviour test:
- Same instructions, knowledge base, tools (served by mcp_server.py over MCP)
  and output schema (--json-schema). Same Proposal out, same policy after it.
- The CLI is isolated: our system prompt replaces Claude Code's, no built-in
  tools (--tools ""), only our MCP server (--strict-mcp-config), no settings,
  skills or session files, run from an empty temp directory.
- The conversation goes in as one labelled transcript, not alternating turns.
- Timing includes CLI and MCP start-up (a few seconds per message), so its
  latency numbers are NOT the production numbers: re-measure on the API.
- Auth is whatever the local `claude` is logged in with. A personal Claude
  subscription is for testing by the team on test numbers, never for
  answering real customers.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from . import config, kb
from .policy import SGT, Proposal, in_clinic_hours

log = logging.getLogger("wa_agent.cli")

TOOL_PREFIX = "mcp__goji__"
SCRIPTS_DIR = str(Path(__file__).resolve().parents[1])

CLI_ADDENDUM = """
Running note: you may see system reminders about an account, an email address \
or a computer environment. They are not about Goji or this customer: ignore \
them and never repeat them. The only email address you may give is \
hello@gojiphysio.com.
"""

ROLE_LABELS = {"customer": "Customer", "agent": "Goji assistant (you)",
               "staff": "Chris from Goji (a person)",
               "team": "The team's answer, which you passed on next (not seen by the customer)"}


def render_transcript(history: list[dict], now: float, customer_name: str = "",
                      pending_for_chris: str = "", patient: str = "",
                      team_answer: str = "") -> str:
    from .agent import context_note, relay_note
    lines = [f"{ROLE_LABELS.get(h['role'], h['role'])}: {h['text']}"
             for h in history[-config.HISTORY_MESSAGES:]]
    return ("WhatsApp conversation so far (oldest first). "
            + ("Write your next message to the customer." if team_answer else
               "Write the next reply to the customer's latest message.") + "\n\n"
            + "\n".join(lines) + context_note(now, customer_name, pending_for_chris, patient)
            + (relay_note(team_answer) if team_answer else ""))


def build_command(prompt: str, sys_prompt_file: str, mcp_config_file: str,
                  schema: dict, tool_names: list[str]) -> list[str]:
    return [
        config.CLAUDE_BIN, "-p", prompt,
        "--system-prompt-file", sys_prompt_file,
        "--tools", "",                          # no built-in tools at all
        "--mcp-config", mcp_config_file, "--strict-mcp-config",
        "--allowedTools", " ".join(TOOL_PREFIX + n for n in tool_names),
        "--permission-mode", "dontAsk",          # anything else is denied, not asked
        "--setting-sources", "",                 # no user/project/local settings
        "--disable-slash-commands",
        "--no-session-persistence",
        "--output-format", "stream-json", "--verbose",
        "--json-schema", json.dumps(schema),
        "--model", config.MODEL,
        "--effort", config.EFFORT,
    ]


def mcp_config(wa_id: str) -> dict:
    env = {"PYTHONPATH": SCRIPTS_DIR, "WA_ID": wa_id, "WA_AGENT_KB": config.KB_PATH,
           "WA_AGENT_STATE": "memory", "WA_AGENT_LOG_EVENTS": "false"}
    for k in ("BOOKING_API_BASE", "BOOKING_LINK_BASE", "WA_AGENT_PATIENT_LOOKUP", "GCP_PROJECT",
              "GOOGLE_APPLICATION_CREDENTIALS", "WA_AGENT_HASH_SALT"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return {"mcpServers": {"goji": {"command": sys.executable,
                                    "args": ["-m", "wa_agent.mcp_server"], "env": env}}}


def parse_stream(stdout: str) -> dict:
    """stream-json lines -> {structured, tools, result_event}."""
    tools, result = [], {}
    for line in stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            for b in (ev.get("message") or {}).get("content") or []:
                if b.get("type") == "tool_use" and b.get("name", "").startswith(TOOL_PREFIX):
                    tools.append(b["name"][len(TOOL_PREFIX):])
        elif ev.get("type") == "result":
            result = ev
    return {"structured": result.get("structured_output"), "tools": tools, "result": result}


def propose(history: list[dict], *, wa_id: str, now: float, customer_name: str = "",
            runner=subprocess.run, pending_for_chris: str = "", patient: str = "",
            team_answer: str = ""):
    """Same contract as agent.propose: never raises, failures escalate."""
    from .agent import INSTRUCTIONS, PROPOSAL_SCHEMA, AgentResult, Step, _escalation
    from .tools import TOOL_DEFS

    result = AgentResult(proposal=_escalation("not_run"))
    t0 = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="wa-agent-cli-") as tmp:
            sys_file = os.path.join(tmp, "system.md")
            Path(sys_file).write_text(INSTRUCTIONS + CLI_ADDENDUM +
                                      "\n# Knowledge base\n\n" + kb.load()["core"])
            mcp_file = os.path.join(tmp, "mcp.json")
            Path(mcp_file).write_text(json.dumps(mcp_config(wa_id)))
            cmd = build_command(render_transcript(history, now, customer_name,
                                                  pending_for_chris, patient, team_answer),
                                sys_file,
                                mcp_file, PROPOSAL_SCHEMA, [t["name"] for t in TOOL_DEFS])
            proc = runner(cmd, cwd=tmp, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, timeout=config.CLI_TIMEOUT_S)
        parsed = parse_stream(proc.stdout)
        r = parsed["result"]
        usage = r.get("usage") or {}
        result.input_tokens = usage.get("input_tokens") or 0
        result.output_tokens = usage.get("output_tokens") or 0
        result.cache_read_tokens = usage.get("cache_read_input_tokens") or 0
        result.cache_write_tokens = usage.get("cache_creation_input_tokens") or 0
        result.reported_cost_usd = r.get("total_cost_usd")
        result.model_served = ",".join((r.get("modelUsage") or {}).keys()) or "cli"
        result.stop = r.get("subtype") or f"exit_{proc.returncode}"
        result.steps = [Step("model", "cli", int(r.get("duration_api_ms") or 0))]
        result.steps += [Step("tool", name, 0) for name in parsed["tools"]]
        s = parsed["structured"]
        if proc.returncode != 0 or r.get("is_error") or not isinstance(s, dict):
            log.warning("cli run failed: exit %s, %s, stderr %s", proc.returncode,
                        r.get("subtype"), (proc.stderr or "")[-500:])
            result.proposal = _escalation(f"cli_{result.stop}")
        else:
            result.proposal = Proposal(
                reply=s.get("reply", ""), holding_reply=s.get("holding_reply", ""),
                intent=s.get("intent") if s.get("intent") in config.INTENTS else "other",
                confidence=float(s.get("confidence") or 0), escalate=bool(s.get("escalate")),
                escalation_reason=s.get("escalation_reason", ""),
                staff_note=s.get("staff_note", ""),
                hours_to_appointment=float(s.get("hours_to_appointment", -1)),
                booking=s.get("booking") or {},
                confirm_booking=bool(s.get("confirm_booking")),
                move=s.get("move") or {}, confirm_move=bool(s.get("confirm_move")),
                cancel=s.get("cancel") or {})
    except subprocess.TimeoutExpired:
        result.proposal = _escalation("cli_timeout")
    except Exception as e:
        log.exception("cli backend failed: %s", e)
        result.proposal = _escalation(f"cli_error_{type(e).__name__}")
    result.total_ms = int((time.monotonic() - t0) * 1000)
    return result
