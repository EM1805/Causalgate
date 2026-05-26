from __future__ import annotations

"""Claude/HF-friendly HTTP entrypoint for CausalGate's MCP app.

The canonical MCP JSON-RPC handler still lives in ``http_server.py``.
This wrapper adds browser/probe-friendly routes around the same FastAPI app so
external connector setup is easier to diagnose, especially when a client opens
``/mcp`` with GET before sending JSON-RPC POST requests.
"""

from typing import Any, Dict

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from .http_server import app as _base_app
from .http_server import capabilities_payload, health_payload, metadata_payload

if _base_app is None:  # pragma: no cover - defensive import boundary
    raise RuntimeError("CausalGate MCP FastAPI app is unavailable. Install the hf extras and FastAPI dependencies.")

app = _base_app


@app.get("/mcp")
async def mcp_get(request: Request) -> JSONResponse:
    """Return diagnostics for humans/probes that open the MCP endpoint with GET.

    MCP tool calls must still use POST /mcp with a JSON-RPC body. This endpoint
    prevents a misleading 404/405 during connector setup and points users to the
    browser-testable endpoints.
    """
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse(
        {
            "ok": True,
            "service": "causalgate-mcp-http",
            "message": "This is the MCP JSON-RPC endpoint. Use POST /mcp for MCP calls; use GET /health or GET /tools for browser checks.",
            "mcp_endpoint": f"{base_url}/mcp",
            "health_endpoint": f"{base_url}/health",
            "tools_endpoint": f"{base_url}/tools",
            "metadata_endpoint": f"{base_url}/metadata",
            "capabilities_endpoint": f"{base_url}/capabilities",
            "post_example": {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {},
            },
            "visibility_note": "If this Hugging Face Space is private, external clients such as Claude may see 404 unless they can authenticate. Make the Space public or put it behind an auth flow Claude supports.",
        }
    )


@app.options("/mcp")
async def mcp_options() -> Response:
    return Response(
        status_code=204,
        headers={
            "Allow": "GET, POST, OPTIONS",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "content-type, accept, mcp-session-id",
        },
    )


@app.get("/.well-known/mcp.json")
async def mcp_well_known(request: Request) -> Dict[str, Any]:
    base_url = str(request.base_url).rstrip("/")
    return {
        "name": "CausalGate",
        "description": metadata_payload().get("description", "CausalGate MCP HTTP server"),
        "transport": "http-jsonrpc",
        "protocolVersion": "2024-11-05",
        "mcp_endpoint": f"{base_url}/mcp",
        "health": health_payload(),
        "capabilities": capabilities_payload(),
    }


__all__ = ["app"]
