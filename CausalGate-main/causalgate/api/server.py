from __future__ import annotations

"""Commercial/product HTTP API for CausalGate.

This module intentionally exposes the product story rather than the older MCP
research/demo story:

    POST /v1/guard  -> action + optional causal evidence -> PASS/REVIEW/HARD_BLOCK
    POST /v1/demo   -> writes the 60-second demo reports and returns a summary
    GET  /v1/health -> service metadata

The endpoints accept plain JSON objects to keep the API stable for external
agent frameworks, low-code tools, and future SDKs.  FastAPI/Pydantic validation
can be added later without changing the response contract.
"""

import os
from pathlib import Path
from typing import Any, Dict, Mapping

try:  # pragma: no cover - exercised in import tests when FastAPI is installed
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.responses import PlainTextResponse
except Exception as exc:  # pragma: no cover
    FastAPI = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]
    Query = None  # type: ignore[assignment]
    PlainTextResponse = None  # type: ignore[assignment]
    _FASTAPI_IMPORT_ERROR = exc
else:
    _FASTAPI_IMPORT_ERROR = None

from causalgate import __version__
from causalgate.agent_firewall.gateway import AgentActionFirewall, AgentFirewallResult
from causalgate.demo import run_product_demo
from causalgate.reports import render_markdown_report

SERVICE_NAME = "causalgate-api"
API_VERSION = "v1"


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _default_audit_log() -> str | None:
    path = os.getenv("CAUSALGATE_API_AUDIT_LOG", "").strip()
    return path or None


def health_payload() -> Dict[str, Any]:
    """Return machine-readable service metadata."""

    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": __version__,
        "api_version": API_VERSION,
        "endpoints": {
            "health": "/v1/health",
            "guard": "/v1/guard",
            "guard_markdown": "/v1/guard/markdown",
            "demo": "/v1/demo",
        },
        "product": "CausalGate Agent Causal Firewall",
        "decisions": ["PASS", "REVIEW", "HARD_BLOCK"],
        "authority_score_bands": {
            "0-39": "weak authority -> HARD_BLOCK",
            "40-69": "partial authority -> REVIEW",
            "70-100": "sufficient authority -> PASS unless policy/risk requires review",
        },
    }


def _firewall_from_payload(payload: Mapping[str, Any]) -> AgentActionFirewall:
    policy = payload.get("policy") or payload.get("policy_path") or None
    # Public API defaults to policy-only mode unless explicitly enabled.  This
    # avoids accidental tool execution in a service context while still allowing
    # enterprise callers to enable ToolGuard evaluation deliberately.
    enable_tool_guard = _bool(payload.get("enable_tool_guard"), default=False)
    return AgentActionFirewall(
        policy=policy,
        enable_tool_guard=enable_tool_guard,
        audit_log_path=payload.get("audit_log_path") or _default_audit_log(),
    )


def guard_action(payload: Mapping[str, Any] | None) -> AgentFirewallResult:
    """Evaluate one action package through the product firewall.

    Accepted top-level fields are intentionally aligned with the Python API and
    CLI: ``action``, ``tool_name``, ``risk_level``, ``environment``,
    ``action_type``, ``target_resource``, ``trusted_runtime_context``,
    ``untrusted_llm_context``, ``causal_evidence``/``evidence``,
    ``treatment``, ``outcome`` and ``require_causal_evidence``.
    """

    payload = _as_dict(payload)
    if not payload:
        raise ValueError("request body must be a JSON object")

    trusted = _as_dict(payload.get("trusted_runtime_context") or payload.get("trusted_context"))
    untrusted = _as_dict(payload.get("untrusted_llm_context") or payload.get("llm_context"))
    action = _clean_str(
        payload.get("action")
        or payload.get("action_name")
        or payload.get("candidate_action")
        or payload.get("tool_name"),
        "agent_action",
    )
    tool_name = _clean_str(payload.get("tool_name") or payload.get("tool") or action, action)
    evidence = payload.get("causal_evidence") if "causal_evidence" in payload else payload.get("evidence")

    firewall = _firewall_from_payload(payload)
    return firewall.evaluate(
        action=action,
        tool_name=tool_name,
        tool_args=_as_dict(payload.get("tool_args")),
        risk_level=_clean_str(trusted.get("risk_level") or payload.get("risk_level"), "unknown"),
        environment=_clean_str(trusted.get("environment") or payload.get("environment"), "unknown"),
        action_type=_clean_str(trusted.get("action_type") or payload.get("action_type"), "unknown"),
        target_resource=_clean_str(trusted.get("target_resource") or payload.get("target_resource"), ""),
        approval_present=_bool(trusted.get("approval_present", payload.get("approval_present")), False),
        rollback_available=_bool(trusted.get("rollback_available", payload.get("rollback_available")), False),
        requires_user_confirmation=_bool(trusted.get("requires_user_confirmation", payload.get("requires_user_confirmation")), False),
        evidence_available=_clean_str(trusted.get("evidence_available") or payload.get("evidence_available"), "unknown"),
        evidence=evidence,
        require_causal_evidence=_bool(payload.get("require_causal_evidence"), False),
        treatment=_clean_str(payload.get("treatment"), ""),
        outcome=_clean_str(payload.get("outcome"), ""),
        scm_graph=_as_dict(payload.get("scm_graph")),
        causal_query=_as_dict(payload.get("causal_query")),
        trusted_runtime_context=trusted,
        untrusted_llm_context=untrusted,
        request_id=_clean_str(payload.get("request_id"), ""),
        user_message=_clean_str(payload.get("user_message"), ""),
        # The public API deliberately does not execute tools.  It is a
        # pre-execution decision service.  Execution can be implemented by the
        # caller after PASS, or by a separate enterprise connector.
        execute=False,
    )


def _require_fastapi() -> None:
    if FastAPI is None or _FASTAPI_IMPORT_ERROR is not None:  # pragma: no cover
        raise RuntimeError(f"FastAPI server dependencies are not installed: {_FASTAPI_IMPORT_ERROR}")


def create_app() -> "FastAPI":
    """Create the CausalGate product API app."""

    _require_fastapi()
    api = FastAPI(
        title="CausalGate API",
        version=__version__,
        description="Causal firewall API for AI-agent actions with causal authority scoring.",
    )

    @api.get("/v1/health")
    def health() -> Dict[str, Any]:
        return health_payload()

    @api.post("/v1/guard")
    def guard(payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return guard_action(payload).to_dict()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.post("/v1/guard/markdown", response_class=PlainTextResponse)
    def guard_markdown(payload: Dict[str, Any]) -> str:
        try:
            return render_markdown_report(guard_action(payload))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.post("/v1/demo")
    def demo(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        body = payload or {}
        out_dir = _clean_str(body.get("out_dir"), "out/api-demo")
        enable_tool_guard = _bool(body.get("enable_tool_guard"), default=False)
        result = run_product_demo(
            out_dir=out_dir,
            policy=body.get("policy") or body.get("policy_path") or None,
            enable_tool_guard=enable_tool_guard,
        )
        return result.to_dict()

    @api.get("/")
    def root() -> Dict[str, Any]:
        return {
            "service": SERVICE_NAME,
            "message": "CausalGate API is running. Use /v1/health or POST /v1/guard.",
            "docs": "/docs",
        }

    return api


app = create_app()


__all__ = ["API_VERSION", "SERVICE_NAME", "app", "create_app", "guard_action", "health_payload"]
