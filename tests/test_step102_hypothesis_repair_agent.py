from causalgate.mcp.tools import call_tool
from causalgate.scientific import repair_hypothesis, run_llm_dialogue


def _candidate():
    return {
        "hypothesis_id": "H_repair_1",
        "claim": "A tutoring program may improve student scores under stated assumptions.",
        "claim_level": "hypothesis_only",
        "treatment": "TutoringProgram",
        "outcome": "PostScore",
        "dag": {
            "nodes": ["TutoringProgram", "PostScore", "PriorScore", "SES"],
            "directed_edges": [
                ["TutoringProgram", "PostScore"],
                ["PriorScore", "TutoringProgram"],
                ["PriorScore", "PostScore"],
                ["SES", "TutoringProgram"],
                ["SES", "PostScore"],
            ],
        },
        "assumptions": ["Exposure is measured before the outcome window."],
        "measurable_predictions": ["After 12 weeks, exposed students are predicted to have higher measured scores than comparison students."],
        "falsification_tests": [
            "No adjusted difference appears in the target outcome.",
            "Future exposure predicts baseline outcome, indicating leakage.",
        ],
        "negative_control_tests": ["A prespecified unrelated outcome should show no adjusted association."],
        "placebo_tests": ["A future-treatment placebo should not predict earlier outcomes."],
        "sensitivity_checks": ["Run hidden-confounding robustness checks."],
        "data_requirements": ["Student-level exposure and outcome records."],
        "test_plan": "Estimate adjusted effects and run falsification checks before any claim upgrade.",
    }


def test_repair_agent_patches_adjustment_set_from_dag():
    hypothesis = _candidate()
    verdict = call_tool("causalgate_veto_hypothesis", {"hypothesis": hypothesis, "enable_identification": False})
    assert verdict["decision"] == "REVISE"
    assert "adjustment_set" in verdict["missing_items"]

    repair = repair_hypothesis({"hypothesis": hypothesis, "verdict": verdict})
    repaired = repair["repaired_hypothesis"]

    assert set(repaired["adjustment_set"]) == {"PriorScore", "SES"}
    assert repaired["claim_level"] == "hypothesis_only"
    assert repair["revision_patch"]["claim_level_changed"] is False


def test_dialogue_uses_repair_agent_before_external_revision():
    result = run_llm_dialogue({
        "goal": "Repair a structured empirical hypothesis.",
        "hypothesis": _candidate(),
        "max_steps": 6,
        "auto_expand": True,
        "agent_repair": True,
        "enable_identification": False,
    })

    assert result["metadata"]["agent_repair"] is True
    assert result["metadata"]["repairs_applied"] >= 1
    assert any(turn["actor"] == "causalgate_repair_agent" for turn in result["turns"])
    assert result["final_hypothesis"]["claim_level"] == "hypothesis_only"
