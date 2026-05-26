from causalgate.causal_core.identification.engine import identify_effect
from causalgate.scientific.hypothesis_veto import evaluate_hypothesis


def _base_payload(adjustment_set):
    return {
        "graph": {
            "nodes": ["X", "Y", "Z", "W"],
            "edges": [["Z", "X"], ["Z", "Y"], ["X", "Y"]],
        },
        "treatment": "X",
        "outcome": "Y",
        "adjustment_set": adjustment_set,
    }


def test_wrong_adjustment_set_is_not_identified():
    result = identify_effect(_base_payload(["W"]))
    assert result["identified"] is False
    assert result["identification_strategy"] == "blocked_invalid_adjustment_set"
    assert "INVALID_ADJUSTMENT_SET_BACKDOOR_OPEN" in result["reason_codes"]
    assert result["raw_id_result"]["open_backdoor_paths"]


def test_valid_backdoor_adjustment_set_is_identified():
    result = identify_effect(_base_payload(["Z"]))
    assert result["identified"] is True
    assert result["identification_strategy"] == "validated_backdoor_adjustment"
    assert "VALID_BACKDOOR_ADJUSTMENT_SET" in result["reason_codes"]
    assert result["raw_id_result"]["open_backdoor_paths"] == []


def test_post_treatment_adjustment_is_rejected():
    result = identify_effect({
        "graph": {
            "nodes": ["X", "Y", "Z", "M"],
            "edges": [["Z", "X"], ["Z", "Y"], ["X", "M"], ["M", "Y"]],
        },
        "treatment": "X",
        "outcome": "Y",
        "adjustment_set": ["Z", "M"],
    })
    assert result["identified"] is False
    assert "ADJUSTMENT_SET_CONTAINS_POST_TREATMENT_DESCENDANT" in result["reason_codes"]


def test_bidirected_hidden_confounding_blocks_simple_online_id():
    result = identify_effect({
        "graph": {
            "nodes": ["X", "Y"],
            "bidirected_edges": [["X", "Y"]],
        },
        "treatment": "X",
        "outcome": "Y",
        "adjustment_set": [],
    })
    assert result["identified"] is False
    assert "HIDDEN_CONFOUNDING_BIDIRECTED_EDGE" in result["reason_codes"]


def _complete_scientific_payload(adjustment_set):
    return {
        "hypothesis_id": "step90-demo",
        "claim": "X may increase Y under the stated measurement window.",
        "claim_level": "causally_identified",
        "treatment": "X",
        "outcome": "Y",
        "confounders": ["Z"],
        "adjustment_set": adjustment_set,
        "dag": {
            "nodes": ["X", "Y", "Z", "W", "N"],
            "edges": [["Z", "X"], ["Z", "Y"], ["X", "Y"]],
        },
        "assumptions": ["Z is observed before X and Y."],
        "falsification_tests": ["negative control outcome N", "future-X placebo test"],
        "measurable_predictions": ["If X increases by one unit, Y should rise within 7 days."],
        "negative_controls": ["N"],
        "placebo_tests": ["future-X placebo test"],
        "sensitivity_checks": ["hidden confounding sensitivity check"],
        "data_requirements": ["measure X, Y, Z, and N daily; Z is observed confounder"],
        "test_plan": "Estimate effect with adjustment set and run falsification tests.",
    }


def test_scientific_veto_does_not_promote_wrong_llm_adjustment_set():
    result = evaluate_hypothesis(_complete_scientific_payload(["W"]))
    assert result["causal_status"] == "not_identified"
    assert "EFFECT_NOT_IDENTIFIED_OR_ID_UNAVAILABLE" in result["reason_codes"]
    assert result["identification"]["identified"] is False
    assert "INVALID_ADJUSTMENT_SET_BACKDOOR_OPEN" in result["identification"]["reason_codes"]


def test_scientific_veto_accepts_valid_adjustment_only_as_candidate():
    result = evaluate_hypothesis(_complete_scientific_payload(["Z"]))
    assert result["causal_status"] == "identified_candidate"
    assert result["identification"]["identified"] is True
    assert "VALID_BACKDOOR_ADJUSTMENT_SET" in result["identification"]["reason_codes"]
