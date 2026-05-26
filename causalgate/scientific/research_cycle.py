from __future__ import annotations

"""Bounded scientific research-cycle controller for CausalGate.

The cycle reviews LLM/researcher hypotheses through CausalGate's veto.  When
``auto_expand`` is enabled, REVISE/TEST_MORE/ABSTAIN results are fed into the
HypothesisExpansionEngine so a weak hypothesis matures into a stronger draft
instead of being discarded.  Expansion remains conservative: it structures and
asks for missing tests; it does not invent evidence or force acceptance.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional
from uuid import uuid4

from .hypothesis_expansion import expand_hypothesis
from .research_loop import ResearchStepResult, ScientificResearchLoop
from .scientific_ledger import ScientificLedger

_TERMINAL_DECISIONS = {"FINAL_CANDIDATE", "BLOCK"}
_CONTINUATION_DECISIONS = {"REVISE", "TEST_MORE", "ABSTAIN"}


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


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _clamp_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    parsed = _as_int(value, default)
    return max(min_value, min(parsed, max_value))


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


def _default_run_id() -> str:
    return "scientific_cycle_" + uuid4().hex[:12]


@dataclass
class ResearchCycleResult:
    run_id: str
    status: str
    goal: str
    steps_completed: int
    max_steps: int
    final_decision: str
    should_continue: bool
    next_instruction: str
    auto_expand: bool = False
    expansion_count: int = 0
    step_results: List[Dict[str, Any]] = field(default_factory=list)
    ledger_summary_event: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ScientificResearchCycle:
    def __init__(self, ledger_path: str = "out/scientific/ledger.jsonl", enable_identification: bool = True) -> None:
        self.ledger_path = ledger_path
        self.enable_identification = enable_identification
        self.step_runner = ScientificResearchLoop(ledger_path=ledger_path, enable_identification=enable_identification)

    def run_cycle(self, payload: Mapping[str, Any]) -> ResearchCycleResult:
        data = _as_dict(payload)
        run_id = _clean_str(data.get("run_id"), _default_run_id())
        goal = _clean_str(data.get("goal") or data.get("research_goal") or data.get("objective"))
        max_steps = _clamp_int(data.get("max_steps"), default=5, min_value=1, max_value=25)
        write_ledger = bool(data.get("write_ledger", True))
        ledger_path = _clean_str(data.get("ledger_path"), self.ledger_path)
        auto_expand = _boolish(data.get("auto_expand"), default=False)

        candidates = _as_list(data.get("candidate_hypotheses") or data.get("hypotheses") or data.get("candidates"))
        if not candidates and isinstance(data.get("hypothesis"), Mapping):
            candidates = [data.get("hypothesis")]

        feedback = _clean_str(data.get("feedback") or data.get("feedback_in") or data.get("previous_feedback"))
        step_results: List[Dict[str, Any]] = []
        final_decision = ""
        next_instruction = feedback
        status = "not_started"
        should_continue = True
        expansion_count = 0
        expanded_candidate: Optional[Dict[str, Any]] = None

        for offset in range(max_steps):
            step_number = _as_int(data.get("start_step"), 1) + offset
            candidate: Optional[Any]
            if expanded_candidate is not None:
                candidate = expanded_candidate
                expanded_candidate = None
            else:
                candidate = candidates[offset] if offset < len(candidates) else None

            if candidate is None and step_results:
                status = "awaiting_llm_revision"
                should_continue = True
                break

            step_payload: Dict[str, Any] = {
                "run_id": run_id,
                "step": step_number,
                "goal": goal,
                "feedback": next_instruction,
                "write_ledger": write_ledger,
                "ledger_path": ledger_path,
                "enable_identification": self.enable_identification,
            }
            if isinstance(candidate, Mapping):
                step_payload["hypothesis"] = dict(candidate)

            result: ResearchStepResult = self.step_runner.run_step(step_payload)
            result_dict = result.to_dict()
            step_results.append(result_dict)

            verdict = _as_dict(result_dict.get("verdict"))
            hypothesis = _as_dict(result_dict.get("hypothesis"))
            decision = _clean_str(verdict.get("decision"), "ABSTAIN")
            final_decision = decision
            next_instruction = _clean_str(result_dict.get("next_instruction") or verdict.get("next_instruction"))

            if decision in _TERMINAL_DECISIONS:
                status = "final_candidate_ready_for_external_validation" if decision == "FINAL_CANDIDATE" else "blocked"
                should_continue = False
                break

            if decision in _CONTINUATION_DECISIONS:
                has_external_next = offset + 1 < len(candidates)
                if auto_expand and hypothesis:
                    expansion = expand_hypothesis(
                        {"hypothesis": hypothesis, "verdict": verdict, "enable_identification": self.enable_identification},
                        enable_identification=self.enable_identification,
                    )
                    result_dict["expansion"] = expansion
                    step_results[-1] = result_dict
                    expansion_count += 1
                    next_instruction = _clean_str(expansion.get("next_required_step"), next_instruction)
                    if expansion.get("accepted"):
                        status = "final_candidate_ready_for_external_validation"
                        final_decision = "FINAL_CANDIDATE"
                        should_continue = False
                        break
                    if expansion.get("should_continue") and isinstance(expansion.get("expanded_hypothesis"), Mapping):
                        expanded_candidate = dict(expansion["expanded_hypothesis"])
                        status = "auto_expanding_hypothesis"
                        should_continue = True
                        continue
                    status = "archived_unsupported" if expansion.get("state") == "ARCHIVED_UNSUPPORTED" else "awaiting_llm_revision"
                    should_continue = expansion.get("state") != "ARCHIVED_UNSUPPORTED"
                    break
                if not has_external_next:
                    status = "awaiting_llm_revision"
                    should_continue = True
                    break
        else:
            status = "max_steps_reached"
            should_continue = final_decision not in _TERMINAL_DECISIONS

        if not step_results:
            status = "awaiting_initial_hypothesis"
            final_decision = "ABSTAIN"
            should_continue = True
            next_instruction = "Provide the first ScientificHypothesisPackage with claim, treatment, outcome, DAG, assumptions, falsification tests, and data requirements."

        summary_event: Dict[str, Any] = {}
        if write_ledger:
            last_result = _as_dict(step_results[-1]) if step_results else {}
            last_hypothesis = _as_dict(last_result.get("hypothesis"))
            summary_event = ScientificLedger(ledger_path).append({
                "run_id": run_id,
                "step": len(step_results),
                "event_type": "research_cycle_summary",
                "hypothesis_id": _clean_str(last_hypothesis.get("hypothesis_id")),
                "hypothesis": last_hypothesis,
                "verdict": {"decision": final_decision, "status": status, "next_instruction": next_instruction},
                "next_instruction": next_instruction,
                "status": status,
                "metadata": {
                    "goal": goal,
                    "steps_completed": len(step_results),
                    "max_steps": max_steps,
                    "should_continue": should_continue,
                    "auto_expand": auto_expand,
                    "expansion_count": expansion_count,
                    "cycle_controller": "causalgate.scientific.research_cycle.ScientificResearchCycle",
                },
            })

        return ResearchCycleResult(
            run_id=run_id,
            status=status,
            goal=goal,
            steps_completed=len(step_results),
            max_steps=max_steps,
            final_decision=final_decision,
            should_continue=should_continue,
            next_instruction=next_instruction,
            auto_expand=auto_expand,
            expansion_count=expansion_count,
            step_results=step_results,
            ledger_summary_event=summary_event,
        )


def run_research_cycle(payload: Mapping[str, Any], *, ledger_path: str = "out/scientific/ledger.jsonl", enable_identification: bool = True) -> Dict[str, Any]:
    data = _as_dict(payload)
    path = _clean_str(data.get("ledger_path"), ledger_path)
    enabled = bool(data.get("enable_identification")) if "enable_identification" in data else enable_identification
    return ScientificResearchCycle(ledger_path=path, enable_identification=enabled).run_cycle(data).to_dict()


__all__ = ["ScientificResearchCycle", "ResearchCycleResult", "run_research_cycle"]
