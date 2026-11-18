import json

from wa_agent import mcp_server


def test_initialize_echoes_protocol_version():
    r = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2025-06-18"}})
    assert r["result"]["protocolVersion"] == "2025-06-18"
    assert "tools" in r["result"]["capabilities"]


def test_notifications_get_no_reply():
    assert mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_lists_the_same_tools_as_the_api_path():
    r = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in r["result"]["tools"]}
    assert names == {"next_slots", "find_available_dates", "get_times", "booking_link", "read_page",
                     "my_appointments"}
    assert all("inputSchema" in t for t in r["result"]["tools"])


def test_call_returns_text_content_and_error_flag(monkeypatch):
    ok = mcp_server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                            "params": {"name": "booking_link",
                                       "arguments": {"service": "physiotherapy"}}})
    assert not ok["result"]["isError"]
    assert "wa-book" in json.loads(ok["result"]["content"][0]["text"])["url"]
    bad = mcp_server.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                             "params": {"name": "booking_link", "arguments": {"service": "x"}}})
    assert bad["result"]["isError"]


def test_wa_id_comes_from_env_not_the_model(monkeypatch):
    seen = {}
    monkeypatch.setattr(mcp_server, "run_tool",
                        lambda name, args, wa_id: (seen.update(wa_id=wa_id) or {}, False))
    monkeypatch.setenv("WA_ID", "6591234567")
    mcp_server.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                       "params": {"name": "my_appointments",
                                  "arguments": {"wa_id": "6500000000"}}})
    assert seen["wa_id"] == "6591234567"
