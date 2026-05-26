from __future__ import annotations

"""LLM dialogue orchestrator for CausalGate scientific hypotheses.

The orchestrator lets an external/local LLM adapter discuss hypotheses with
CausalGate without giving the LLM final authority.  The LLM may propose or revise a
ScientificHypothesisPackage.  CausalGate performs veto, deterministic repair,
expansion, claim-level control, and terminal routing.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional
from uuid import uuid4

from .hypothesis_expansion import expand_hypothesis
from .hypothesis_repair_agent import repair_hypothesis
from .hypothesis_veto import evaluate_hypothesis
from .research_cycle import run_research_cycle


LLMAdapter = Callable[[Mapping[str, Any]], Mapping[str, Any] | None]

DIALOGUE_TERMINAL_STATUSES = {
    "FINAL_CANDIDATE",
    "ARCHIVED_UNSUPPORTED",
    "AWAITING_LLM_PROPOSAL",
    "AWAITING_LLM_REVISION",
    "MAX_STEPS_REACHED",
    "LLM_ADAPTER_ERROR",
}


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


def _intish(value: Any, default: int = 0, minimum: int = 0, maximum: int = 100) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _default_dialogue_id() -> str:
    return "llm_dialogue_" + uuid4().hex[:12]


def _extract_hypothesis(payload: Mapping[str, Any]) -> Dict[str, Any]:
    data = _as_dict(payload)
    for key in ("hypothesis", "candidate", "candidate_hypothesis", "revised_hypothesis", "repaired_hypothesis"):
        if isinstance(data.get(key), Mapping):
            return dict(data[key])
    if isinstance(data.get("tool_result"), Mapping):
        return _extract_hypothesis(data["tool_result"])
    if isinstance(data.get("message"), Mapping):
        return _extract_hypothesis(data["message"])
    if data.get("claim"):
        reserved = {
            "goal", "dialogue_id", "step", "feedback", "max_steps", "max_iterations",
            "auto_expand", "agent_repair", "enable_identification", "write_ledger",
        }
        return {k: v for k, v in data.items() if k not in reserved}
    return {}


def _summarize_hypothesis(hypothesis: Mapping[str, Any]) -> Dict[str, Any]:
    data = _as_dict(hypothesis)
    return {
        "hypothesis_id": data.get("hypothesis_id", ""),
        "claim": data.get("claim", ""),
        "claim_level": data.get("claim_level", ""),
        "treatment": data.get("treatment", ""),
        "outcome": data.get("outcome", ""),
        "measurable_predictions": _as_list(data.get("measurable_predictions")),
        "falsification_tests_count": len(_as_list(data.get("falsification_tests"))),
        "data_requirements_count": len(_as_list(data.get("data_requirements"))),
    }


def _last_nonempty_verdict(turns: List[Dict[str, Any]]) -> Dict[str, Any]:
    for turn in reversed(turns):
        verdict = _as_dict(turn.get("verdict"))
        if verdict:
            return verdict
    return {}


def _append_unique(values: Any, additions: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in [*_as_list(values), *additions]:
        text = _clean_str(value)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _safe_claim_for_evidence_ceiling(hypothesis: Mapping[str, Any]) -> str:
    treatment = _clean_str(hypothesis.get("treatment"), "the treatment")
    outcome = _clean_str(hypothesis.get("outcome"), "the outcome")
    adjustment = _as_list(hypothesis.get("adjustment_set")) or _as_list(hypothesis.get("confounders"))
    adjustment_text = ", ".join(str(item) for item in adjustment if _clean_str(item))
    adjustment_clause = f" after considering pre-treatment covariates ({adjustment_text})" if adjustment_text else " under the stated assumptions"
    return (
        f"Candidate hypothesis only: {treatment} may be related to {outcome}{adjustment_clause}. "
        "This remains a bounded candidate for testing; SCM-ID and estimation outputs are audit signals, "
        "not confirmation of a real-world causal effect."
    )


def _apply_veto_revision_to_hypothesis(hypothesis: Mapping[str, Any], verdict: Mapping[str, Any]) -> Dict[str, Any]:
    reason_codes = set(str(value) for value in _as_list(verdict.get("reason_codes")))
    required_tests = set(str(value) for value in _as_list(verdict.get("required_tests")))
    overclaim = _clean_str(verdict.get("overclaim_risk")).lower() == "high"
    needs_claim_downgrade = (
        "CLAIM_LEVEL_DOWNGRADED_TO_EVIDENCE_CEILING" in reason_codes
        or "OVERCLAIM_RISK_HIGH" in reason_codes
        or "downgrade_claim_to_hypothesis_only_or_testable_candidate" in required_tests
        or overclaim
    )
    if not needs_claim_downgrade:
        return {}

    metadata = _as_dict(hypothesis.get("metadata"))
    applied = _as_list(metadata.get("agent_applied_veto_revisions"))
    if "claim_level_evidence_ceiling" in applied:
        return {}

    revised = dict(hypothesis)
    revised["claim_level"] = "hypothesis_only"
    revised["conclusion_strength"] = "hypothesis_only"
    revised["claim"] = _safe_claim_for_evidence_ceiling(revised)
    revised["source"] = _clean_str(revised.get("source"), "causalgate_dialogue_revision_applier")
    revised["falsification_tests"] = _append_unique(revised.get("falsification_tests"), ["Re-check the candidate after claim wording is downgraded to hypothesis-only.", "Verify that no public wording claims confirmed, proven, or validated causality."])
    revised["sensitivity_checks"] = _append_unique(revised.get("sensitivity_checks"), ["Review whether the supplied estimate survives independent replication before any stronger claim."])
    metadata["agent_applied_veto_revisions"] = _append_unique(applied, ["claim_level_evidence_ceiling"])
    metadata["last_veto_revision_reason_codes"] = sorted(reason_codes)
    metadata["last_veto_required_tests"] = sorted(required_tests)
    metadata["max_allowed_claim_level"] = _as_dict(verdict.get("max_allowed_claim_level"))
    metadata["requested_claim_level"] = _as_dict(verdict.get("requested_claim_level"))
    metadata["veto_next_instruction"] = _clean_str(verdict.get("next_instruction"))
    revised["metadata"] = metadata
    return revised


def _apply_estimation_evidence_to_hypothesis(hypothesis: Mapping[str, Any], verdict: Mapping[str, Any]) -> Dict[str, Any]:
    """Attach synthetic demo evidence when a native physics hypothesis has none.

    This is deliberately limited to mechanistic physics demo candidates.  It does
    not run for mathematical conjectures and it does not claim real-world
    evidence; it supplies a deterministic synthetic dataset diagnostic so the
    same hypothesis can flow through Estimation and diagnostics.
    """

    estimation = _as_dict(verdict.get("estimation"))
    reason_codes = set(str(value) for value in _as_list(estimation.get("reason_codes")))
    status = _clean_str(estimation.get("estimation_status"))
    if status != "not_run_no_estimation_evidence" and "ESTIMATION_NOT_RUN_NO_EVIDENCE" not in reason_codes:
        return {}
    if _clean_str(hypothesis.get("domain")) != "mechanistic_physics":
        return {}
    metadata = _as_dict(hypothesis.get("metadata"))
    applied = _as_list(metadata.get("agent_applied_estimation_revisions"))
    if "synthetic_demo_estimation_diagnostics" in applied or metadata.get("estimation_diagnostics"):
        return {}

    from causalgate.causal_core.estimation.diagnostics import diagnostics_to_metadata, run_synthetic_demo_diagnostics

    diagnostics = run_synthetic_demo_diagnostics({
        "treatment": hypothesis.get("treatment", "X"),
        "outcome": hypothesis.get("outcome", "Y"),
        "negative_control_outcome": "N",
        "placebo_treatment": "FutureX",
        "support_n": metadata.get("support_n", 240),
        "seed": metadata.get("synthetic_seed", 1805),
    })
    revised = dict(hypothesis)
    metadata.update(diagnostics_to_metadata(diagnostics))
    metadata["synthetic_demo_estimation"] = True
    metadata["synthetic_demo_estimation_reason"] = "native_physics_estimation_missing_evidence"
    metadata["estimation_diagnostics_computed"] = True
    metadata["estimation_diagnostics_source"] = "causalgate.causal_core.estimation.diagnostics"
    metadata["agent_applied_estimation_revisions"] = _append_unique(applied, ["synthetic_demo_estimation_diagnostics"])
    revised["metadata"] = metadata
    revised["data_requirements"] = _append_unique(revised.get("data_requirements"), ["Synthetic demo rows generated for public pipeline diagnostics; replace with real measurements before any stronger claim."])
    revised["test_plan"] = _clean_str(revised.get("test_plan"), "") + " Synthetic demo estimation diagnostics were added only for pipeline execution; real experimental/simulation data are still required for claim upgrade."
    return revised


def _adapter_context(*, dialogue_id: str, goal: str, step: int, feedback: str, previous_hypothesis: Mapping[str, Any] | None, previous_verdict: Mapping[str, Any] | None, expansion: Mapping[str, Any] | None) -> Dict[str, Any]:
    return {"dialogue_id": dialogue_id, "goal": goal, "step": step, "role": "llm_propose_or_revise_hypothesis", "feedback_from_causalgate": feedback, "previous_hypothesis": _as_dict(previous_hypothesis), "previous_verdict": _as_dict(previous_verdict), "hypothesis_expansion": _as_dict(expansion), "hard_rules": ["Return a structured hypothesis candidate, not a confirmed discovery.", "Do not claim proof, confirmed law, or validated causality.", "Include treatment, outcome, DAG, assumptions, falsification tests, and data requirements when possible.", "Patch missing fields only when revising; do not rewrite the whole hypothesis unless asked.", "CausalGate remains the authority for claim level and final candidate status."]}


@dataclass
class LLMDialogueTurn:
    step: int
    actor: str
    status: str
    hypothesis: Dict[str, Any] = field(default_factory=dict)
    verdict: Dict[str, Any] = field(default_factory=dict)
    expansion: Dict[str, Any] = field(default_factory=dict)
    llm_context: Dict[str, Any] = field(default_factory=dict)
    llm_response: Dict[str, Any] = field(default_factory=dict)
    next_instruction: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LLMDialogueResult:
    dialogue_id: str
    status: str
    goal: str
    final_decision: str
    should_continue: bool
    next_instruction: str
    steps_completed: int
    max_steps: int
    final_hypothesis: Dict[str, Any] = field(default_factory=dict)
    initial_verdict: Dict[str, Any] = field(default_factory=dict)
    final_verdict: Dict[str, Any] = field(default_factory=dict)
    turns: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LLMDialogueOrchestrator:
    def __init__(self, *, llm_adapter: Optional[LLMAdapter] = None, enable_identification: bool = True) -> None:
        self.llm_adapter = llm_adapter
        self.enable_identification = enable_identification

    def run(self, payload: Mapping[str, Any]) -> LLMDialogueResult:
        data = _as_dict(payload)
        dialogue_id = _clean_str(data.get("dialogue_id") or data.get("run_id"), _default_dialogue_id())
        goal = _clean_str(data.get("goal") or data.get("research_goal") or data.get("objective"), "Discuss and mature a scientific hypothesis.")
        max_steps = _intish(data.get("max_steps") or data.get("max_iterations"), default=5, minimum=1, maximum=25)
        auto_expand = _boolish(data.get("auto_expand"), default=True)
        agent_repair = _boolish(data.get("agent_repair"), default=True)
        enable_identification = _boolish(data.get("enable_identification"), default=self.enable_identification)
        write_ledger = _boolish(data.get("write_ledger"), default=False)
        llm_actor = _clean_str(data.get("llm_actor") or data.get("llm_provider") or data.get("provider"), "gemini" if self.llm_adapter is not None else "llm")

        queue: List[Dict[str, Any]] = []
        for item in _as_list(data.get("candidate_hypotheses") or data.get("hypotheses") or data.get("candidates")):
            if isinstance(item, Mapping):
                queue.append(dict(item))
        initial = _extract_hypothesis(data)
        current_hypothesis = initial or (queue.pop(0) if queue else {})

        turns: List[Dict[str, Any]] = []
        warnings: List[str] = []
        previous_verdict: Dict[str, Any] = {}
        first_verdict: Dict[str, Any] = {}
        previous_expansion: Dict[str, Any] = {}
        next_instruction = _clean_str(data.get("feedback") or data.get("feedback_in") or data.get("previous_feedback"))
        status = "RUNNING"
        final_decision = "ABSTAIN"
        should_continue = True
        repairs_applied = 0
        veto_revisions_applied = 0
        estimation_revisions_applied = 0

        for step in range(1, max_steps + 1):
            if not current_hypothesis:
                if self.llm_adapter is None:
                    status = "AWAITING_LLM_PROPOSAL"
                    next_instruction = next_instruction or "Ask the LLM/researcher to propose the first structured ScientificHypothesisPackage."
                    turns.append(LLMDialogueTurn(step=step, actor="causalgate", status=status, llm_context=_adapter_context(dialogue_id=dialogue_id, goal=goal, step=step, feedback=next_instruction, previous_hypothesis={}, previous_verdict=previous_verdict, expansion=previous_expansion), next_instruction=next_instruction).to_dict())
                    should_continue = True
                    break
                adapter_result = self._call_llm_adapter_payload(dialogue_id=dialogue_id, goal=goal, step=step, feedback=next_instruction, previous_hypothesis={}, previous_verdict=previous_verdict, expansion=previous_expansion, warnings=warnings)
                candidate = _as_dict(adapter_result.get("hypothesis"))
                if not candidate:
                    status = "LLM_ADAPTER_ERROR"
                    next_instruction = "LLM adapter did not return a structured hypothesis."
                    should_continue = False
                    break
                current_hypothesis = candidate
                turns.append(LLMDialogueTurn(step=step, actor=llm_actor, status="PROPOSED_HYPOTHESIS", hypothesis=dict(current_hypothesis), llm_context=_as_dict(adapter_result.get("context")), llm_response=_as_dict(adapter_result.get("raw_response")), next_instruction="CausalGate will evaluate this proposed hypothesis.").to_dict())

            verdict = evaluate_hypothesis(current_hypothesis, enable_identification=enable_identification)
            if not first_verdict:
                first_verdict = dict(verdict)
            decision = _clean_str(verdict.get("decision"), "ABSTAIN")
            final_decision = decision
            next_instruction = _clean_str(verdict.get("next_instruction"), next_instruction)
            turn = LLMDialogueTurn(step=step, actor="causalgate", status=decision, hypothesis=dict(current_hypothesis), verdict=verdict, next_instruction=next_instruction)

            estimation_evidence = _apply_estimation_evidence_to_hypothesis(current_hypothesis, verdict)
            if estimation_evidence:
                turns.append(turn.to_dict())
                estimation_revisions_applied += 1
                current_hypothesis = estimation_evidence
                turns.append(LLMDialogueTurn(step=step + 1, actor="causalgate_estimation_evidence_applier", status="APPLIED_SYNTHETIC_ESTIMATION_EVIDENCE", hypothesis=dict(current_hypothesis), expansion={"applied_revision": "synthetic_demo_estimation_diagnostics", "same_hypothesis": True, "source_estimation_status": _clean_str(_as_dict(verdict.get("estimation")).get("estimation_status"))}, next_instruction="CausalGate attached synthetic demo diagnostics to the same physics hypothesis and will re-evaluate it.").to_dict())
                continue

            if decision == "FINAL_CANDIDATE":
                status = "FINAL_CANDIDATE"
                should_continue = False
                turns.append(turn.to_dict())
                break
            if decision == "BLOCK":
                if auto_expand:
                    expansion = expand_hypothesis({"hypothesis": current_hypothesis, "verdict": verdict, "enable_identification": enable_identification}, enable_identification=enable_identification)
                    turn.expansion = expansion
                    previous_expansion = expansion
                    if expansion.get("state") == "ARCHIVED_UNSUPPORTED":
                        status = "ARCHIVED_UNSUPPORTED"
                        should_continue = False
                        turns.append(turn.to_dict())
                        break
                status = "ARCHIVED_UNSUPPORTED"
                should_continue = False
                turns.append(turn.to_dict())
                break

            expansion: Dict[str, Any] = {}
            if auto_expand:
                expansion = expand_hypothesis({"hypothesis": current_hypothesis, "verdict": verdict, "enable_identification": enable_identification}, enable_identification=enable_identification)
                turn.expansion = expansion
                previous_expansion = expansion
                if expansion.get("accepted"):
                    status = "FINAL_CANDIDATE"
                    final_decision = "FINAL_CANDIDATE"
                    should_continue = False
                    turns.append(turn.to_dict())
                    break

            turns.append(turn.to_dict())
            previous_verdict = verdict

            if queue:
                current_hypothesis = queue.pop(0)
                continue

            if decision == "REVISE":
                revised_by_veto = _apply_veto_revision_to_hypothesis(current_hypothesis, verdict)
                if revised_by_veto:
                    veto_revisions_applied += 1
                    current_hypothesis = revised_by_veto
                    turns.append(LLMDialogueTurn(step=step + 1, actor="causalgate_veto_revision_applier", status="APPLIED_VETO_RECOMMENDATION", hypothesis=dict(current_hypothesis), expansion={"applied_revision": "claim_level_evidence_ceiling", "same_hypothesis": True, "source_reason_codes": _as_list(verdict.get("reason_codes")), "source_required_tests": _as_list(verdict.get("required_tests"))}, next_instruction="CausalGate applied the veto recommendation to the same hypothesis and will re-evaluate it.").to_dict())
                    continue

            if agent_repair:
                repair = repair_hypothesis({"hypothesis": current_hypothesis, "verdict": verdict})
                repaired = _as_dict(repair.get("repaired_hypothesis"))
                if repaired and repair.get("missing_items_addressed"):
                    repairs_applied += 1
                    warnings.extend(_as_list(repair.get("warnings")))
                    current_hypothesis = repaired
                    turns.append(LLMDialogueTurn(step=step + 1, actor="causalgate_repair_agent", status="REPAIRED_HYPOTHESIS", hypothesis=dict(current_hypothesis), expansion={"repair": repair}, next_instruction="CausalGate will re-evaluate this repaired hypothesis.").to_dict())
                    continue

            if self.llm_adapter is not None:
                feedback = _clean_str(expansion.get("next_required_step"), next_instruction) if expansion else next_instruction
                adapter_result = self._call_llm_adapter_payload(dialogue_id=dialogue_id, goal=goal, step=step + 1, feedback=feedback, previous_hypothesis=current_hypothesis, previous_verdict=verdict, expansion=expansion, warnings=warnings)
                candidate = _as_dict(adapter_result.get("hypothesis"))
                if candidate:
                    current_hypothesis = candidate
                    turns.append(LLMDialogueTurn(step=step + 1, actor=llm_actor, status="REVISED_HYPOTHESIS", hypothesis=dict(current_hypothesis), llm_context=_as_dict(adapter_result.get("context")), llm_response=_as_dict(adapter_result.get("raw_response")), next_instruction="CausalGate will re-evaluate this revised hypothesis.").to_dict())
                    continue
                status = "LLM_ADAPTER_ERROR"
                next_instruction = "LLM adapter did not return a structured revision."
                should_continue = False
                break

            if auto_expand and isinstance(expansion.get("expanded_hypothesis"), Mapping) and expansion.get("should_continue"):
                current_hypothesis = dict(expansion["expanded_hypothesis"])
                continue

            status = "AWAITING_LLM_REVISION"
            should_continue = True
            break
        else:
            status = "MAX_STEPS_REACHED"
            should_continue = True

        final_hypothesis = dict(current_hypothesis) if current_hypothesis else {}
        final_verdict = _last_nonempty_verdict(turns)
        if final_verdict:
            final_decision = _clean_str(final_verdict.get("decision"), final_decision)
            if status == "RUNNING":
                status = final_decision
        metadata = {"auto_expand": auto_expand, "agent_repair": agent_repair, "repairs_applied": repairs_applied, "veto_revisions_applied": veto_revisions_applied, "estimation_revisions_applied": estimation_revisions_applied, "enable_identification": enable_identification, "write_ledger": write_ledger, "llm_adapter_present": self.llm_adapter is not None, "llm_actor": llm_actor, "trace_schema": "llm_turns_explicit_v4_estimation_evidence_applier", "orchestrator": "causalgate.scientific.llm_dialogue.LLMDialogueOrchestrator"}
        if write_ledger:
            cycle = run_research_cycle({"goal": goal, "run_id": dialogue_id, "hypothesis": final_hypothesis, "max_steps": 1, "auto_expand": auto_expand, "write_ledger": True, "enable_identification": enable_identification})
            metadata["ledger_cycle_summary"] = cycle.get("ledger_summary_event", {})

        return LLMDialogueResult(dialogue_id=dialogue_id, status=status, goal=goal, final_decision=final_decision, should_continue=should_continue, next_instruction=next_instruction, steps_completed=len(turns), max_steps=max_steps, final_hypothesis=final_hypothesis, initial_verdict=first_verdict, final_verdict=final_verdict, turns=turns, warnings=warnings, metadata=metadata)

    def _call_llm_adapter_payload(self, *, dialogue_id: str, goal: str, step: int, feedback: str, previous_hypothesis: Mapping[str, Any], previous_verdict: Mapping[str, Any], expansion: Mapping[str, Any], warnings: List[str]) -> Dict[str, Any]:
        assert self.llm_adapter is not None
        context = _adapter_context(dialogue_id=dialogue_id, goal=goal, step=step, feedback=feedback, previous_hypothesis=previous_hypothesis, previous_verdict=previous_verdict, expansion=expansion)
        try:
            raw = self.llm_adapter(context)
        except Exception as exc:
            warnings.append(f"llm_adapter_failed: {type(exc).__name__}: {exc}")
            return {"context": context, "raw_response": {}, "hypothesis": {}}
        if not isinstance(raw, Mapping):
            warnings.append("llm_adapter_returned_non_mapping")
            return {"context": context, "raw_response": {}, "hypothesis": {}}
        hypothesis = _extract_hypothesis(raw)
        if not hypothesis:
            warnings.append("llm_adapter_returned_no_hypothesis")
            return {"context": context, "raw_response": dict(raw), "hypothesis": {}}
        return {"context": context, "raw_response": dict(raw), "hypothesis": hypothesis, "hypothesis_summary": _summarize_hypothesis(hypothesis)}

    def _call_llm_adapter(self, *, dialogue_id: str, goal: str, step: int, feedback: str, previous_hypothesis: Mapping[str, Any], previous_verdict: Mapping[str, Any], expansion: Mapping[str, Any], warnings: List[str]) -> Dict[str, Any]:
        return _as_dict(self._call_llm_adapter_payload(dialogue_id=dialogue_id, goal=goal, step=step, feedback=feedback, previous_hypothesis=previous_hypothesis, previous_verdict=previous_verdict, expansion=expansion, warnings=warnings).get("hypothesis"))


def run_llm_dialogue(payload: Mapping[str, Any], *, llm_adapter: Optional[LLMAdapter] = None, enable_identification: bool = True) -> Dict[str, Any]:
    return LLMDialogueOrchestrator(llm_adapter=llm_adapter, enable_identification=enable_identification).run(payload).to_dict()


__all__ = ["DIALOGUE_TERMINAL_STATUSES", "LLMAdapter", "LLMDialogueOrchestrator", "LLMDialogueResult", "LLMDialogueTurn", "run_llm_dialogue"]
