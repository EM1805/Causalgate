from causalgate.scientific import (
    CLAIM_LEVELS,
    ScientificHypothesisPackage,
    claim_level_audit,
    evaluate_hypothesis,
    normalize_claim_level,
)


def _complete_payload(claim_level="hypothesis_only"):
    return {
        "hypothesis_id": "hyp_claim_level_demo",
        "claim": "X may cause Y if Z is controlled.",
        "claim_level": claim_level,
        "variables": {"treatment": "X", "outcome": "Y", "confounders": ["Z"]},
        "dag": {"edges": [["Z", "X"], ["Z", "Y"], ["X", "Y"]]},
        "assumptions": ["Z is observed", "X precedes Y"],
        "adjustment_set": ["Z"],
        "measurable_predictions": ["If X increases, Y should change after a defined lag while controlling for Z."],
        "falsification_tests": ["negative control", "future-X placebo", "hidden confounding sensitivity check"],
        "negative_controls": ["Negative control outcome N should not change."],
        "placebo_tests": ["future-X placebo"],
        "sensitivity_checks": ["hidden confounding sensitivity check"],
        "data_requirements": ["observed Z", "time ordered samples"],
        "test_plan": "Estimate adjusted X->Y and compare with negative control and future-X placebo.",
    }


def test_claim_level_ladder_has_eight_levels():
    assert len(CLAIM_LEVELS) == 8
    assert normalize_claim_level("hypothesis_only").index == 2
    assert normalize_claim_level("testable_candidate").index == 3
    assert normalize_claim_level("level_5").key == "causally_identified"


def test_hypothesis_contract_stores_numeric_claim_level():
    hyp = ScientificHypothesisPackage.from_dict(_complete_payload("level_3"))
    assert hyp.claim_level == "testable_candidate"
    assert hyp.claim_level_index == 3
    assert hyp.claim_level_key == "testable_hypothesis"
    assert hyp.to_identification_query()["claim_level_index"] == 3


def test_final_candidate_is_capped_at_testable_without_extra_evidence():
    result = evaluate_hypothesis(_complete_payload("hypothesis_only"), enable_identification=False)
    assert result["decision"] == "FINAL_CANDIDATE"
    assert result["claim_level_index"] == 3
    assert result["scientific_claim_level"]["key"] == "testable_hypothesis"
    assert result["max_allowed_claim_level"]["index"] == 3


def test_strong_requested_claim_is_downgraded_or_revised():
    result = evaluate_hypothesis(_complete_payload("level_7"), enable_identification=False)
    assert result["decision"] == "REVISE"
    assert result["claim_level_downgraded"] is True
    assert result["requested_claim_level"]["index"] == 7
    assert result["max_allowed_claim_level"]["index"] <= 2
    assert "CLAIM_LEVEL_DOWNGRADED_TO_EVIDENCE_CEILING" in result["reason_codes"]


def test_claim_level_audit_allows_identification_ceiling():
    audit = claim_level_audit(
        "level_5",
        decision="FINAL_CANDIDATE",
        missing_items=[],
        identification={"identified": True, "identification_tier": "identified_graphical"},
        falsification={},
    )
    assert audit["max_allowed"]["index"] == 5
    assert audit["final"]["index"] == 5
