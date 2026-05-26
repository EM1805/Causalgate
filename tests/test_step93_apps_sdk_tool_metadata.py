from __future__ import annotations

from causalgate import __version__
from causalgate.mcp.http_server import handle_mcp_http_payload, health_payload, metadata_payload
from causalgate.mcp.schemas import SECURITY_SCHEMES, app_metadata, list_tool_schemas


def _tool_by_name(name: str):
    return {tool["name"]: tool for tool in list_tool_schemas()}[name]


def test_step93_tool_descriptors_include_apps_sdk_metadata():
    tools = list_tool_schemas()
    assert len(tools) >= 8
    for tool in tools:
        assert tool["name"].startswith("causalgate_")
        assert isinstance(tool.get("title"), str) and tool["title"]
        assert tool["description"].startswith("Use this when")
        assert tool["inputSchema"]["type"] == "object"
        assert "outputSchema" in tool
        assert tool["securitySchemes"] == SECURITY_SCHEMES
        assert tool["_meta"]["securitySchemes"] == SECURITY_SCHEMES
        assert "openai/toolInvocation/invoking" in tool["_meta"]
        assert "openai/toolInvocation/invoked" in tool["_meta"]
        assert set(tool["annotations"]).issuperset({"readOnlyHint", "destructiveHint", "openWorldHint"})


def test_step93_veto_schema_is_hypothesis_wrapped_and_strict():
    tool = _tool_by_name("causalgate_veto_hypothesis")
    schema = tool["inputSchema"]
    assert schema["required"] == ["hypothesis"]
    assert schema["additionalProperties"] is False
    hyp = schema["properties"]["hypothesis"]
    assert "negative_control_variables" in hyp["properties"]
    assert "negative_control_tests" in hyp["properties"]
    assert "dag" in hyp["properties"]
    assert "identified_candidate" in hyp["properties"]["requested_claim_level"]["enum"]


def test_step93_initialize_ping_and_tool_call():
    init = handle_mcp_http_payload({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["title"] == "CausalGate Causal Scientific Veto"
    assert init["result"]["serverInfo"]["version"] == __version__
    assert init["result"]["capabilities"]["tools"]["listChanged"] is False

    ping = handle_mcp_http_payload({"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}})
    assert ping["result"] == {}

    response = handle_mcp_http_payload({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "causalgate_health", "arguments": {}}})
    assert response["result"]["isError"] is False
    assert len(response["result"]["content"][0]["text"]) < 120
    assert response["result"]["structuredContent"]["status"] == "ok"


def test_step93_metadata_payload():
    meta = app_metadata("https://example.hf.space")
    assert meta["mcp_endpoint"] == "https://example.hf.space/mcp"
    assert meta["auth"]["type"] == "none"
    assert meta["securitySchemes"] == SECURITY_SCHEMES
    assert health_payload()["metadata_endpoint"] == "/metadata"
    assert metadata_payload()["name"] == "CausalGate"


def test_step93_research_annotations():
    assert _tool_by_name("causalgate_run_research_cycle")["annotations"]["readOnlyHint"] is False
    assert _tool_by_name("causalgate_run_research_cycle")["annotations"]["idempotentHint"] is False
    assert _tool_by_name("causalgate_run_claude_research_cycle")["annotations"]["openWorldHint"] is True


def test_step93_repair_tool_is_exposed_in_schema():
    tool = _tool_by_name("causalgate_repair_hypothesis")
    assert tool["inputSchema"]["type"] == "object"
    assert "hypothesis" in tool["inputSchema"]["properties"]
    assert tool["annotations"]["readOnlyHint"] is False
