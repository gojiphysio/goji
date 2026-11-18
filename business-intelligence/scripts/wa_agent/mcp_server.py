"""
The agent's tools as a stdio MCP server, for the Claude CLI backend
(cli_backend.py). Same handlers as the API path (tools.py), so both backends
see identical tools and results.

The customer's WhatsApp id comes from the WA_ID env var the backend sets per
call, never from the model, so my_appointments stays keyed on the chat's own
number.

Hand-rolled newline-delimited JSON-RPC (initialize, tools/list, tools/call):
three methods aren't worth an SDK dependency for a temporary backend.
"""
from __future__ import annotations

import json
import os
import sys

from .tools import TOOL_DEFS, run_tool

SERVER_INFO = {"name": "goji", "version": "0.1"}


def handle(req: dict) -> dict | None:
    """One JSON-RPC request -> response (None for notifications)."""
    method, rid = req.get("method"), req.get("id")
    if rid is None:  # notification, e.g. notifications/initialized
        return None
    if method == "initialize":
        version = (req.get("params") or {}).get("protocolVersion", "2025-06-18")
        result = {"protocolVersion": version, "serverInfo": SERVER_INFO,
                  "capabilities": {"tools": {}}}
    elif method == "tools/list":
        result = {"tools": [{"name": t["name"], "description": t["description"],
                             "inputSchema": t["input_schema"]} for t in TOOL_DEFS]}
    elif method == "tools/call":
        params = req.get("params") or {}
        out, is_err = run_tool(params.get("name", ""), params.get("arguments") or {},
                               wa_id=os.environ.get("WA_ID", ""))
        text = out if isinstance(out, str) else json.dumps(out)
        result = {"content": [{"type": "text", "text": text}], "isError": is_err}
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601, "message": f"unknown method {method}"}}
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            resp = handle(json.loads(line))
        except Exception as e:  # malformed input: answer, don't die
            resp = {"jsonrpc": "2.0", "id": None,
                    "error": {"code": -32700, "message": str(e)}}
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
