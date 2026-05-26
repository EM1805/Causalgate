from causalgate.scientific import expand_hypothesis, evaluate_hypothesis
from causalgate.mcp.tools import call_tool, list_tools


def test_expansion_preserves_incomplete_hypothesis_and_creates_next_draft():
    hypothesis = {
        "hypothesis_id": "H-exp-001",
        "claim": "Sleep may improve productivity.",
        "metadata": {"version": 1},
    }
    verdict = evaluate_hypothesis(hypothesis, enable_identification=False)
    result = expand_hypothesis({"hypothesis": hypothesis, "verdict": verdict}, enable_identification=False)

    assert result["state"] in {"NEEDS_STRUCTURE", "NEEDS_FALSIFICATION", "DRAFT"}
    assert result["accepted"] is False
    assert result["should_continue"] is True
    assert result["new_version"] == 2
    assert result["lineage"]["parent_hypothesis_id"] == "H-exp-001"
    assert result["expanded_hypothesis"]["metadata"]["previous_decision"] == verdict["decision"]
    assert result["expanded_hypothesis"]["metadata"]["claim_rule"]
    assert result["expansion_questions"]
    assert "Expanded draft is not accepted yet" in result["warnings"][0]


def test_expansion_adds_falsification_scaffold_when_tests_are_missing():
    hypothesis = {
        "hypothesis_id": "H-exp-002",
        "claim": "X may causally affect Y.",
        "treatment": "X",
        "outcome": "Y",
        "dag": {"nodes": ["X", "Y"], "edges": [{"source": "X", "target": "Y"}]},
        "assumptions": ["No uncontrolled confounding."],
        "data_requirements": ["Time ordered X and Y."],
    }
    result = expand_hypothesis({
        "hypothesis": hypothesis,
        "verdict": {
            "decision": "TEST_MORE",
            "missing_items": ["falsification_tests", "negative_control_outcome_or_exposure"],
            "required_tests": ["negative_control", "placebo_or_temporal_leakage_test"],
        },
    }, enable_identification=False)

    expanded = result["expanded_hypothesis"]
    assert result["state"] == "NEEDS_FALSIFICATION"
    assert expanded["falsification_tests"]
    assert expanded["negative_control_tests"]
    assert expanded["placebo_tests"]
    assert result["next_required_step"] == "add_falsification_tests"


def test_expansion_accepts_final_candidate_without_forcing_stronger_claim():
    hypothesis = {
        "hypothesis_id": "H-exp-003",
        "claim": "X may causally affect Y under stated assumptions.",
        "claim_level": "testable_candidate",
        "metadata": {"version": 4},
    }
    result = expand_hypothesis({
        "hypothesis": hypothesis,
        "verdict": {"decision": "FINAL_CANDIDATE", "missing_items": [], "required_tests": []},
    }, enable_identification=False)

    assert result["state"] == "ACCEPTED_CANDIDATE"
    assert result["accepted"] is True
    assert result["should_continue"] is False
    assert result["new_version"] == 4
    assert "external validation" in result["warnings"][0]


def test_mcp_exposes_hypothesis_expansion_tool():
    tools = {tool["name"] for tool in list_tools()["tools"]}
    assert "causalgate_expand_hypothesis" in tools

    result = call_tool("causalgate_expand_hypothesis", {
        "hypothesis": {"hypothesis_id": "H-mcp-exp", "claim": "X may affect Y."},
        "verdict": {"decision": "REVISE", "missing_items": ["dag_with_nodes_and_edges"]},
        "enable_identification": False,
    })
    assert result["state"] == "NEEDS_STRUCTURE"
    assert result["expanded_hypothesis"]["metadata"]["expanded_by"] == "causalgate.scientific.hypothesis_expansion"
