from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from causalgate.contracts import DecisionPackage
from causalgate.gate import DecisionGate

from .blocked_response import build_blocked_response
from .execution_policy import (
    ASK_USER,
    BLOCK,
    DEFAULT_EXECUTION_POLICY,
    EXECUTE,
    EXECUTE_WITH_WARNING,
    ExecutionPolicy,
)


ToolExecutor = Callable[[Dict[str, Any]], Any]


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _decision_to_dict(decision: DecisionPackage | Mapping[str, Any]) -> Dict[str, Any]:
    if isinstance(decision, DecisionPackage):
        return decision.to_dict()
    if isinstance(decision, Mapping):
        return dict(decision)
    return {}


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default

def _payload_with_split_context(
    action_payload: Any,
    *,
    trusted_runtime_context: Mapping[str, Any] | None = None,
    untrusted_llm_context: Mapping[str, Any] | None = None,
    tool_name: str = "",
) -> Any:
    """Attach split contexts to a mapping payload without mutating caller data."""

    if not isinstance(action_payload, Mapping):
        return action_payload

    payload = dict(action_payload)
    trusted = _as_dict(payload.get("trusted_runtime_context") or payload.get("trusted_context"))
    untrusted = _as_dict(payload.get("untrusted_llm_context") or payload.get("llm_context"))

    trusted.update(_as_dict(trusted_runtime_context))
    untrusted.update(_as_dict(untrusted_llm_context))

    if tool_name:
        trusted.setdefault("tool_name", tool_name)

    if trusted:
        payload["trusted_runtime_context"] = trusted
    if untrusted:
        payload["untrusted_llm_context"] = untrusted
    return payload



@dataclass
class ToolGuardResult:
    """Result returned after CausalGate enforces a tool-call decision."""

    status: str = "blocked"
    executed: bool = False
    blocked: bool = True
    needs_user_confirmation: bool = False
    execution_action: str = BLOCK
    tool_name: str = ""
    tool_args: Dict[str, Any] = field(default_factory=dict)
    decision_package: Dict[str, Any] = field(default_factory=dict)
    tool_result: Any = None
    blocked_response: Dict[str, Any] = field(default_factory=dict)
    warning: str = ""
    error: Dict[str, Any] = field(default_factory=dict)
    audit_payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ToolGuard:
    """Pre-execution guard for AI-agent tool calls.

    The agent/LLM may propose a tool call, but this class is the enforcement
    boundary: it calls CausalGate's DecisionGate first and executes the supplied
    tool only when the resulting decision is explicitly executable.
    """

    def __init__(
        self,
        *,
        decision_gate: Any | None = None,
        policy: ExecutionPolicy | None = None,
        audit_log_path: str | Path | None = None,
        **gate_kwargs: Any,
    ) -> None:
        self.decision_gate = decision_gate or DecisionGate(**gate_kwargs)
        self.policy = policy or DEFAULT_EXECUTION_POLICY
        self.audit_log_path = Path(audit_log_path) if audit_log_path else None

    def evaluate(
        self,
        action_payload: Any,
        *,
        trusted_runtime_context: Mapping[str, Any] | None = None,
        untrusted_llm_context: Mapping[str, Any] | None = None,
        tool_name: str = "",
    ) -> Dict[str, Any]:
        """Return a plain DecisionPackage dict without executing anything."""

        payload = _payload_with_split_context(
            action_payload,
            trusted_runtime_context=trusted_runtime_context,
            untrusted_llm_context=untrusted_llm_context,
            tool_name=tool_name,
        )
        decision = self.decision_gate.evaluate(payload)
        return _decision_to_dict(decision)

    def guard_tool_call(
        self,
        action_payload: Any,
        *,
        tool_executor: ToolExecutor | None = None,
        tool_args: Mapping[str, Any] | None = None,
        tool_name: str = "",
        trusted_runtime_context: Mapping[str, Any] | None = None,
        untrusted_llm_context: Mapping[str, Any] | None = None,
    ) -> ToolGuardResult:
        """Evaluate and conditionally execute one tool call.

        ``tool_executor`` is intentionally a callable that receives a single
        dictionary. This keeps the guard generic across shell tools, API tools,
        file tools, calendar/email tools, and custom agent functions.
        """

        guarded_payload = _payload_with_split_context(
            action_payload,
            trusted_runtime_context=trusted_runtime_context,
            untrusted_llm_context=untrusted_llm_context,
            tool_name=tool_name,
        )
        decision = self.evaluate(guarded_payload)
        execution_action = self.policy.action_for(decision.get("decision", "abstain"))
        args = _as_dict(tool_args)
        resolved_tool_name = _clean_str(
            tool_name
            or decision.get("selected_action")
            or decision.get("candidate_action")
            or _as_dict(guarded_payload).get("tool_name")
            or _as_dict(_as_dict(guarded_payload).get("trusted_runtime_context")).get("tool_name")
            or _as_dict(guarded_payload).get("action_name")
            or _as_dict(guarded_payload).get("candidate_action")
        )

        if execution_action in {BLOCK, ASK_USER}:
            result = ToolGuardResult(
                status="needs_user_confirmation" if execution_action == ASK_USER else "blocked",
                executed=False,
                blocked=True,
                needs_user_confirmation=execution_action == ASK_USER,
                execution_action=execution_action,
                tool_name=resolved_tool_name,
                tool_args=args,
                decision_package=decision,
                blocked_response=build_blocked_response(decision, execution_action=execution_action),
                audit_payload=self._build_audit_payload(
                    decision=decision,
                    execution_action=execution_action,
                    tool_name=resolved_tool_name,
                    tool_args=args,
                    executed=False,
                ),
            )
            self._append_audit(result)
            return result

        warning = ""
        if execution_action == EXECUTE_WITH_WARNING:
            warning = _clean_str(
                decision.get("reason"),
                "CausalGate allowed execution with warning; execute only with mitigation/audit.",
            )

        if tool_executor is None:
            result = ToolGuardResult(
                status="permitted_not_executed",
                executed=False,
                blocked=False,
                needs_user_confirmation=False,
                execution_action=execution_action,
                tool_name=resolved_tool_name,
                tool_args=args,
                decision_package=decision,
                warning=warning,
                audit_payload=self._build_audit_payload(
                    decision=decision,
                    execution_action=execution_action,
                    tool_name=resolved_tool_name,
                    tool_args=args,
                    executed=False,
                ),
            )
            self._append_audit(result)
            return result

        try:
            tool_result = tool_executor(args)
            result = ToolGuardResult(
                status="executed_with_warning" if execution_action == EXECUTE_WITH_WARNING else "executed",
                executed=True,
                blocked=False,
                needs_user_confirmation=False,
                execution_action=execution_action,
                tool_name=resolved_tool_name,
                tool_args=args,
                decision_package=decision,
                tool_result=tool_result,
                warning=warning,
                audit_payload=self._build_audit_payload(
                    decision=decision,
                    execution_action=execution_action,
                    tool_name=resolved_tool_name,
                    tool_args=args,
                    executed=True,
                ),
            )
            self._append_audit(result)
            return result
        except Exception as exc:  # pragma: no cover - defensive tool boundary
            result = ToolGuardResult(
                status="tool_error",
                executed=False,
                blocked=False,
                needs_user_confirmation=False,
                execution_action=execution_action,
                tool_name=resolved_tool_name,
                tool_args=args,
                decision_package=decision,
                warning=warning,
                error={"type": type(exc).__name__, "message": str(exc)},
                audit_payload=self._build_audit_payload(
                    decision=decision,
                    execution_action=execution_action,
                    tool_name=resolved_tool_name,
                    tool_args=args,
                    executed=False,
                    error={"type": type(exc).__name__, "message": str(exc)},
                ),
            )
            self._append_audit(result)
            return result

    def _build_audit_payload(
        self,
        *,
        decision: Mapping[str, Any],
        execution_action: str,
        tool_name: str,
        tool_args: Mapping[str, Any],
        executed: bool,
        error: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        return {
            "event_type": "tool_guard",
            "request_id": _as_dict(decision.get("audit_payload")).get("request_id", ""),
            "selected_action": decision.get("selected_action", ""),
            "gate_decision": decision.get("decision", "abstain"),
            "runtime_decision": decision.get("runtime_decision", "UNKNOWN"),
            "execution_action": execution_action,
            "executed": executed,
            "blocked": execution_action in {BLOCK, ASK_USER},
            "needs_user_confirmation": execution_action == ASK_USER,
            "tool_name": tool_name,
            "tool_args": dict(tool_args or {}),
            "reason": decision.get("reason", ""),
            "reason_codes": list(decision.get("reason_codes", []) or []),
            "error": dict(error or {}),
        }

    def _append_audit(self, result: ToolGuardResult) -> None:
        if not self.audit_log_path:
            return
        from causalgate.learning.audit_log import AuditLog

        AuditLog(self.audit_log_path).append_event(result.audit_payload)


# Convenience aliases for embedding in agent frameworks.
def guard_tool_call(
    action_payload: Any,
    *,
    tool_executor: ToolExecutor | None = None,
    tool_args: Mapping[str, Any] | None = None,
    tool_name: str = "",
    trusted_runtime_context: Mapping[str, Any] | None = None,
    untrusted_llm_context: Mapping[str, Any] | None = None,
    decision_gate: Any | None = None,
    policy: ExecutionPolicy | None = None,
    audit_log_path: str | Path | None = None,
    **gate_kwargs: Any,
) -> Dict[str, Any]:
    return ToolGuard(
        decision_gate=decision_gate,
        policy=policy,
        audit_log_path=audit_log_path,
        **gate_kwargs,
    ).guard_tool_call(
        action_payload,
        tool_executor=tool_executor,
        tool_args=tool_args,
        tool_name=tool_name,
        trusted_runtime_context=trusted_runtime_context,
        untrusted_llm_context=untrusted_llm_context,
    ).to_dict()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a tool call through CausalGate Agent Tool Guard.")
    parser.add_argument("--input", required=True, help="Path to ActionPackage/tool-call JSON.")
    parser.add_argument("--tool-args", default="", help="Optional JSON file with tool arguments. CLI mode never executes a real tool.")
    parser.add_argument("--tool-name", default="")
    parser.add_argument("--out", default="out/agent_tool_guard_result.json")
    parser.add_argument("--audit-log", default="")
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    tool_args = json.loads(Path(args.tool_args).read_text(encoding="utf-8")) if args.tool_args else {}
    guard = ToolGuard(audit_log_path=args.audit_log or None)
    result = guard.guard_tool_call(payload, tool_args=tool_args, tool_name=args.tool_name).to_dict()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({
        "status": result.get("status"),
        "out": str(out_path),
        "executed": result.get("executed"),
        "blocked": result.get("blocked"),
        "execution_action": result.get("execution_action"),
        "gate_decision": _as_dict(result.get("decision_package")).get("decision"),
        "tool_name": result.get("tool_name"),
    }, indent=2))
    return 0


__all__ = ["ToolGuard", "ToolGuardResult", "guard_tool_call", "ToolExecutor"]


if __name__ == "__main__":
    raise SystemExit(main())
