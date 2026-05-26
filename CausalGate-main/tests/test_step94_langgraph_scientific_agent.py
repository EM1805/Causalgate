from __future__ import annotations

from causalgate.mcp.schemas import list_tool_schemas
from causalgate.mcp.tools import call_tool
from causalgate.scientific.langgraph_agent import (
    build_langgraph_scientific_graph,
    langgraph_available,
    prepare_scientific_agent_state,
    run_langgraph_scientific_agent,
    run_stdlib_scientific_agent,
)


def _valid_candidate():
    return {
        "hypothesis_id": "h_step94_valid",
        "claim": "Increasing X is expected to increase Y within a 7 day observation window under the stated DAG assumptions.",
        "claim_level": "testable_candidate",
        "treatment": "X",
        "outcome": "Y",
        "variables": ["X", "Y", "Z", "N"],
        "confounders": ["Z"],
        "adjustment_set": ["Z"],
        "negative_control_variables": ["N"],
        "negative_control_tests": ["Negative control N should not increase after X changes."],
        "falsification_tests": [
            "negative control outcome N remains unchanged",
            "future-X placebo / temporal leakage test should be null",
        ],
        "placebo_tests": ["future-X placebo test"],
        "sensitivity_checks": ["hidden confounding robustness bounds"],
        "measurable_predictions": ["Y should increase within 7 days after higher X, conditional on Z"],
        "assumptions": ["Z is measured for all observations and blocks observed confounding"],
        "data_requirements": ["Measure X, Y, Z confounder, and N daily for at least 90 days"],
        "test_plan": ["Estimate adjusted association with Z and run negative-control and placebo checks"],
        "dag": {"nodes": ["X", "Y", "Z", "N"], "edges": [["Z", "X"], ["Z", "Y"], ["X", "Y"]]},
    }


def test_step94_stdlib_graph_agent_reviews_candidate_without_langgraph_dependency():
    result = run_stdlib_scientific_agent({
        "goal": "Review a candidate mechanism.",
        "candidate_hypotheses": [_valid_candidate()],
        "write_ledger": False,
    })

    assert result["used_langgraph"] is False
    assert result["graph_backend"] == "stdlib_fallback"
    assert result["final_decision"] == "FINAL_CANDIDATE"
    assert result["required_next_actor"] == "human_or_external_validation"
    assert result["graph_trace"] == ["prepare_state", "causalgate_research_cycle", "route_after_veto", "finalize"]
    assert result["cycle"]["step_results"][0]["verdict"]["causal_status"] == "identified_candidate"
    assert "No final scientific answer may bypass" in result["safety_boundary"]["hard_rule"]


def test_step94_requested_langgraph_falls_back_cleanly_when_optional_dependency_missing():
    result = run_langgraph_scientific_agent({
        "goal": "Review with optional LangGraph.",
        "hypothesis": _valid_candidate(),
        "use_langgraph": True,
        "write_ledger": False,
    })

    if not langgraph_available():
        assert result["used_langgraph"] is False
        assert result["graph_backend"] == "stdlib_fallback"
        assert any("not installed" in warning for warning in result["warnings"])
    else:
        assert result["used_langgraph"] is True
        assert result["graph_backend"] == "langgraph"


def test_step94_empty_payload_does_not_autonomously_discover_claims():
    state = prepare_scientific_agent_state({"goal": "Find a new law", "write_ledger": False})
    assert state["candidate_hypotheses"] == []

    result = run_langgraph_scientific_agent({"goal": "Find a new law", "write_ledger": False})
    assert result["should_continue"] is True
    assert result["required_next_actor"] == "llm_or_researcher"
    assert any("No candidate_hypotheses supplied" in warning for warning in result["warnings"])
    assert result["safety_boundary"]["no_autonomous_discovery_claim"].startswith("The agent may output candidate hypotheses")


def test_step94_mcp_tool_schema_and_call_are_available():
    tools = {tool["name"]: tool for tool in list_tool_schemas()}
    assert "causalgate_run_langgraph_scientific_agent" in tools
    schema = tools["causalgate_run_langgraph_scientific_agent"]["inputSchema"]
    assert schema["required"] == ["goal"]
    assert schema["properties"]["use_langgraph"]["default"] is False
    assert tools["causalgate_run_langgraph_scientific_agent"]["annotations"]["readOnlyHint"] is False

    result = call_tool("causalgate_run_langgraph_scientific_agent", {
        "goal": "MCP review",
        "hypothesis": _valid_candidate(),
        "write_ledger": False,
    })
    assert result["final_decision"] == "FINAL_CANDIDATE"
    assert result["cycle"]["steps_completed"] == 1


def test_step94_build_langgraph_graph_has_clear_error_when_not_installed():
    if not langgraph_available():
        try:
            build_langgraph_scientific_graph()
        except RuntimeError as exc:
            assert "langgraph" in str(exc).lower()
        else:  # pragma: no cover
            raise AssertionError("Expected RuntimeError when optional LangGraph dependency is missing")
