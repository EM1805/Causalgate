from __future__ import annotations

"""Native scientific-agent state for CausalGate.

This module is intentionally stdlib-only.  It gives CausalGate a first-class agent
runtime state without requiring LangGraph or any other orchestration framework.
The state is a contract for bounded scientific loops: external LLMs/researchers
may propose or revise hypotheses, while CausalGate owns the conservative veto,
claim-level audit, and routing decision.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional
from uuid import uuid4


_NATIVE_DECISIONS = {"FINAL_CANDIDATE", "REVISE", "TEST_MORE", "BLOCK", "ABSTAIN"}


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


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


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    parsed = _as_int(value, default)
    return max(minimum, min(maximum, parsed))


def _dedupe(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in values:
        text = _clean_str(item)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def default_native_run_id() -> str:
    return "native_scientific_" + uuid4().hex[:12]


def native_agent_safety_boundary() -> Dict[str, Any]:
    """Return the hard safety boundary used by the native agent runtime."""

    return {
        "agent_role": "Orchestrates bounded hypothesis review, revision routing, and evidence requests.",
        "llm_role": "May propose or revise hypothesis packages; may not self-certify evidence or final claim levels.",
        "causalgate_role": "Must run hypothesis veto, falsification policy, SCM/ID checks when available, and claim-level audit before any final output.",
        "hard_rule": "No final scientific answer may bypass CausalGate's veto and claim-level audit.",
        "no_autonomous_discovery_claim": "Without external validation, the agent may output candidate hypotheses only, not confirmed discoveries or laws.",
        "no_empty_autonomy": "If no hypothesis or generator is supplied, the agent must ask for a structured ScientificHypothesisPackage instead of inventing one.",
    }


@dataclass
class NativeScientificAgentState:
    """Mutable state snapshot for CausalGate's native scientific agent."""

    goal: str = "Review a scientific hypothesis candidate."
    run_id: str = field(default_factory=default_native_run_id)
    status: str = "initialized"
    phase: str = "prepare"
    route: str = "need_initial_hypothesis"

    iteration: int = 0
    max_iterations: int = 3
    revision_count: int = 0

    hypothesis: Dict[str, Any] = field(default_factory=dict)
    candidate_hypotheses: List[Dict[str, Any]] = field(default_factory=list)
    feedback: str = ""

    verdict: Dict[str, Any] = field(default_factory=dict)
    step_results: List[Dict[str, Any]] = field(default_factory=list)
    completed_tests: List[Dict[str, Any]] = field(default_factory=list)

    final_decision: str = "ABSTAIN"
    veto_status: str = "not_run"
    evidence_status: str = "unknown"
    falsifiability_status: str = "unknown"
    claim_level: Dict[str, Any] = field(default_factory=dict)
    max_allowed_claim_level: Dict[str, Any] = field(default_factory=dict)
    missing_evidence: List[str] = field(default_factory=list)
    required_tests: List[str] = field(default_factory=list)

    should_continue: bool = True
    required_next_actor: str = "llm_or_researcher"
    next_instruction: str = ""
    final_report: Dict[str, Any] = field(default_factory=dict)

    ledger_path: str = "out/scientific/ledger.jsonl"
    write_ledger: bool = False
    enable_identification: bool = True

    agent_backend: str = "causalgate_native"
    trace: List[str] = field(default_factory=lambda: ["prepare_state"])
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Optional[Mapping[str, Any]]) -> "NativeScientificAgentState":
        data = _as_dict(payload)
        candidates: List[Dict[str, Any]] = []
        raw_candidates = data.get("candidate_hypotheses") or data.get("hypotheses") or data.get("candidates")
        for item in _as_list(raw_candidates):
            if isinstance(item, Mapping):
                candidates.append(dict(item))

        hypothesis: Dict[str, Any] = {}
        if isinstance(data.get("hypothesis"), Mapping):
            hypothesis = dict(data.get("hypothesis") or {})
        elif isinstance(data.get("claim"), str):
            # Convenience wrapper for tool callers that submit a flat hypothesis.
            hypothesis = {k: v for k, v in data.items() if k not in {"candidate_hypotheses", "hypotheses", "candidates"}}

        return cls(
            goal=_clean_str(data.get("goal") or data.get("research_goal") or data.get("objective"), "Review a scientific hypothesis candidate."),
            run_id=_clean_str(data.get("run_id"), default_native_run_id()),
            max_iterations=_clamp_int(data.get("max_iterations") or data.get("max_steps"), default=3, minimum=1, maximum=25),
            hypothesis=hypothesis,
            candidate_hypotheses=candidates,
            feedback=_clean_str(data.get("feedback") or data.get("feedback_in") or data.get("previous_feedback")),
            ledger_path=_clean_str(data.get("ledger_path"), "out/scientific/ledger.jsonl"),
            write_ledger=_as_bool(data.get("write_ledger"), False),
            enable_identification=_as_bool(data.get("enable_identification"), True),
            metadata=_as_dict(data.get("metadata")),
        )

    def append_trace(self, event: str) -> None:
        event = _clean_str(event)
        if event:
            self.trace.append(event)

    def update_from_step_result(self, step_result: Mapping[str, Any]) -> None:
        result = _as_dict(step_result)
        self.step_results.append(result)
        self.status = _clean_str(result.get("status"), self.status)
        self.phase = "causalgate_veto"
        self.hypothesis = _as_dict(result.get("hypothesis")) or self.hypothesis
        self.verdict = _as_dict(result.get("verdict"))
        self.final_decision = _clean_str(self.verdict.get("decision"), "ABSTAIN")
        if self.final_decision not in _NATIVE_DECISIONS:
            self.final_decision = "ABSTAIN"
        self.veto_status = self.final_decision
        self.evidence_status = _clean_str(self.verdict.get("evidence_status"), "unknown")
        self.falsifiability_status = _clean_str(self.verdict.get("falsifiability_status"), "unknown")
        self.claim_level = _as_dict(self.verdict.get("scientific_claim_level"))
        self.max_allowed_claim_level = _as_dict(self.verdict.get("max_allowed_claim_level"))
        self.missing_evidence = _dedupe(self.verdict.get("missing_items") or [])
        self.required_tests = _dedupe(self.verdict.get("required_tests") or [])
        self.next_instruction = _clean_str(result.get("next_instruction") or self.verdict.get("next_instruction"))
        self.should_continue = bool(result.get("should_continue", self.final_decision not in {"FINAL_CANDIDATE", "BLOCK"}))
        self.append_trace("causalgate_veto_completed")

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["safety_boundary"] = native_agent_safety_boundary()
        return data


__all__ = [
    "NativeScientificAgentState",
    "default_native_run_id",
    "native_agent_safety_boundary",
]
