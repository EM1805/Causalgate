from __future__ import annotations

"""CausalGate native scientific-agent runtime.

The native runtime owns the conservative safety loop.  By default it does not
invent hypotheses.  When ``native_hypothesis_agent`` is true, it may generate a
first structured *candidate* using CausalGate's deterministic discovery agent.  That
candidate still goes through the normal veto/claim-level audit before any final
status is returned.  When ``auto_expand_hypothesis`` is true, it may structure an
already-submitted weak hypothesis through HypothesisExpansionEngine and re-check
that expanded draft.  This is maturation, not evidence invention.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional

from .agent_router import NativeAgentRoute, route_next_step
from .agent_state import NativeScientificAgentState, native_agent_safety_boundary
from .hypothesis_discovery_agent import generate_hypothesis
from .hypothesis_expansion import expand_hypothesis
from .research_loop import ResearchStepResult, ScientificResearchLoop


HypothesisGenerator = Callable[[Mapping[str, Any]], Mapping[str, Any] | None]
TestExecutor = Callable[[Mapping[str, Any]], Mapping[str, Any] | None]

_ESTIMATION_PAYLOAD_KEYS = {
    "data",
    "dataset",
    "data_path",
    "effect_estimate",
    "ci_low",
    "ci_high",
    "standard_error",
    "p_value",
    "n",
    "sample_size",
    "estimator",
    "estimand",
    "estimation_method",
    "estimation_plan",
}


@dataclass
class NativeScientificAgentResult:
    run_id: str
    goal: str
    status: str
    final_decision: str
    route: str
    required_next_actor: str
    should_continue: bool
    next_instruction: str
    iterations_completed: int
    agent_backend: str = "causalgate_native"
    state: Dict[str, Any] = field(default_factory=dict)
    route_payload: Dict[str, Any] = field(default_factory=dict)
    final_report: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    trace: List[str] = field(default_factory=list)
    safety_boundary: Dict[str, Any] = field(default_factory=native_agent_safety_boundary)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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


def _merge_estimation_payload_into_hypothesis(hypothesis: Mapping[str, Any], payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Copy top-level agent estimation fields into hypothesis.metadata.

    The research loop passes only the normalized hypothesis to the veto. Keeping
    estimation payload fields inside hypothesis.metadata makes those values
    visible to SCM-ID/estimation without changing the public agent payload shape.
    Existing hypothesis metadata wins, so explicit nested values are never
    overwritten by convenience top-level fields.
    """

    merged = dict(hypothesis)
    metadata = _as_dict(merged.get("metadata"))
    copied = False
    for key in sorted(_ESTIMATION_PAYLOAD_KEYS):
        if key in payload and key not in merged and key not in metadata:
            metadata[key] = payload[key]
            copied = True
    if copied or metadata:
        merged["metadata"] = metadata
    return merged


def _next_candidate_from_queue(state: NativeScientificAgentState, cursor: int) -> tuple[Dict[str, Any], int]:
    if cursor < len(state.candidate_hypotheses):
        return dict(state.candidate_hypotheses[cursor]), cursor + 1
    return {}, cursor


def _build_final_report(state: NativeScientificAgentState, route: NativeAgentRoute) -> Dict[str, Any]:
    verdict = _as_dict(state.verdict)
    short = _as_dict(verdict.get("short_for_llm"))
    max_level = _as_dict(verdict.get("max_allowed_claim_level")) or _as_dict(state.max_allowed_claim_level)
    final_level = _as_dict(verdict.get("scientific_claim_level")) or _as_dict(state.claim_level)
    return {
        "public_claim_boundary": {
            "final_decision": state.final_decision,
            "allowed_wording_level": final_level,
            "max_allowed_claim_level": max_level,
            "do_not_say": [
                "confirmed law",
                "proven causality",
                "autonomous scientific discovery",
                "experimentally validated unless Level 6 evidence exists",
            ],
        },
        "summary_for_llm": short,
        "next_actor": route.required_next_actor,
        "next_instruction": route.instruction,
        "reason": route.reason,
    }


class NativeScientificAgent:
    def __init__(
        self,
        *,
        hypothesis_generator: Optional[HypothesisGenerator] = None,
        test_executor: Optional[TestExecutor] = None,
        ledger_path: str = "out/scientific/ledger.jsonl",
        enable_identification: bool = True,
    ) -> None:
        self.hypothesis_generator = hypothesis_generator
        self.test_executor = test_executor
        self.ledger_path = ledger_path
        self.enable_identification = enable_identification

    def run(self, payload: Mapping[str, Any]) -> NativeScientificAgentResult:
        raw_payload = _as_dict(payload)
        auto_expand = _boolish(raw_payload.get("auto_expand_hypothesis") or raw_payload.get("auto_expand"), default=False)
        native_hypothesis_agent = _boolish(raw_payload.get("native_hypothesis_agent") or raw_payload.get("native_discovery") or raw_payload.get("generate_hypothesis"), default=False)
        state = NativeScientificAgentState.from_payload(raw_payload)
        if not state.ledger_path:
            state.ledger_path = self.ledger_path
        state.enable_identification = bool(state.enable_identification if state.enable_identification is not None else self.enable_identification)
        state.metadata["auto_expand_hypothesis"] = auto_expand
        state.metadata["native_hypothesis_agent"] = native_hypothesis_agent

        candidate_cursor = 0
        current_hypothesis = dict(state.hypothesis) if state.hypothesis else {}
        if not current_hypothesis:
            current_hypothesis, candidate_cursor = _next_candidate_from_queue(state, candidate_cursor)
        if not current_hypothesis and self.hypothesis_generator is not None:
            current_hypothesis = self._call_hypothesis_generator(state)
        if not current_hypothesis and native_hypothesis_agent:
            current_hypothesis = self._call_native_hypothesis_agent(raw_payload, state)
        if current_hypothesis:
            current_hypothesis = _merge_estimation_payload_into_hypothesis(current_hypothesis, raw_payload)

        if not current_hypothesis:
            state.status = "awaiting_initial_hypothesis"
            state.phase = "awaiting_input"
            state.final_decision = "ABSTAIN"
            state.veto_status = "not_run"
            route = route_next_step(state)
            self._apply_route(state, route)
            state.warnings.append("No hypothesis was supplied; native agent refused to invent one autonomously. Set native_hypothesis_agent=true to use CausalGate's deterministic candidate generator.")
            state.append_trace("await_initial_hypothesis")
            return self._result_from_state(state, route)

        route = route_next_step({"hypothesis": current_hypothesis, "final_decision": "", "status": "ready"})

        for iteration in range(1, state.max_iterations + 1):
            state.iteration = iteration
            state.phase = "review_hypothesis"
            state.hypothesis = dict(current_hypothesis)
            state.append_trace(f"iteration_{iteration}_start")

            step_result = self._run_causalgate_step(state)
            state.update_from_step_result(step_result.to_dict())
            route = route_next_step(state)
            self._apply_route(state, route)

            if route.terminal:
                state.final_report = _build_final_report(state, route)
                state.append_trace("terminal_route")
                break

            if route.route == "run_required_tests":
                if self.test_executor is None:
                    state.status = "awaiting_test_results"
                    state.phase = "awaiting_external_tests"
                    state.append_trace("await_external_test_executor")
                    break
                test_result = self._call_test_executor(state)
                state.completed_tests.append(test_result)
                state.append_trace("test_executor_completed")
                revised = _as_dict(test_result.get("revised_hypothesis")) or _as_dict(test_result.get("hypothesis"))
                if revised:
                    current_hypothesis = _merge_estimation_payload_into_hypothesis(revised, raw_payload)
                    state.revision_count += 1
                    continue
                state.status = "awaiting_revised_hypothesis_after_tests"
                state.phase = "awaiting_input"
                break

            if route.route in {"revise_hypothesis", "ask_more_data"}:
                next_candidate, candidate_cursor = _next_candidate_from_queue(state, candidate_cursor)
                if not next_candidate and self.hypothesis_generator is not None:
                    next_candidate = self._call_hypothesis_generator(state)
                if not next_candidate and auto_expand and state.hypothesis:
                    expansion = expand_hypothesis(
                        {"hypothesis": state.hypothesis, "verdict": state.verdict, "enable_identification": state.enable_identification},
                        enable_identification=state.enable_identification,
                    )
                    state.metadata["last_hypothesis_expansion"] = expansion
                    state.append_trace("hypothesis_expansion_generated")
                    if expansion.get("accepted"):
                        state.status = "final_candidate_ready_for_external_validation"
                        state.final_decision = "FINAL_CANDIDATE"
                        route = route_next_step(state)
                        self._apply_route(state, route)
                        break
                    if expansion.get("should_continue") and isinstance(expansion.get("expanded_hypothesis"), Mapping):
                        next_candidate = dict(expansion["expanded_hypothesis"])
                    elif expansion.get("state") == "ARCHIVED_UNSUPPORTED":
                        state.status = "archived_unsupported"
                        state.phase = "safe_stop"
                        state.should_continue = False
                        state.warnings.append("Hypothesis expansion archived the current claim as unsupported.")
                        break
                if next_candidate:
                    current_hypothesis = _merge_estimation_payload_into_hypothesis(next_candidate, raw_payload)
                    state.revision_count += 1
                    state.append_trace("revision_candidate_loaded")
                    continue
                state.status = "awaiting_llm_revision" if route.route == "revise_hypothesis" else "awaiting_more_data"
                state.phase = "awaiting_input"
                state.append_trace("await_external_revision")
                break

            state.status = "abstain"
            state.phase = "safe_stop"
            state.final_decision = "ABSTAIN"
            state.warnings.append(f"Unknown or unsupported native route: {route.route}; stopped safely.")
            state.append_trace("safe_stop_unknown_route")
            break
        else:
            state.status = "max_iterations_reached"
            state.phase = "safe_stop"
            route = route_next_step(state)
            self._apply_route(state, route)
            state.warnings.append("Native scientific agent reached its bounded iteration limit.")
            state.append_trace("max_iterations_reached")

        if not state.final_report:
            state.final_report = _build_final_report(state, route)
        return self._result_from_state(state, route)

    def _run_causalgate_step(self, state: NativeScientificAgentState) -> ResearchStepResult:
        runner = ScientificResearchLoop(ledger_path=state.ledger_path, enable_identification=state.enable_identification)
        return runner.run_step({
            "run_id": state.run_id,
            "step": state.iteration,
            "goal": state.goal,
            "feedback": state.feedback or state.next_instruction,
            "hypothesis": dict(state.hypothesis),
            "write_ledger": state.write_ledger,
            "ledger_path": state.ledger_path,
            "enable_identification": state.enable_identification,
        })

    def _call_hypothesis_generator(self, state: NativeScientificAgentState) -> Dict[str, Any]:
        assert self.hypothesis_generator is not None
        try:
            generated = self.hypothesis_generator(state.to_dict())
        except Exception as exc:
            state.warnings.append(f"hypothesis_generator_failed: {type(exc).__name__}: {exc}")
            return {}
        if isinstance(generated, Mapping):
            state.append_trace("hypothesis_generator_proposed_candidate")
            return dict(generated)
        state.warnings.append("hypothesis_generator_returned_no_candidate")
        return {}

    def _call_native_hypothesis_agent(self, payload: Mapping[str, Any], state: NativeScientificAgentState) -> Dict[str, Any]:
        try:
            discovery = generate_hypothesis(payload)
        except Exception as exc:
            state.warnings.append(f"native_hypothesis_agent_failed: {type(exc).__name__}: {exc}")
            return {}
        hypothesis = _as_dict(discovery.get("hypothesis"))
        if not hypothesis:
            state.warnings.append("native_hypothesis_agent_returned_no_candidate")
            return {}
        state.metadata["native_discovery"] = {
            "hypothesis_id": discovery.get("hypothesis_id") or hypothesis.get("hypothesis_id", ""),
            "discovery_patch": _as_dict(discovery.get("discovery_patch")),
        }
        state.warnings.extend(_as_list(discovery.get("warnings")))
        state.append_trace("native_hypothesis_agent_generated_candidate")
        return hypothesis

    def _call_test_executor(self, state: NativeScientificAgentState) -> Dict[str, Any]:
        assert self.test_executor is not None
        try:
            result = self.test_executor(state.to_dict())
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return dict(result) if isinstance(result, Mapping) else {"ok": False, "error": "test_executor_returned_non_mapping"}

    def _apply_route(self, state: NativeScientificAgentState, route: NativeAgentRoute) -> None:
        state.route = route.route
        state.required_next_actor = route.required_next_actor
        state.should_continue = route.should_continue
        state.next_instruction = route.instruction
        state.append_trace(f"route:{route.route}")

    def _result_from_state(self, state: NativeScientificAgentState, route: NativeAgentRoute) -> NativeScientificAgentResult:
        return NativeScientificAgentResult(
            run_id=state.run_id,
            goal=state.goal,
            status=state.status,
            final_decision=state.final_decision,
            route=route.route,
            required_next_actor=route.required_next_actor,
            should_continue=route.should_continue,
            next_instruction=route.instruction,
            iterations_completed=state.iteration,
            state=state.to_dict(),
            route_payload=route.to_dict(),
            final_report=dict(state.final_report),
            warnings=list(state.warnings),
            trace=list(state.trace),
            safety_boundary=native_agent_safety_boundary(),
        )


def run_native_scientific_agent(payload: Mapping[str, Any]) -> Dict[str, Any]:
    return NativeScientificAgent().run(payload).to_dict()


__all__ = ["HypothesisGenerator", "TestExecutor", "NativeScientificAgent", "NativeScientificAgentResult", "run_native_scientific_agent"]
