from __future__ import annotations

"""Deterministic routing policy for CausalGate's native scientific agent."""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping

from .agent_state import NativeScientificAgentState


ROUTE_NEED_INITIAL_HYPOTHESIS = "need_initial_hypothesis"
ROUTE_RUN_VETO = "run_veto"
ROUTE_REVISE_HYPOTHESIS = "revise_hypothesis"
ROUTE_RUN_REQUIRED_TESTS = "run_required_tests"
ROUTE_ASK_MORE_DATA = "ask_more_data"
ROUTE_FINAL_REPORT = "final_report"
ROUTE_STOP_BLOCKED = "stop_blocked"
ROUTE_EXTERNAL_VALIDATION = "external_validation"
ROUTE_MAX_ITERATIONS_REACHED = "max_iterations_reached"


@dataclass(frozen=True)
class NativeAgentRoute:
    route: str
    required_next_actor: str
    should_continue: bool
    terminal: bool
    instruction: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _state_dict(state: NativeScientificAgentState | Mapping[str, Any]) -> Dict[str, Any]:
    if isinstance(state, NativeScientificAgentState):
        return state.to_dict()
    return dict(state) if isinstance(state, Mapping) else {}


def route_next_step(state: NativeScientificAgentState | Mapping[str, Any]) -> NativeAgentRoute:
    """Route the next action after each CausalGate gate.

    The router is deliberately conservative.  It never upgrades a scientific
    claim; it only decides whether the next actor should be a researcher/LLM,
    test executor, data provider, human validator, or no one because the claim
    is blocked.
    """

    data = _state_dict(state)
    decision = _clean_str(data.get("final_decision") or data.get("veto_status"), "ABSTAIN")
    status = _clean_str(data.get("status"), "initialized")
    instruction = _clean_str(data.get("next_instruction"))
    missing = set(data.get("missing_evidence") or [])
    required_tests = set(data.get("required_tests") or [])
    hypothesis = data.get("hypothesis") if isinstance(data.get("hypothesis"), Mapping) else {}
    step_results = data.get("step_results") or []

    if not hypothesis and not step_results:
        return NativeAgentRoute(
            route=ROUTE_NEED_INITIAL_HYPOTHESIS,
            required_next_actor="llm_or_researcher",
            should_continue=True,
            terminal=False,
            instruction=(
                "Provide a structured ScientificHypothesisPackage with claim, treatment, outcome, DAG, assumptions, "
                "measurable prediction, falsification tests, negative controls, placebo/leakage checks, and data requirements."
            ),
            reason="no_hypothesis_available",
        )

    if status == "max_iterations_reached":
        return NativeAgentRoute(
            route=ROUTE_MAX_ITERATIONS_REACHED,
            required_next_actor="human_or_researcher",
            should_continue=False,
            terminal=True,
            instruction=instruction or "Stop and review the accumulated veto trail before continuing.",
            reason="bounded_iteration_limit_reached",
        )

    if decision == "FINAL_CANDIDATE":
        return NativeAgentRoute(
            route=ROUTE_EXTERNAL_VALIDATION,
            required_next_actor="human_or_external_validation",
            should_continue=False,
            terminal=True,
            instruction=instruction or "Run external validation before making any stronger scientific claim.",
            reason="candidate_passed_causalgate_gate_but_requires_external_validation",
        )

    if decision == "BLOCK":
        return NativeAgentRoute(
            route=ROUTE_STOP_BLOCKED,
            required_next_actor="stop_or_reframe_goal",
            should_continue=False,
            terminal=True,
            instruction=instruction or "Do not publish or act on this claim; reframe the research goal or submit a weaker hypothesis.",
            reason="causalgate_blocked_claim",
        )

    if decision == "REVISE":
        return NativeAgentRoute(
            route=ROUTE_REVISE_HYPOTHESIS,
            required_next_actor="llm_or_researcher",
            should_continue=True,
            terminal=False,
            instruction=instruction or "Revise the hypothesis and resubmit it through CausalGate's veto.",
            reason="hypothesis_revision_required",
        )

    if decision == "TEST_MORE" or required_tests:
        return NativeAgentRoute(
            route=ROUTE_RUN_REQUIRED_TESTS,
            required_next_actor="test_executor_or_researcher",
            should_continue=True,
            terminal=False,
            instruction=instruction or "Run the required falsification, placebo, negative-control, and sensitivity tests.",
            reason="tests_required_before_candidate_status",
        )

    if missing or decision == "ABSTAIN":
        return NativeAgentRoute(
            route=ROUTE_ASK_MORE_DATA,
            required_next_actor="data_provider_or_researcher",
            should_continue=True,
            terminal=False,
            instruction=instruction or "Provide missing structure, measurements, assumptions, or evidence before continuing.",
            reason="missing_evidence_or_abstention",
        )

    return NativeAgentRoute(
        route=ROUTE_RUN_VETO,
        required_next_actor="causalgate_veto",
        should_continue=True,
        terminal=False,
        instruction=instruction or "Run CausalGate's hypothesis veto before any final scientific output.",
        reason="veto_not_yet_run",
    )


__all__ = [
    "NativeAgentRoute",
    "route_next_step",
    "ROUTE_NEED_INITIAL_HYPOTHESIS",
    "ROUTE_RUN_VETO",
    "ROUTE_REVISE_HYPOTHESIS",
    "ROUTE_RUN_REQUIRED_TESTS",
    "ROUTE_ASK_MORE_DATA",
    "ROUTE_FINAL_REPORT",
    "ROUTE_STOP_BLOCKED",
    "ROUTE_EXTERNAL_VALIDATION",
    "ROUTE_MAX_ITERATIONS_REACHED",
]
