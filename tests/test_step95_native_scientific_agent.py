from causalgate.scientific import (
    NativeScientificAgent,
    NativeScientificAgentState,
    route_next_step,
    run_native_scientific_agent,
)
from causalgate.mcp.tools import call_tool


def _valid_testable_hypothesis():
    return {
        "claim": "X may increase Y within 7 days under explicit assumptions.",
        "claim_level": "testable_candidate",
        "treatment": "X",
        "outcome": "Y",
        "dag": {"nodes": ["X", "Y", "N"], "edges": [["X", "Y"]]},
        "assumptions": ["X temporally precedes Y", "No unmeasured confounding in this simplified test setting"],
        "falsification_tests": [
            "A future-X placebo should not predict present Y",
            "Negative control outcome N should not change when X changes",
        ],
        "measurable_predictions": ["Y should increase within 7 days after X compared with baseline"],
        "negative_control_variables": ["N"],
        "negative_control_tests": ["N should not increase within 7 days after X"],
        "placebo_tests": ["future X placebo must fail"],
        "sensitivity_checks": ["hidden confounding sensitivity check"],
        "data_requirements": ["daily measured X, Y, N for at least 120 days"],
        "test_plan": "Fit lagged model, run bootstrap and placebo checks.",
    }


def test_native_agent_does_not_invent_hypothesis_when_empty():
    result = run_native_scientific_agent({"goal": "Find a new causal law", "write_ledger": False})
    assert result["status"] == "awaiting_initial_hypothesis"
    assert result["final_decision"] == "ABSTAIN"
    assert result["route"] == "need_initial_hypothesis"
    assert result["required_next_actor"] == "llm_or_researcher"
    assert "refused to invent" in " ".join(result["warnings"])


def test_native_agent_routes_valid_candidate_to_external_validation():
    result = run_native_scientific_agent({
        "goal": "Review candidate",
        "hypothesis": _valid_testable_hypothesis(),
        "write_ledger": False,
        "enable_identification": False,
    })
    assert result["final_decision"] == "FINAL_CANDIDATE"
    assert result["route"] == "external_validation"
    assert result["required_next_actor"] == "human_or_external_validation"
    assert result["final_report"]["public_claim_boundary"]["final_decision"] == "FINAL_CANDIDATE"


def test_native_agent_routes_overclaim_to_revision():
    bad = _valid_testable_hypothesis()
    bad["claim"] = "We proved a new law: X always causes Y."
    result = run_native_scientific_agent({"goal": "Review overclaim", "hypothesis": bad, "write_ledger": False})
    assert result["final_decision"] == "REVISE"
    assert result["route"] == "revise_hypothesis"
    assert result["required_next_actor"] == "llm_or_researcher"


def test_route_next_step_rejects_empty_state():
    state = NativeScientificAgentState.from_payload({"goal": "empty"})
    route = route_next_step(state)
    assert route.route == "need_initial_hypothesis"
    assert route.should_continue is True


def test_native_agent_local_generator_is_optional_and_bounded():
    def generator(state):
        return _valid_testable_hypothesis()

    result = NativeScientificAgent(hypothesis_generator=generator).run({"goal": "Generate one candidate", "write_ledger": False})
    data = result.to_dict()
    assert data["final_decision"] == "FINAL_CANDIDATE"
    assert "hypothesis_generator_proposed_candidate" in data["trace"]


def test_native_agent_can_opt_into_deterministic_hypothesis_generation():
    result = run_native_scientific_agent({
        "goal": "green space visits -> stress levels",
        "native_hypothesis_agent": True,
        "write_ledger": False,
        "enable_identification": False,
        "max_iterations": 4,
    })

    assert result["state"]["metadata"]["native_hypothesis_agent"] is True
    assert result["state"]["metadata"]["native_discovery"]["hypothesis_id"]
    assert "native_hypothesis_agent_generated_candidate" in result["trace"]
    assert result["state"]["hypothesis"]["claim_level"] == "hypothesis_only"
    assert result["final_decision"] in {"FINAL_CANDIDATE", "REVISE", "TEST_MORE", "ABSTAIN"}


def test_native_agent_propagates_top_level_estimation_payload_to_hypothesis_metadata():
    result = run_native_scientific_agent({
        "goal": "Review candidate with existing estimate",
        "hypothesis": _valid_testable_hypothesis(),
        "write_ledger": False,
        "enable_identification": False,
        "effect_estimate": 0.12,
        "ci_low": 0.04,
        "ci_high": 0.20,
        "data_path": "data/study.csv",
    })

    metadata = result["state"]["hypothesis"]["metadata"]
    assert metadata["effect_estimate"] == 0.12
    assert metadata["ci_low"] == 0.04
    assert metadata["ci_high"] == 0.20
    assert metadata["data_path"] == "data/study.csv"


def test_mcp_exposes_native_agent_tool():
    tools = call_tool("causalgate_health", {})["tools"]
    assert "causalgate_run_native_scientific_agent" in tools
    result = call_tool("causalgate_run_native_scientific_agent", {"goal": "Review", "write_ledger": False})
    assert result["route"] == "need_initial_hypothesis"
