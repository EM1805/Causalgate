from __future__ import annotations

from causalgate import __version__
from causalgate.mcp.http_server import (
    SERVICE_NAME,
    handle_mcp_http_payload,
    handle_tool_call_http_payload,
    health_payload,
)


def test_health_payload_exposes_mcp_endpoint_and_tools():
    payload = health_payload()
    assert payload["status"] == "ok"
    assert payload["service"] == SERVICE_NAME
    assert payload["version"] == __version__
    assert payload["mcp_endpoint"] == "/mcp"
    assert payload["tool_count"] >= 1
    assert "causalgate_health" in payload["tools"]


def test_http_mcp_initialize():
    response = handle_mcp_http_payload({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert response["result"]["serverInfo"]["name"] == "causalgate-mcp"
    assert response["result"]["serverInfo"]["version"] == __version__
    assert "tools" in response["result"]["capabilities"]


def test_http_mcp_tools_list():
    response = handle_mcp_http_payload({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tools = response["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert "causalgate_health" in names
    assert "causalgate_veto_hypothesis" in names
    assert "causalgate_run_research_cycle" in names


def test_http_mcp_tools_call_health():
    response = handle_mcp_http_payload({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "causalgate_health", "arguments": {}},
    })
    structured = response["result"]["structuredContent"]
    assert structured["status"] == "ok"
    assert structured["service"] == "causalgate-mcp"
    assert structured["version"] == __version__


def test_direct_tools_call_missing_name_is_safe_error():
    response = handle_tool_call_http_payload({"arguments": {}})
    assert response["ok"] is False
    assert response["error"]["code"] == "MISSING_TOOL_NAME"


def test_http_mcp_batch_request():
    response = handle_mcp_http_payload([
        {"jsonrpc": "2.0", "id": "a", "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": "b", "method": "tools/list", "params": {}},
    ])
    assert isinstance(response, list)
    assert len(response) == 2
    assert response[0]["id"] == "a"
    assert response[1]["id"] == "b"
