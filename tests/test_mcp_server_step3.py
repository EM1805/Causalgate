from __future__ import annotations

from causalgate.mcp.server import handle_message


def test_mcp_tools_list_and_call_health():
    resp = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert resp["result"]["tools"]

    call = handle_message({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "causalgate_health", "arguments": {}},
    })
    assert call["result"]["structuredContent"]["status"] == "ok"
