from __future__ import annotations

"""Conservative tool planner for CausalGate scientific workflows.

The planner is intentionally rule-based and auditable.  It chooses which
CausalGate MCP tool should be called next, but it does not execute tools itself and
it does not upgrade claim strength.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping


@dataclass
class PlannedToolCall:
    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    required_next_actor: str = "causalgate_mcp"
    safety_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScientificToolPlan:
    goal: str
    mode: str
    planned_calls: List[PlannedToolCall] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    guardrails: List[str] = field(default_factory=lambda: [
        "Planner selects tools only; CausalGate veto remains final authority.",
        "External literature search can provide references, not proof or validated causality.",
        "Do not promote beyond testable_candidate without external validation evidence.",
    ])

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["planned_calls"] = [call.to_dict() for call in self.planned_calls]
        return data


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


def _boolish(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _infer_goal(payload: Mapping[str, Any]) -> str:
    return _clean_str(payload.get("goal") or payload.get("research_goal") or payload.get("objective"), "Generate and review a scientific hypothesis.")


def _has_hypothesis(payload: Mapping[str, Any]) -> bool:
    if isinstance(payload.get("hypothesis"), Mapping):
        return True
    return bool(_clean_str(payload.get("claim")))


def _hypothesis_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    if isinstance(payload.get("hypothesis"), Mapping):
        return dict(payload["hypothesis"])
    if _clean_str(payload.get("claim")):
        reserved = {"goal", "research_goal", "objective", "mode", "max_steps", "max_iterations", "include_external_evidence", "provider"}
        return {k: v for k, v in payload.items() if k not in reserved}
    return {}


def plan_scientific_tools(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Return an auditable MCP-tool plan for a scientific workflow.

    Modes:
    - auto: choose a default safe sequence.
    - generate_review: native generation followed by review loop.
    - literature_first: search external metadata before hypothesis review.
    - review_only: veto an already supplied hypothesis.
    - gemini_language_only: CausalGate generates/reviews; Gemini only renders language.
    """

    data = _as_dict(payload)
    goal = _infer_goal(data)
    requested_mode = _clean_str(data.get("mode"), "auto")
    include_external = _boolish(data.get("include_external_evidence"), default=requested_mode in {"auto", "literature_first"})
    max_steps = int(data.get("max_steps") or data.get("max_iterations") or 6)
    max_steps = max(1, min(25, max_steps))
    hypothesis = _hypothesis_payload(data)
    has_hypothesis = bool(hypothesis)

    if requested_mode == "auto":
        mode = "review_only" if has_hypothesis else "generate_review"
    else:
        mode = requested_mode

    plan = ScientificToolPlan(goal=goal, mode=mode)

    if include_external:
        plan.planned_calls.append(PlannedToolCall(
            tool_name="causalgate_search_scientific_literature",
            arguments={
                "query": goal,
                "sources": _as_list(data.get("sources")) or ["crossref", "openalex", "pubmed"],
                "limit": int(data.get("literature_limit") or 5),
            },
            reason="Collect public scientific metadata/references before evaluating evidence quality.",
            required_next_actor="external_literature_api",
            safety_notes=["Search results are not proof; they are evidence candidates for review."],
        ))

    if mode == "review_only":
        if not has_hypothesis:
            plan.warnings.append("review_only requested but no hypothesis was supplied; planner falls back to native generation.")
            mode = "generate_review"
            plan.mode = mode
        else:
            plan.planned_calls.append(PlannedToolCall(
                tool_name="causalgate_veto_hypothesis",
                arguments={"hypothesis": hypothesis, "enable_identification": _boolish(data.get("enable_identification"), True)},
                reason="Conservatively review the supplied hypothesis and clamp overclaims.",
            ))
            return plan.to_dict()

    if mode == "gemini_language_only":
        plan.planned_calls.append(PlannedToolCall(
            tool_name="causalgate_run_gemini_llm_dialogue",
            arguments={
                "goal": goal,
                "max_steps": max_steps,
                "max_iterations": max_steps,
                "auto_expand": True,
                "agent_repair": True,
                "enable_identification": _boolish(data.get("enable_identification"), True),
                "native_hypothesis_agent": True,
                "gemini_language_only": True,
            },
            reason="Use CausalGate for hypothesis generation/review and Gemini only for safe language rendering.",
            safety_notes=["Gemini must not propose, revise, or upgrade scientific claims in this mode."],
        ))
        return plan.to_dict()

    if mode in {"generate_review", "literature_first"}:
        plan.planned_calls.append(PlannedToolCall(
            tool_name="causalgate_run_native_scientific_agent",
            arguments={
                "goal": goal,
                "max_iterations": max_steps,
                "auto_expand": True,
                "agent_repair": True,
                "enable_identification": _boolish(data.get("enable_identification"), True),
                "native_hypothesis_agent": True,
                "write_ledger": _boolish(data.get("write_ledger"), False),
            },
            reason="Let CausalGate generate a structured candidate and immediately run veto/audit routing.",
        ))
        plan.planned_calls.append(PlannedToolCall(
            tool_name="causalgate_infer_evidence_requirements",
            arguments={"hypothesis": {"claim": goal}},
            reason="Return the minimum evidence checklist before stronger claim levels are allowed.",
        ))
        return plan.to_dict()

    plan.warnings.append(f"Unknown planner mode '{requested_mode}'; returning health check plan only.")
    plan.planned_calls.append(PlannedToolCall(
        tool_name="causalgate_health",
        arguments={},
        reason="Fallback tool to inspect available CausalGate MCP tools.",
    ))
    return plan.to_dict()


__all__ = ["PlannedToolCall", "ScientificToolPlan", "plan_scientific_tools"]
