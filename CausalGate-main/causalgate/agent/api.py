from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional
from urllib.parse import urlparse

from .. import __version__ as CAUSALGATE_VERSION
from .feedback_loop import record_agent_outcome
from .modes import list_agent_modes
from .runner import CausalGateAgent
from .types import as_dict, clean_str


def _json_default(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return str(value)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=_json_default)


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


@dataclass
class AgentAPIConfig:
    """Configuration for CausalGate's stdlib-only agent HTTP API.

    The API is intentionally conservative:
    - /agent/decide never executes tools.
    - /agent/run defaults to no execution unless execute_tools=true is provided.
    - even then, execution still requires ToolRegistry + ToolGuard approval.
    """

    host: str = "127.0.0.1"
    port: int = 8088
    evidence_output_dir: str = "out"
    audit_log_path: str = "out/agent_learning_events.jsonl"
    enable_evidence_reader: bool = True
    default_execute_tools: bool = False
    default_agent_mode: str = "general_agent"
    action_registry_path: str = "action_registry.yaml"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CausalGateThreadingHTTPServer(ThreadingHTTPServer):
    """Threaded HTTP server with daemon request threads for tests and demos.

    Python's default ThreadingHTTPServer can keep non-daemon request threads
    alive while a client connection is open. That is fine for long-running
    services, but it can make local tests and demo shutdowns hang. CausalGate's
    stdlib API is intentionally small, so daemon request threads are safer here.
    """

    daemon_threads = True
    block_on_close = False


AgentFactory = Callable[[AgentAPIConfig, Mapping[str, Any]], Any]


def build_agent_for_api(config: AgentAPIConfig, payload: Mapping[str, Any] | None = None) -> CausalGateAgent:
    payload = payload or {}
    return CausalGateAgent(
        evidence_output_dir=payload.get("evidence_output_dir") or config.evidence_output_dir,
        enable_evidence_reader=_safe_bool(payload.get("enable_evidence_reader"), config.enable_evidence_reader)
        and not _safe_bool(payload.get("disable_evidence_reader"), False),
        action_registry_path=payload.get("action_registry_path") or config.action_registry_path,
        default_agent_mode=payload.get("default_agent_mode") or config.default_agent_mode,
        audit_log_path=payload.get("audit_log_path") or config.audit_log_path,
    )


def _call_agent(
    payload: Mapping[str, Any],
    *,
    agent: Any | None = None,
    config: AgentAPIConfig | None = None,
    agent_factory: AgentFactory | None = None,
    force_no_execute: bool = False,
) -> Dict[str, Any]:
    config = config or AgentAPIConfig()
    body = dict(payload or {})
    api_agent = agent or (agent_factory(config, body) if agent_factory else build_agent_for_api(config, body))

    requested_execute = _safe_bool(body.get("execute_tools"), config.default_execute_tools)
    execute_tools = False if force_no_execute else requested_execute

    user_message = clean_str(body.get("user_message") or body.get("message"))
    raw_candidate_actions = body.get("candidate_actions")
    candidate_actions = list(raw_candidate_actions or []) if raw_candidate_actions is not None else None

    result = api_agent.run(
        user_message,
        trusted_runtime_context=as_dict(body.get("trusted_runtime_context") or body.get("trusted_context")),
        untrusted_llm_context=as_dict(body.get("untrusted_llm_context") or body.get("llm_context")),
        planner_context=as_dict(body.get("planner_context")),
        candidate_actions=candidate_actions,
        tool_args=as_dict(body.get("tool_args")),
        execute_tools=execute_tools,
        agent_mode=body.get("agent_mode") or config.default_agent_mode,
    )
    data = result.to_dict() if hasattr(result, "to_dict") else dict(result or {})
    data.setdefault("api", {})
    data["api"].update(
        {
            "endpoint_mode": "decide" if force_no_execute else "run",
            "execute_tools_requested": requested_execute,
            "execute_tools_effective": execute_tools,
            "safe_default": not config.default_execute_tools,
            "agent_mode": body.get("agent_mode") or config.default_agent_mode,
        }
    )
    return data


def decide_agent_request(
    payload: Mapping[str, Any],
    *,
    agent: Any | None = None,
    config: AgentAPIConfig | None = None,
    agent_factory: AgentFactory | None = None,
) -> Dict[str, Any]:
    """Evaluate one agent turn without executing tools."""

    return _call_agent(payload, agent=agent, config=config, agent_factory=agent_factory, force_no_execute=True)


def run_agent_request(
    payload: Mapping[str, Any],
    *,
    agent: Any | None = None,
    config: AgentAPIConfig | None = None,
    agent_factory: AgentFactory | None = None,
) -> Dict[str, Any]:
    """Run one agent turn.

    Tool execution remains opt-in at the HTTP layer and still requires the
    normal ToolRegistry/ToolGuard gates. With the default registry, no external
    tools are registered, so the runtime fails closed.
    """

    return _call_agent(payload, agent=agent, config=config, agent_factory=agent_factory, force_no_execute=False)


def record_agent_outcome_request(payload: Mapping[str, Any], *, config: AgentAPIConfig | None = None) -> Dict[str, Any]:
    """Append an observed outcome for a prior agent decision."""

    config = config or AgentAPIConfig()
    body = dict(payload or {})
    return record_agent_outcome(
        path=body.get("audit_log_path") or config.audit_log_path,
        decision_event_id=clean_str(body.get("decision_event_id")),
        request_id=clean_str(body.get("request_id")),
        selected_action=clean_str(body.get("selected_action")),
        outcome=clean_str(body.get("outcome"), "unknown"),
        success=body.get("success") if isinstance(body.get("success"), bool) else None,
        harm=body.get("harm") if isinstance(body.get("harm"), bool) else None,
        user_satisfaction=body.get("user_satisfaction"),
        latency_ms=body.get("latency_ms"),
        metadata=as_dict(body.get("metadata")),
    )


def _response(handler: BaseHTTPRequestHandler, status: int, payload: Mapping[str, Any]) -> None:
    raw = _json_dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    # Keep the stdlib API deterministic in tests and short-lived demos:
    # every response explicitly closes the connection after writing the body.
    handler.send_header("Connection", "close")
    handler.end_headers()
    handler.wfile.write(raw)
    try:
        handler.wfile.flush()
    except Exception:
        pass
    handler.close_connection = True


def _read_json_body(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("Request body must be a JSON object.")
    return dict(value)


def make_agent_api_handler(
    *,
    config: AgentAPIConfig | None = None,
    agent_factory: AgentFactory | None = None,
):
    """Create a BaseHTTPRequestHandler subclass bound to API config."""

    config = config or AgentAPIConfig()

    class AgentAPIHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"
        server_version = f"CausalGateAgentAPI/{CAUSALGATE_VERSION}"

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler naming
            path = urlparse(self.path).path.rstrip("/") or "/"
            try:
                if path == "/health":
                    _response(self, 200, {"status": "ok", "service": "causalgate_agent_api", "config": config.to_dict()})
                    return
                if path == "/agent/tools":
                    agent = agent_factory(config, {}) if agent_factory else build_agent_for_api(config, {})
                    registry = getattr(agent, "tool_registry", None)
                    tools = registry.to_dict() if registry is not None and hasattr(registry, "to_dict") else {}
                    _response(self, 200, {"status": "ok", "tools": tools})
                    return
                if path == "/agent/modes":
                    _response(self, 200, {"status": "ok", "modes": list_agent_modes(), "default_agent_mode": config.default_agent_mode})
                    return
                _response(self, 404, {"status": "error", "error": "not_found", "path": path})
            except Exception as exc:  # fail closed and return a structured error
                _response(self, 500, {"status": "error", "error": type(exc).__name__, "message": str(exc)})

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler naming
            path = urlparse(self.path).path.rstrip("/") or "/"
            try:
                body = _read_json_body(self)
                if path == "/agent/decide":
                    _response(self, 200, decide_agent_request(body, config=config, agent_factory=agent_factory))
                    return
                if path in {"/agent/run", "/agent/tool-guard"}:
                    # /agent/tool-guard is an alias for one guarded run. It does
                    # not expose direct ToolGuard bypasses; it still starts from
                    # the agent runtime and safe registry.
                    _response(self, 200, run_agent_request(body, config=config, agent_factory=agent_factory))
                    return
                if path == "/agent/outcome":
                    _response(self, 200, record_agent_outcome_request(body, config=config))
                    return
                _response(self, 404, {"status": "error", "error": "not_found", "path": path})
            except json.JSONDecodeError as exc:
                _response(self, 400, {"status": "error", "error": "invalid_json", "message": str(exc)})
            except Exception as exc:
                _response(self, 500, {"status": "error", "error": type(exc).__name__, "message": str(exc)})

        def log_message(self, format: str, *args: Any) -> None:
            # Keep library/tests quiet; callers can put a proxy/server logger in
            # front if they need request logs.
            return

    return AgentAPIHandler


def serve(config: AgentAPIConfig | None = None) -> None:
    config = config or AgentAPIConfig()
    handler = make_agent_api_handler(config=config)
    server = CausalGateThreadingHTTPServer((config.host, config.port), handler)
    print(f"CausalGate Agent API listening on http://{config.host}:{config.port}")
    print("Endpoints: GET /health, GET /agent/tools, GET /agent/modes, POST /agent/decide, POST /agent/run, POST /agent/outcome")
    server.serve_forever()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the CausalGate Agent Runtime API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--evidence-out-dir", default="out")
    parser.add_argument("--audit-log", default="out/agent_learning_events.jsonl")
    parser.add_argument("--disable-evidence-reader", action="store_true")
    parser.add_argument("--default-agent-mode", default="general_agent")
    parser.add_argument("--action-registry", default="action_registry.yaml")
    parser.add_argument("--default-execute-tools", action="store_true", help="Unsafe for demos: make /agent/run execute by default when possible.")
    args = parser.parse_args(argv)

    serve(
        AgentAPIConfig(
            host=args.host,
            port=args.port,
            evidence_output_dir=args.evidence_out_dir,
            audit_log_path=args.audit_log,
            enable_evidence_reader=not args.disable_evidence_reader,
            default_execute_tools=bool(args.default_execute_tools),
            default_agent_mode=args.default_agent_mode,
            action_registry_path=args.action_registry,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
