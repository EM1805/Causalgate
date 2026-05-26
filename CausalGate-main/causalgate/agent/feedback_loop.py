from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from causalgate.learning import (
    DEFAULT_AUDIT_LOG_PATH,
    AuditEvent,
    AuditLog,
    OutcomeTracker,
    export_learning_datasets,
)


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _clean_lower(value: Any, default: str = "unknown") -> str:
    text = _clean_str(value, default).lower()
    return text or default


def _candidate_name(item: Any) -> str:
    if isinstance(item, Mapping):
        return _clean_str(
            item.get("action_name")
            or item.get("candidate_action")
            or item.get("selected_action")
            or item.get("name")
        )
    return _clean_str(item)


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        text = _clean_str(value)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _candidate_names_from_agent_result(result: Mapping[str, Any]) -> List[str]:
    names: List[str] = []
    llm_response = _as_dict(result.get("llm_response"))
    for item in _as_list(llm_response.get("candidate_actions")):
        name = _candidate_name(item)
        if name:
            names.append(name)

    brain = _as_dict(result.get("brain_result"))
    for item in _as_list(brain.get("evaluated_actions")):
        name = _candidate_name(item)
        if name:
            names.append(name)

    selected = _clean_str(result.get("selected_action"))
    if selected:
        names.insert(0, selected)
    recommended = _candidate_name(result.get("recommended_action"))
    if recommended:
        names.append(recommended)
    return _dedupe(names)


@dataclass
class AgentFeedbackSummary:
    """Small user-facing summary for one feedback write."""

    decision_event_id: str = ""
    outcome_event_id: str = ""
    request_id: str = ""
    selected_action: str = ""
    gate_decision: str = ""
    outcome: str = ""
    learning_log_path: str = ""
    dataset_exports: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AgentFeedbackLoop:
    """Bridge AgentRunner decisions into CausalGate's offline Learning Loop.

    Step 9 keeps the online path conservative: it does not train, estimate, or
    update policies live. It only appends structured decision/outcome events
    that offline Discovery, Estimation, RCT candidate building, or audit tools
    can consume later.
    """

    def __init__(self, path: str | Path = DEFAULT_AUDIT_LOG_PATH) -> None:
        self.path = Path(path)
        self.audit_log = AuditLog(self.path)
        self.outcome_tracker = OutcomeTracker(self.path)

    def build_decision_event(self, agent_result: Mapping[str, Any]) -> AuditEvent:
        result = dict(agent_result or {})
        brain = _as_dict(result.get("brain_result"))
        selected = _as_dict(brain.get("selected"))
        audit_payload = _as_dict(selected.get("audit_payload"))
        llm_response = _as_dict(result.get("llm_response"))
        evidence = _as_dict(result.get("evidence_bundle"))
        recommendation = _as_dict(result.get("recommendation"))
        tool_guard = _as_dict(result.get("tool_guard_result"))
        decision_package = _as_dict(tool_guard.get("decision_package"))

        selected_action = _clean_str(result.get("selected_action") or selected.get("selected_action"))
        gate_decision = _clean_str(result.get("decision") or selected.get("decision"), "abstain")
        runtime_decision = _clean_str(
            selected.get("runtime_decision")
            or decision_package.get("runtime_decision")
            or tool_guard.get("status"),
            "UNKNOWN",
        )
        evidence_query = _as_dict(evidence.get("query"))
        request_id = _clean_str(audit_payload.get("request_id") or evidence_query.get("request_id"))

        candidate_actions = _candidate_names_from_agent_result(result)
        reason_codes = [str(x) for x in selected.get("reason_codes", []) or []]
        if result.get("blocked") and "agent_runner_blocked" not in reason_codes:
            reason_codes.append("agent_runner_blocked")
        if result.get("executed") and "tool_executed" not in reason_codes:
            reason_codes.append("tool_executed")
        if result.get("recommendation") and "recommendation_generated" not in reason_codes:
            reason_codes.append("recommendation_generated")
        if evidence and "structured_causal_evidence_attached" not in reason_codes:
            reason_codes.append("structured_causal_evidence_attached")

        risk_level = _clean_str(
            selected.get("risk_level")
            or decision_package.get("risk_level")
            or _as_dict(audit_payload).get("risk_level"),
            "unknown",
        )
        evidence_tier = _clean_str(result.get("evidence_tier") or selected.get("evidence_tier"), "unknown")
        identification_tier = _clean_str(selected.get("identification_tier"), "unknown")
        confidence = _clean_str(selected.get("confidence"), "unknown")

        return AuditEvent(
            event_type="decision",
            request_id=request_id,
            user_message=_clean_str(result.get("user_message") or llm_response.get("user_message")),
            candidate_actions=candidate_actions,
            selected_action=selected_action,
            gate_decision=gate_decision,
            runtime_decision=runtime_decision,
            veto=gate_decision == "veto" or runtime_decision == "HARD_BLOCK",
            risk_level=risk_level,
            ambiguity=_clean_str(audit_payload.get("ambiguity"), "unknown"),
            evidence_tier=evidence_tier,
            identification_tier=identification_tier,
            confidence=confidence,
            reason_codes=_dedupe(reason_codes),
            reason=_clean_str(selected.get("reason") or "; ".join(result.get("notes", []) or [])),
            source="causalgate_agent_runtime",
            payload={
                "mode": "agent_runtime",
                "selected": selected,
                "agent_status": result.get("status"),
                "response_type": result.get("response_type"),
                "executed": bool(result.get("executed")),
                "blocked": bool(result.get("blocked")),
                "needs_user_confirmation": bool(result.get("needs_user_confirmation")),
                "tool_guard": tool_guard,
                "tool_result": result.get("tool_result"),
                "llm_response": llm_response,
                "recommendation": recommendation,
                "recommended_action": _as_dict(result.get("recommended_action")),
                "recommendation_summary": _clean_str(result.get("recommendation_summary")),
                "recommendation_requires_recheck": bool(result.get("recommendation_requires_recheck", True)),
                "evidence_bundle": evidence,
                "evidence_warnings": list(result.get("evidence_warnings") or []),
                "usable_for_autonomous_action": bool(result.get("usable_for_autonomous_action")),
                "notes": list(result.get("notes") or []),
            },
        )

    def append_agent_decision(self, agent_result: Mapping[str, Any]) -> Dict[str, Any]:
        return self.audit_log.append_event(self.build_decision_event(agent_result))

    def record_outcome(
        self,
        *,
        decision_event_id: str = "",
        request_id: str = "",
        selected_action: str = "",
        outcome: str = "unknown",
        success: bool | None = None,
        harm: bool | None = None,
        user_satisfaction: float | None = None,
        latency_ms: float | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        return self.outcome_tracker.record_outcome(
            decision_event_id=decision_event_id,
            request_id=request_id,
            selected_action=selected_action,
            outcome=outcome,
            success=success,
            harm=harm,
            user_satisfaction=user_satisfaction,
            latency_ms=latency_ms,
            metadata=metadata,
        )

    def export_datasets(self, out_dir: str | Path) -> Dict[str, Any]:
        return export_learning_datasets(self.path, out_dir)


def build_agent_decision_event(agent_result: Mapping[str, Any]) -> AuditEvent:
    return AgentFeedbackLoop().build_decision_event(agent_result)


def append_agent_decision(agent_result: Mapping[str, Any], path: str | Path = DEFAULT_AUDIT_LOG_PATH) -> Dict[str, Any]:
    return AgentFeedbackLoop(path).append_agent_decision(agent_result)


def record_agent_outcome(
    *,
    path: str | Path = DEFAULT_AUDIT_LOG_PATH,
    decision_event_id: str = "",
    request_id: str = "",
    selected_action: str = "",
    outcome: str = "unknown",
    success: bool | None = None,
    harm: bool | None = None,
    user_satisfaction: float | None = None,
    latency_ms: float | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    return AgentFeedbackLoop(path).record_outcome(
        decision_event_id=decision_event_id,
        request_id=request_id,
        selected_action=selected_action,
        outcome=outcome,
        success=success,
        harm=harm,
        user_satisfaction=user_satisfaction,
        latency_ms=latency_ms,
        metadata=metadata,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Agent feedback utilities for CausalGate Step 9.")
    sub = parser.add_subparsers(dest="command", required=True)

    add_decision = sub.add_parser("append-decision", help="Append an AgentRunResult JSON as a learning decision event.")
    add_decision.add_argument("--input", required=True)
    add_decision.add_argument("--log", default=DEFAULT_AUDIT_LOG_PATH)

    add_outcome = sub.add_parser("record-outcome", help="Record an observed outcome for an agent decision.")
    add_outcome.add_argument("--log", default=DEFAULT_AUDIT_LOG_PATH)
    add_outcome.add_argument("--decision-event-id", default="")
    add_outcome.add_argument("--request-id", default="")
    add_outcome.add_argument("--selected-action", default="")
    add_outcome.add_argument("--outcome", default="unknown")
    add_outcome.add_argument("--success", choices=["true", "false", ""], default="")
    add_outcome.add_argument("--harm", choices=["true", "false", ""], default="")
    add_outcome.add_argument("--user-satisfaction", type=float, default=None)
    add_outcome.add_argument("--latency-ms", type=float, default=None)

    export = sub.add_parser("export-datasets", help="Export learning/RCT/fine-tuning datasets from the feedback log.")
    export.add_argument("--log", default=DEFAULT_AUDIT_LOG_PATH)
    export.add_argument("--out-dir", default="out/learning/datasets")

    args = parser.parse_args(argv)
    if args.command == "append-decision":
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        print(json.dumps(append_agent_decision(payload, path=args.log), indent=2, ensure_ascii=False))
        return 0
    if args.command == "record-outcome":
        success = None if args.success == "" else args.success == "true"
        harm = None if args.harm == "" else args.harm == "true"
        event = record_agent_outcome(
            path=args.log,
            decision_event_id=args.decision_event_id,
            request_id=args.request_id,
            selected_action=args.selected_action,
            outcome=args.outcome,
            success=success,
            harm=harm,
            user_satisfaction=args.user_satisfaction,
            latency_ms=args.latency_ms,
        )
        print(json.dumps(event, indent=2, ensure_ascii=False))
        return 0
    if args.command == "export-datasets":
        print(json.dumps(AgentFeedbackLoop(args.log).export_datasets(args.out_dir), indent=2, ensure_ascii=False))
        return 0
    return 1


__all__ = [
    "AgentFeedbackSummary",
    "AgentFeedbackLoop",
    "build_agent_decision_event",
    "append_agent_decision",
    "record_agent_outcome",
]


if __name__ == "__main__":
    raise SystemExit(main())
