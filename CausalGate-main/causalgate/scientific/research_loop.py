from __future__ import annotations

"""Scientific research loop primitives for CausalGate.

Step 3 does not try to make CausalGate a full autonomous scientist.  It adds the
safe orchestration boundary needed by an external LLM: normalize a candidate
hypothesis, run CausalGate's hypothesis veto, produce the next instruction, and
optionally write the whole event to a ledger.

The LLM remains the generator.  CausalGate remains the conservative reviewer.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Mapping, Optional
from uuid import uuid4

from .hypothesis_contract import ScientificHypothesisPackage, normalize_scientific_hypothesis
from .hypothesis_veto import evaluate_hypothesis
from .scientific_ledger import ScientificLedger


_TERMINAL_DECISIONS = {"FINAL_CANDIDATE", "BLOCK"}


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _default_run_id() -> str:
    return "scientific_run_" + uuid4().hex[:12]


def _default_hypothesis_id(run_id: str, step: int) -> str:
    clean = run_id.replace(" ", "_") or "run"
    return f"{clean}_hyp_{step:03d}"


def _skeleton_hypothesis(goal: str, run_id: str, step: int, feedback: str = "") -> Dict[str, Any]:
    """Create a conservative placeholder when no LLM hypothesis is provided.

    This lets MCP clients ask CausalGate what structure is required before a model
    has generated a full candidate.
    """

    return {
        "run_id": run_id,
        "step": step,
        "hypothesis_id": _default_hypothesis_id(run_id, step),
        "claim": goal,
        "claim_level": "hypothesis_only",
        "conclusion_strength": "hypothesis_only",
        "source": "research_loop_skeleton",
        "metadata": {
            "goal": goal,
            "feedback_in": feedback,
            "note": "Skeleton only: an LLM/researcher must fill variables, DAG, assumptions, tests, and data requirements.",
        },
    }


@dataclass
class ResearchStepResult:
    """Result of one CausalGate-reviewed scientific research step."""

    run_id: str
    step: int
    status: str
    hypothesis: Dict[str, Any]
    verdict: Dict[str, Any]
    should_continue: bool
    next_instruction: str
    ledger_event: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ScientificResearchLoop:
    """Single-step loop runner used by MCP/API/agent integrations."""

    def __init__(self, ledger_path: str = "out/scientific/ledger.jsonl", enable_identification: bool = True) -> None:
        self.ledger_path = ledger_path
        self.enable_identification = enable_identification

    def run_step(self, payload: Mapping[str, Any]) -> ResearchStepResult:
        data = _as_dict(payload)
        run_id = _clean_str(data.get("run_id"), _default_run_id())
        step = _as_int(data.get("step"), 1)
        feedback = _clean_str(data.get("feedback") or data.get("feedback_in") or data.get("previous_feedback"))
        goal = _clean_str(data.get("goal") or data.get("research_goal") or data.get("objective"))

        hypothesis_payload = data.get("hypothesis")
        if not isinstance(hypothesis_payload, Mapping):
            hypothesis_payload = _skeleton_hypothesis(goal or "Generate a precise scientific hypothesis candidate.", run_id, step, feedback)

        merged = dict(hypothesis_payload)
        merged.setdefault("run_id", run_id)
        merged.setdefault("step", step)
        merged.setdefault("hypothesis_id", _default_hypothesis_id(run_id, step))
        if goal:
            merged.setdefault("metadata", {})
            if isinstance(merged["metadata"], Mapping):
                merged["metadata"] = {**dict(merged["metadata"]), "goal": goal}
        if feedback:
            merged.setdefault("metadata", {})
            if isinstance(merged["metadata"], Mapping):
                merged["metadata"] = {**dict(merged["metadata"]), "feedback_in": feedback}

        hypothesis = normalize_scientific_hypothesis(merged)
        verdict = evaluate_hypothesis(hypothesis.to_dict(), enable_identification=self.enable_identification)
        decision = _clean_str(verdict.get("decision"), "ABSTAIN")
        next_instruction = _clean_str(verdict.get("next_instruction"))
        should_continue = decision not in _TERMINAL_DECISIONS

        if decision == "FINAL_CANDIDATE":
            status = "final_candidate_ready_for_external_validation"
        elif decision == "BLOCK":
            status = "blocked"
        elif decision == "TEST_MORE":
            status = "needs_more_tests"
        elif decision == "REVISE":
            status = "needs_revision"
        else:
            status = "abstain"

        ledger_event: Dict[str, Any] = {}
        if bool(data.get("write_ledger", True)):
            ledger_event = ScientificLedger(data.get("ledger_path") or self.ledger_path).append({
                "run_id": run_id,
                "step": step,
                "event_type": "research_step",
                "hypothesis_id": hypothesis.hypothesis_id,
                "hypothesis": hypothesis.to_dict(),
                "verdict": verdict,
                "feedback_in": feedback,
                "next_instruction": next_instruction,
                "status": status,
                "metadata": {
                    "goal": goal,
                    "should_continue": should_continue,
                    "terminal_decisions": sorted(_TERMINAL_DECISIONS),
                },
            })

        return ResearchStepResult(
            run_id=run_id,
            step=step,
            status=status,
            hypothesis=hypothesis.to_dict(),
            verdict=verdict,
            should_continue=should_continue,
            next_instruction=next_instruction,
            ledger_event=ledger_event,
        )


def run_research_step(payload: Mapping[str, Any], *, ledger_path: str = "out/scientific/ledger.jsonl", enable_identification: bool = True) -> Dict[str, Any]:
    """Functional helper for MCP/API clients."""

    data = _as_dict(payload)
    path = _clean_str(data.get("ledger_path"), ledger_path)
    enabled = bool(data.get("enable_identification")) if "enable_identification" in data else enable_identification
    return ScientificResearchLoop(ledger_path=path, enable_identification=enabled).run_step(payload).to_dict()


__all__ = [
    "ScientificResearchLoop",
    "ResearchStepResult",
    "run_research_step",
]
