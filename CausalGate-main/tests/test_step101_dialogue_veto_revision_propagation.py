from causalgate.scientific.llm_dialogue import run_llm_dialogue


def _overclaiming_demo_hypothesis():
    return {
        "hypothesis_id": "dialogue-veto-revision-demo",
        "claim": "In a synthetic demo study, increasing X may increase Y after adjusting for pre-treatment confounder Z.",
        "claim_level": "causally_identified",
        "domain": "empirical_causal_demo",
        "treatment": "X",
        "outcome": "Y",
        "confounders": ["Z"],
        "adjustment_set": ["Z"],
        "dag": {
            "nodes": ["X", "Y", "Z", "N"],
            "edges": [["Z", "X"], ["Z", "Y"], ["X", "Y"]],
        },
        "assumptions": [
            "Z is measured before X and Y.",
            "The supplied DAG is the demo causal graph.",
            "No unmeasured confounding remains after adjusting for Z in this synthetic example.",
        ],
        "identification_strategy": "validated backdoor adjustment using Z",
        "falsification_tests": [
            "Future-X placebo test should not predict present Y.",
            "Negative control outcome N should not change under X after adjustment.",
        ],
        "measurable_predictions": [
            "Estimated Y should increase when X increases under adjustment for Z.",
        ],
        "negative_controls": ["N"],
        "negative_control_variables": ["N"],
        "negative_control_tests": ["N should not increase under X after adjustment for Z."],
        "placebo_tests": ["Future-X placebo must fail."],
        "sensitivity_checks": ["Hidden-confounding sensitivity check and CI review."],
        "data_requirements": ["Synthetic demo payload includes an external effect estimate and confidence interval."],
        "test_plan": "Run SCM-ID, load the supplied demo estimate, keep claim bounded as candidate-level evidence.",
        "metadata": {
            "demo_pipeline": "complete_causal_json",
            "synthetic_demo": True,
            "effect_estimate": 0.12,
            "ci_low": 0.04,
            "ci_high": 0.20,
            "support_n": 240,
            "estimator": "demo_external_effect_estimate",
        },
    }


def test_dialogue_loop_applies_veto_revision_to_same_hypothesis():
    result = run_llm_dialogue({
        "goal": "Complete causal demo",
        "hypothesis": _overclaiming_demo_hypothesis(),
        "enable_identification": True,
        "auto_expand": False,
        "agent_repair": True,
        "max_steps": 4,
        "write_ledger": False,
    })

    assert result["metadata"]["veto_revisions_applied"] == 1
    assert any(turn["actor"] == "causalgate_veto_revision_applier" for turn in result["turns"])

    final_hypothesis = result["final_hypothesis"]
    assert final_hypothesis["hypothesis_id"] == "dialogue-veto-revision-demo"
    assert final_hypothesis["treatment"] == "X"
    assert final_hypothesis["outcome"] == "Y"
    assert final_hypothesis["dag"]["edges"] == [["Z", "X"], ["Z", "Y"], ["X", "Y"]]
    assert final_hypothesis["claim_level"] == "hypothesis_only"
    assert "confirmed" not in final_hypothesis["claim"].lower()
    assert "not confirmation" in final_hypothesis["claim"].lower()
    assert "claim_level_evidence_ceiling" in final_hypothesis["metadata"]["agent_applied_veto_revisions"]
    assert final_hypothesis["metadata"]["max_allowed_claim_level"]["key"] == "candidate_hypothesis"

    evaluated_claims = [turn.get("hypothesis", {}).get("claim", "") for turn in result["turns"] if turn.get("actor") == "causalgate"]
    assert len(evaluated_claims) >= 2
    assert evaluated_claims[0] != evaluated_claims[-1]


def test_dialogue_loop_does_not_reapply_same_veto_revision_forever():
    result = run_llm_dialogue({
        "goal": "Complete causal demo",
        "hypothesis": _overclaiming_demo_hypothesis(),
        "enable_identification": True,
        "auto_expand": False,
        "agent_repair": True,
        "max_steps": 6,
        "write_ledger": False,
    })

    applier_turns = [turn for turn in result["turns"] if turn["actor"] == "causalgate_veto_revision_applier"]
    assert len(applier_turns) == 1
    assert result["steps_completed"] <= 6
