from __future__ import annotations

"""Minimal stdio JSON-RPC server for CausalGate MCP-style tool calls."""

import json
import sys
from typing import Any, Dict, Mapping

from causalgate import __version__

from .tools import call_tool, list_tools


def _jsonrpc_result(msg_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _jsonrpc_error(msg_id: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
    if data is not None:
        payload["error"]["data"] = data
    return payload


def _tool_result(result: Mapping[str, Any]) -> Dict[str, Any]:
    is_error = "error" in result or result.get("ok") is False
    if is_error:
        summary = result.get("error", {}).get("message") if isinstance(result.get("error"), Mapping) else "CausalGate tool error"
    else:
        decision = result.get("decision") or result.get("status") or result.get("tool") or "ok"
        summary = f"CausalGate result: {decision}"
    return {
        "content": [{"type": "text", "text": str(summary)}],
        "structuredContent": dict(result),
        "isError": bool(is_error),
    }


def initialize_result() -> Dict[str, Any]:
    return {
        "protocolVersion": "2024-11-05",
        "serverInfo": {"name": "causalgate-mcp", "title": "CausalGate Causal Scientific Veto", "version": __version__},
        "instructions": "Use CausalGate as a conservative causal/scientific reviewer. It can normalize hypotheses, assess falsification, run identification-aware vetoes, and return whether a claim should be blocked, revised, tested more, abstained on, or treated only as a final candidate for testing.",
        "capabilities": {"tools": {"listChanged": False}},
    }


def handle_message(message: Mapping[str, Any]) -> Dict[str, Any] | None:
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") if isinstance(message.get("params"), Mapping) else {}

    if method == "initialize":
        return _jsonrpc_result(msg_id, initialize_result())
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _jsonrpc_result(msg_id, {})
    if method == "tools/list":
        return _jsonrpc_result(msg_id, list_tools())
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), Mapping) else {}
        if not isinstance(name, str) or not name.strip():
            return _jsonrpc_error(msg_id, -32602, "Missing tool name for tools/call")
        return _jsonrpc_result(msg_id, _tool_result(call_tool(name.strip(), arguments)))

    return _jsonrpc_error(msg_id, -32601, f"Method not found: {method}", {"supported_methods": ["initialize", "notifications/initialized", "ping", "tools/list", "tools/call"]})


def main() -> int:
    for line in sys.stdin:
        text = line.strip()
        if not text:
            continue
        try:
            message = json.loads(text)
            response = handle_message(message) if isinstance(message, Mapping) else _jsonrpc_error(None, -32600, "Invalid request: JSON-RPC message must be an object")
        except Exception as exc:
            response = _jsonrpc_error(None, -32700, f"Invalid request: {type(exc).__name__}: {exc}")
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
