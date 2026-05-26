from __future__ import annotations

"""Optional LangGraph adapter for CausalGate's scientific research loop.

This module intentionally keeps LangGraph optional.  The stdlib fallback is the
canonical safe path used by MCP, Hugging Face Spaces, and tests.  When LangGraph
is installed, callers may request a real LangGraph execution graph, but the
safety boundary is the same:

LLM/planner may propose or revise hypotheses; CausalGate must veto/audit before any
scientific claim is returned.
"""

from dataclasses import asdict, dataclass, field
from importlib.util import find_spec
from typing import Any, Callable, Dict, List, Mapping, Optional, TypedDict
from uuid import uuid4

from .research_cycle import run_research_cycle


HypothesisGenerator = Callable[[Mapping[str, Any]], Mapping[str, Any]]


class ScientificAgentState(TypedDict, total=False):
    """State object shared by the LangGraph and fallback execution paths."""

    goal: str
    run_id: str
    max_steps: int
    candidate_hypotheses: List[Dict[str, Any]]
    feedback: str
    ledger_path: str
    write_ledger: bool
    enable_identification: bool
    cycle: Dict[str, Any]
    final_decision: str
    status: str
    should_continue: bool
    next_instruction: str
    required_next_actor: str
    graph_trace: List[str]
    graph_backend: str
    warnings: List[str]


@dataclass
class LangGraphScientificAgentResult:
    """Result of the optional LangGraph scientific agent adapter."""

    run_id: str
    goal: str
    status: str
    graph_backend: str
    langgraph_available: bool
    used_langgraph: bool
    final_decision: str
    should_continue: bool
    required_next_actor: str
    next_instruction: str
    cycle: Dict[str, Any] = field(default_factory=dict)
    graph_trace: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    safety_boundary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if not data["safety_boundary"]:
            data["safety_boundary"] = default_safety_boundary()
        return data


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


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    parsed = _as_int(value, default)
    return max(minimum, min(maximum, parsed))


def _default_run_id() -> str:
    return "langgraph_scientific_" + uuid4().hex[:12]


def langgraph_available() -> bool:
    """Return True when the optional ``langgraph`` package is importable."""

    return find_spec("langgraph") is not None


def default_safety_boundary() -> Dict[str, Any]:
    return {
        "llm_role": "May generate or revise hypotheses, tests, and prose.",
        "causalgate_role": "Must normalize, veto, audit claim level, and decide whether stronger evidence is required.",
        "hard_rule": "No final scientific answer may bypass CausalGate's hypothesis veto and claim-level audit.",
        "allowed_public_claim": "Respect cycle.step_results[-1].verdict.max_allowed_claim_level before wording any result.",
        "no_autonomous_discovery_claim": "The agent may output candidate hypotheses, not confirmed new laws without external validation.",
    }


def _normalize_candidates(data: Mapping[str, Any]) -> List[Dict[str, Any]]:
    raw_candidates = data.get("candidate_hypotheses") or data.get("hypotheses") or data.get("candidates")
    if raw_candidates is None and isinstance(data.get("hypothesis"), Mapping):
        raw_candidates = [data.get("hypothesis")]

    candidates: List[Dict[str, Any]] = []
    for item in _as_list(raw_candidates):
        if isinstance(item, Mapping):
            candidates.append(dict(item))
    return candidates


def prepare_scientific_agent_state(payload: Mapping[str, Any]) -> ScientificAgentState:
    """Normalize external payloads into the agent's state object."""

    data = _as_dict(payload)
    return {
        "goal": _clean_str(data.get("goal") or data.get("research_goal") or data.get("objective"), "Review a scientific hypothesis candidate."),
        "run_id": _clean_str(data.get("run_id"), _default_run_id()),
        "max_steps": _clamp_int(data.get("max_steps"), default=3, minimum=1, maximum=25),
        "candidate_hypotheses": _normalize_candidates(data),
        "feedback": _clean_str(data.get("feedback") or data.get("feedback_in") or data.get("previous_feedback")),
        "ledger_path": _clean_str(data.get("ledger_path"), "out/scientific/ledger.jsonl"),
        "write_ledger": _as_bool(data.get("write_ledger"), False),
        "enable_identification": _as_bool(data.get("enable_identification"), True),
        "graph_trace": ["prepare_state"],
        "graph_backend": "stdlib_fallback",
        "warnings": [],
    }


def _run_causalgate_cycle_node(state: ScientificAgentState) -> ScientificAgentState:
    """Run the safe CausalGate review cycle node."""

    cycle_payload: Dict[str, Any] = {
        "goal": state.get("goal", ""),
        "run_id": state.get("run_id", _default_run_id()),
        "max_steps": state.get("max_steps", 3),
        "candidate_hypotheses": state.get("candidate_hypotheses", []),
        "feedback": state.get("feedback", ""),
        "ledger_path": state.get("ledger_path", "out/scientific/ledger.jsonl"),
        "write_ledger": state.get("write_ledger", False),
        "enable_identification": state.get("enable_identification", True),
    }
    cycle = run_research_cycle(cycle_payload, enable_identification=bool(state.get("enable_identification", True)))
    trace = list(state.get("graph_trace", [])) + ["causalgate_research_cycle"]
    return {
        **state,
        "cycle": cycle,
        "final_decision": _clean_str(cycle.get("final_decision"), "ABSTAIN"),
        "status": _clean_str(cycle.get("status"), "abstain"),
        "should_continue": bool(cycle.get("should_continue", True)),
        "next_instruction": _clean_str(cycle.get("next_instruction")),
        "graph_trace": trace,
    }


def _route_after_cycle_node(state: ScientificAgentState) -> ScientificAgentState:
    """Decide who must act next after CausalGate's review."""

    should_continue = bool(state.get("should_continue", True))
    status = _clean_str(state.get("status"), "abstain")
    decision = _clean_str(state.get("final_decision"), "ABSTAIN")

    if not should_continue and decision == "FINAL_CANDIDATE":
        next_actor = "human_or_external_validation"
    elif not should_continue and decision == "BLOCK":
        next_actor = "stop_or_reframe_goal"
    elif status == "awaiting_llm_revision":
        next_actor = "llm_or_researcher"
    else:
        next_actor = "llm_or_researcher"

    return {
        **state,
        "required_next_actor": next_actor,
        "graph_trace": list(state.get("graph_trace", [])) + ["route_after_veto"],
    }


def _finalize_node(state: ScientificAgentState) -> ScientificAgentState:
    warnings = list(state.get("warnings", []))
    if state.get("required_next_actor") == "llm_or_researcher" and not state.get("candidate_hypotheses"):
        warnings.append("No candidate_hypotheses supplied; CausalGate returned a skeleton/revision instruction instead of doing autonomous discovery.")
    return {
        **state,
        "warnings": warnings,
        "graph_trace": list(state.get("graph_trace", [])) + ["finalize"],
    }


def run_stdlib_scientific_agent(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Run the graph-shaped scientific agent without requiring LangGraph."""

    state = prepare_scientific_agent_state(payload)
    state = _run_causalgate_cycle_node(state)
    state = _route_after_cycle_node(state)
    state = _finalize_node(state)
    return _state_to_result(state, used_langgraph=False).to_dict()


def build_langgraph_scientific_graph() -> Any:
    """Build a LangGraph StateGraph when the optional package is installed.

    The graph is intentionally small and auditable: prepare -> CausalGate cycle ->
    route -> finalize.  A future LLM generation node can be inserted before the
    CausalGate cycle, but it must still pass through the same veto node.
    """

    if not langgraph_available():
        raise RuntimeError("Optional dependency 'langgraph' is not installed. Use run_stdlib_scientific_agent or install requirements-langgraph.txt.")

    from langgraph.graph import END, START, StateGraph  # type: ignore

    graph = StateGraph(ScientificAgentState)
    graph.add_node("prepare", lambda state: prepare_scientific_agent_state(state))
    graph.add_node("causalgate_cycle", _run_causalgate_cycle_node)
    graph.add_node("route", _route_after_cycle_node)
    graph.add_node("finalize", _finalize_node)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "causalgate_cycle")
    graph.add_edge("causalgate_cycle", "route")
    graph.add_edge("route", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


def _state_to_result(state: ScientificAgentState, *, used_langgraph: bool) -> LangGraphScientificAgentResult:
    return LangGraphScientificAgentResult(
        run_id=_clean_str(state.get("run_id")),
        goal=_clean_str(state.get("goal")),
        status=_clean_str(state.get("status"), "abstain"),
        graph_backend="langgraph" if used_langgraph else _clean_str(state.get("graph_backend"), "stdlib_fallback"),
        langgraph_available=langgraph_available(),
        used_langgraph=used_langgraph,
        final_decision=_clean_str(state.get("final_decision"), "ABSTAIN"),
        should_continue=bool(state.get("should_continue", True)),
        required_next_actor=_clean_str(state.get("required_next_actor"), "llm_or_researcher"),
        next_instruction=_clean_str(state.get("next_instruction")),
        cycle=_as_dict(state.get("cycle")),
        graph_trace=list(state.get("graph_trace", [])),
        warnings=list(state.get("warnings", [])),
        safety_boundary=default_safety_boundary(),
    )


def run_langgraph_scientific_agent(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Run the CausalGate scientific agent through LangGraph when requested.

    Payload options:
    - ``use_langgraph``: if true and LangGraph is installed, use a compiled
      StateGraph. Otherwise return the stdlib fallback result with a warning.
    - ``candidate_hypotheses`` or ``hypothesis``: LLM/researcher generated
      candidates to be reviewed. CausalGate does not invent them by itself.
    """

    data = _as_dict(payload)
    requested_langgraph = _as_bool(data.get("use_langgraph"), False)
    if requested_langgraph and langgraph_available():
        try:
            graph = build_langgraph_scientific_graph()
            state = graph.invoke(data)
            return _state_to_result(state, used_langgraph=True).to_dict()
        except Exception as exc:  # pragma: no cover - depends on optional LangGraph runtime/version.
            fallback = run_stdlib_scientific_agent(data)
            fallback.setdefault("warnings", []).append(f"LangGraph execution failed; stdlib fallback used: {type(exc).__name__}: {exc}")
            fallback["used_langgraph"] = False
            fallback["graph_backend"] = "stdlib_fallback_after_langgraph_error"
            return fallback

    result = run_stdlib_scientific_agent(data)
    if requested_langgraph and not result.get("langgraph_available"):
        result.setdefault("warnings", []).append("LangGraph was requested but is not installed; stdlib fallback used. Install requirements-langgraph.txt to enable it.")
    return result


__all__ = [
    "ScientificAgentState",
    "LangGraphScientificAgentResult",
    "langgraph_available",
    "default_safety_boundary",
    "prepare_scientific_agent_state",
    "build_langgraph_scientific_graph",
    "run_stdlib_scientific_agent",
    "run_langgraph_scientific_agent",
]
