from __future__ import annotations

"""Authenticated, single-tenant beta decision API. No tools are executed."""

import logging
from typing import Any, Dict, Mapping

try:  # pragma: no cover - exercised in import tests when FastAPI is installed
    from fastapi import FastAPI, HTTPException
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import PlainTextResponse, JSONResponse
except Exception as exc:  # pragma: no cover
    FastAPI = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]
    PlainTextResponse = None  # type: ignore[assignment]
    _FASTAPI_IMPORT_ERROR = exc
else:
    _FASTAPI_IMPORT_ERROR = None

from causalgate import __version__
from causalgate.agent_firewall.gateway import AgentActionFirewall, AgentFirewallResult
from causalgate.api.security import APISettings, APISecurityMiddleware, validate_json
from causalgate.agent_firewall.policy import load_firewall_policy
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
            "ready": "/v1/ready",
        },
        "product": "CausalGate Agent Causal Firewall",
        "decisions": ["PASS", "REVIEW", "HARD_BLOCK"],
        "authority_score_bands": {
            "0-39": "weak authority -> HARD_BLOCK",
            "40-69": "partial authority -> REVIEW",
            "70-100": "sufficient authority -> PASS unless policy/risk requires review",
        },
    }


_STRINGS = {"action", "action_name", "candidate_action", "tool_name", "tool", "risk_level",
            "environment", "action_type", "target_resource", "evidence_available", "treatment",
            "outcome", "request_id", "user_message"}
_BOOLS = {"approval_present", "rollback_available", "requires_user_confirmation", "require_causal_evidence"}
_OBJECTS = {"tool_args", "trusted_runtime_context", "trusted_context", "untrusted_llm_context",
            "llm_context", "scm_graph", "causal_query", "causal_evidence", "evidence"}
_TRUSTED = (_STRINGS | _BOOLS | {"recipient_external", "share_scope_external", "policy_bypass",
            "live_trading", "real_money", "external_counterparty", "irreversible", "reversibility",
            "resource_sensitivity", "blast_radius", "service_criticality", "user_intent_score"})
_TRUSTED_BOOLS = _BOOLS | {"recipient_external", "share_scope_external", "policy_bypass", "live_trading",
                         "real_money", "external_counterparty", "irreversible"}


def _validate_payload(payload):
    if not isinstance(payload, Mapping) or not payload:
        raise ValueError("A non-empty JSON object is required")
    validate_json(payload)
    if set(payload) - (_STRINGS | _BOOLS | _OBJECTS):
        raise ValueError("Unknown or server-controlled request field")
    for key, value in payload.items():
        if key in _STRINGS and (not isinstance(value, str) or len(value) > 4096):
            raise ValueError("Invalid string field")
        if key in _BOOLS and type(value) is not bool:
            raise ValueError("Boolean fields must be JSON booleans")
        if key in _OBJECTS and not isinstance(value, dict):
            raise ValueError("Evidence and context fields must be JSON objects")
    for name in ("trusted_runtime_context", "trusted_context"):
        for key, value in payload.get(name, {}).items():
            if key not in _TRUSTED or isinstance(value, (dict, list)):
                raise ValueError("Invalid trusted context field")
            if key in _TRUSTED_BOOLS and type(value) is not bool:
                raise ValueError("Trusted boolean fields must be JSON booleans")
            if key in _STRINGS and not isinstance(value, str):
                raise ValueError("Invalid trusted context string")
    query = payload.get("causal_query", {})
    if set(query) - {"scm_graph", "graph", "treatment", "outcome", "adjustment_set", "strategy_hint", "query_id", "effect", "time_window_days"}:
        raise ValueError("Unsupported causal query field")
    for graph in (payload.get("scm_graph", {}), query.get("scm_graph", {}), query.get("graph", {})):
        if not isinstance(graph, dict):
            raise ValueError("Graph must be an object")
        if set(graph) - {"nodes", "edges", "directed_edges", "bidirected_edges"}:
            raise ValueError("Unsupported graph field")
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        directed = graph.get("directed_edges", [])
        bidirected = graph.get("bidirected_edges", [])
        if not all(isinstance(v, list) for v in (nodes, edges, directed, bidirected)) or len(nodes) > 8 or len(edges) + len(directed) + len(bidirected) > 32:
            raise ValueError("Beta graph limits exceeded")
        from causalgate.causal_core.identification import normalize_scm_graph
        if len(normalize_scm_graph(graph)["nodes"]) > 8:
            raise ValueError("Beta graph limits exceeded")
    if not any(payload.get(key) for key in ("action", "action_name", "candidate_action", "tool_name", "tool")):
        raise ValueError("An action or tool name is required")


def _firewall_from_settings(settings: APISettings) -> AgentActionFirewall:
    return AgentActionFirewall(
        policy=settings.policy_path,
        enable_tool_guard=settings.enable_tool_guard,
        audit_log_path=settings.audit_log_path,
    )


def guard_action(payload: Mapping[str, Any] | None, *, settings: APISettings | None = None) -> AgentFirewallResult:
    """Evaluate one action package through the product firewall.

    Accepted top-level fields are intentionally aligned with the Python API and
    CLI: ``action``, ``tool_name``, ``risk_level``, ``environment``,
    ``action_type``, ``target_resource``, ``trusted_runtime_context``,
    ``untrusted_llm_context``, ``causal_evidence``/``evidence``,
    ``treatment``, ``outcome`` and ``require_causal_evidence``.
    """

    _validate_payload(payload)
    payload = dict(payload)

    trusted = _as_dict(payload.get("trusted_runtime_context") or payload.get("trusted_context"))
    untrusted = _as_dict(payload.get("untrusted_llm_context") or payload.get("llm_context"))
    environment = trusted.get("environment", payload.get("environment", ""))
    risk_level = trusted.get("risk_level", payload.get("risk_level", ""))
    action_type = trusted.get("action_type", payload.get("action_type", ""))
    if not environment.strip() or environment.strip().lower() == "unknown":
        raise ValueError("An explicit environment is required")
    if risk_level not in {"low", "medium", "high", "critical"}:
        raise ValueError("An explicit risk level is required")
    if action_type not in {"read", "query", "mutation", "write", "delete", "destructive", "execute", "communicate", "share"}:
        raise ValueError("An explicit action type is required")
    action = _clean_str(
        payload.get("action")
        or payload.get("action_name")
        or payload.get("candidate_action")
        or payload.get("tool_name"),
        "agent_action",
    )
    tool_name = _clean_str(payload.get("tool_name") or payload.get("tool") or action, action)
    evidence = payload.get("causal_evidence") if "causal_evidence" in payload else payload.get("evidence")

    firewall = _firewall_from_settings(settings or APISettings.from_env())
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
        # A client cannot opt a state-changing or causal action out of evidence checks.
        require_causal_evidence=bool(payload.get("require_causal_evidence") or payload.get("treatment")
            or payload.get("outcome") or trusted.get("treatment") or trusted.get("outcome")
            or payload.get("scm_graph") or payload.get("causal_query")
            or evidence is not None or action_type not in {"read", "query"}),
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


def create_app(settings: APISettings | None = None) -> "FastAPI":
    """Create the CausalGate product API app."""

    _require_fastapi()
    settings = settings or APISettings.from_env()
    # Reject an invalid operator policy at startup, before any traffic is accepted.
    load_firewall_policy(settings.policy_path)
    api = FastAPI(
        title="CausalGate API",
        version=__version__,
        description="Causal firewall API for AI-agent actions with causal authority scoring.",
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
    )
    api.add_middleware(APISecurityMiddleware, settings=settings)

    @api.exception_handler(RequestValidationError)
    async def invalid_request(_request, _exc):
        return JSONResponse(status_code=422, content={"detail": "Invalid request body"})

    @api.get("/v1/health")
    def health() -> Dict[str, Any]:
        return health_payload()

    @api.get("/v1/ready")
    def ready() -> Dict[str, Any]:
        if not settings.api_key:
            raise HTTPException(status_code=503, detail="API authentication is not configured")
        return {"status": "ready"}

    @api.post("/v1/guard")
    def guard(payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return guard_action(payload, settings=settings).to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid action package") from exc
        except Exception as exc:
            logging.getLogger(__name__).exception("Guard evaluation failed")
            raise HTTPException(status_code=500, detail="Decision evaluation failed; do not execute the action") from exc

    @api.post("/v1/guard/markdown", response_class=PlainTextResponse)
    def guard_markdown(payload: Dict[str, Any]) -> str:
        try:
            return render_markdown_report(guard_action(payload, settings=settings))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid action package") from exc
        except Exception as exc:
            logging.getLogger(__name__).exception("Guard evaluation failed")
            raise HTTPException(status_code=500, detail="Decision evaluation failed; do not execute the action") from exc

    @api.get("/")
    def root() -> Dict[str, Any]:
        return {
            "service": SERVICE_NAME,
            "message": "CausalGate API is running. Use /v1/health or POST /v1/guard.",
            "beta": True,
        }

    return api


app = create_app()


__all__ = ["API_VERSION", "SERVICE_NAME", "app", "create_app", "guard_action", "health_payload"]
