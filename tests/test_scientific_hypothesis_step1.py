from causalgate.scientific import ScientificHypothesisPackage, evaluate_hypothesis


def test_scientific_hypothesis_contract_normalizes_compact_dag():
    payload = {
        "claim": "X may affect Y through M.",
        "variables": {"treatment": "X", "outcome": "Y", "mediators": ["M"], "confounders": ["Z"]},
        "dag": {"edges": [["Z", "X"], ["Z", "Y"], ["X", "M"], ["M", "Y"]]},
        "assumptions": ["Z is observed"],
        "adjustment_set": ["Z"],
        "measurable_predictions": ["If X increases, Y should increase within a 7-day window after controlling for Z."],
        "falsification_tests": ["negative control", "placebo test", "hidden confounding sensitivity check"],
        "negative_controls": ["Negative control outcome N should not change."],
        "placebo_tests": ["future-X placebo test"],
        "sensitivity_checks": ["hidden confounding sensitivity check"],
        "data_requirements": ["observed X before Y", "observed Z"],
        "test_plan": "Compare adjusted effect with negative control and placebo tests.",
    }
    hyp = ScientificHypothesisPackage.from_dict(payload)
    assert hyp.treatment == "X"
    assert hyp.outcome == "Y"
    assert len(hyp.dag["nodes"]) >= 4
    assert hyp.missing_core_items() == []


def test_scientific_veto_revises_overclaim():
    result = evaluate_hypothesis(
        {
            "claim": "We discovered a new law: X always causes Y.",
            "variables": {"treatment": "X", "outcome": "Y"},
            "dag": {"edges": [["X", "Y"]]},
            "assumptions": ["temporal order"],
            "measurable_predictions": ["If X increases, Y should increase within a defined window."],
            "falsification_tests": ["negative control", "placebo test", "hidden confounding sensitivity check"],
            "negative_controls": ["Negative control outcome N should not change."],
            "placebo_tests": ["future-X placebo test"],
            "sensitivity_checks": ["hidden confounding sensitivity check"],
            "data_requirements": ["observed X and Y"],
            "test_plan": "Compare against negative control and placebo.",
        },
        enable_identification=False,
    )
    assert result["decision"] == "REVISE"
    assert "OVERCLAIM_RISK_HIGH" in result["reason_codes"]


def test_scientific_veto_accepts_structured_candidate_without_id_backend():
    result = evaluate_hypothesis(
        {
            "claim": "X may cause Y if Z is controlled.",
            "claim_level": "hypothesis_only",
            "variables": {"treatment": "X", "outcome": "Y", "confounders": ["Z"]},
            "dag": {"edges": [["Z", "X"], ["Z", "Y"], ["X", "Y"]]},
            "assumptions": ["Z is observed", "X precedes Y"],
            "adjustment_set": ["Z"],
            "measurable_predictions": ["If X increases, Y should increase within a 7-day lag after controlling for Z."],
            "falsification_tests": ["negative control", "future-X placebo", "hidden confounding sensitivity check"],
            "negative_controls": ["Negative control outcome N should not change."],
            "placebo_tests": ["future-X placebo"],
            "sensitivity_checks": ["hidden confounding sensitivity check"],
            "data_requirements": ["observed Z", "time ordered samples"],
            "test_plan": "Estimate adjusted X->Y and compare with negative control and future-X placebo.",
        },
        enable_identification=False,
    )
    assert result["decision"] == "FINAL_CANDIDATE"
    assert result["claim_level"] == "testable_candidate"
    assert result["short_for_llm"]["scientific_rule"]
