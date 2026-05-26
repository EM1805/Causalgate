from causalgate.causal_core.identification import identify_effect
from causalgate.scientific.hypothesis_veto import evaluate_hypothesis


def _frontdoor_graph():
    return {
        "nodes": ["X", "M", "Y", "U"],
        "edges": [["X", "M"], ["M", "Y"], ["U", "X"], ["U", "Y"]],
    }


def test_valid_frontdoor_mediator_set_is_identified():
    result = identify_effect({
        "graph": _frontdoor_graph(),
        "treatment": "X",
        "outcome": "Y",
        "mediators": ["M"],
        "strategy_hint": "frontdoor",
    })

    assert result["identified"] is True
    assert result["identification_strategy"] == "validated_frontdoor_mediator"
    assert result["identification_tier"] == "identified_frontdoor"
    assert "VALID_FRONTDOOR_MEDIATOR_SET" in result["reason_codes"]
    assert result["mediators"] == ["M"]
    assert "sum_{M}" in result["formula"]


def test_frontdoor_rejects_direct_path_bypassing_mediator():
    result = identify_effect({
        "graph": {
            "nodes": ["X", "M", "Y", "U"],
            "edges": [["X", "M"], ["M", "Y"], ["X", "Y"], ["U", "X"], ["U", "Y"]],
        },
        "treatment": "X",
        "outcome": "Y",
        "mediators": ["M"],
        "strategy_hint": "frontdoor",
    })

    assert result["identified"] is False
    assert result["identification_strategy"] == "blocked_invalid_frontdoor_mediator_set"
    assert "FRONTDOOR_DIRECT_PATH_BYPASSES_MEDIATOR" in result["reason_codes"]
    assert result["raw_id_result"]["directed_paths_bypassing_mediators"]


def test_frontdoor_rejects_open_backdoor_from_treatment_to_mediator():
    result = identify_effect({
        "graph": {
            "nodes": ["X", "M", "Y", "U", "C"],
            "edges": [["X", "M"], ["M", "Y"], ["U", "X"], ["U", "Y"], ["C", "X"], ["C", "M"]],
        },
        "treatment": "X",
        "outcome": "Y",
        "mediators": ["M"],
        "strategy_hint": "frontdoor",
    })

    assert result["identified"] is False
    assert result["identification_strategy"] == "blocked_invalid_frontdoor_mediator_set"
    assert "FRONTDOOR_BACKDOOR_X_TO_MEDIATOR_OPEN" in result["reason_codes"]
    assert result["raw_id_result"]["open_backdoor_paths_x_to_mediator"]


def _complete_frontdoor_hypothesis():
    return {
        "hypothesis_id": "step91-frontdoor-demo",
        "claim": "X may affect Y through mediator M under the stated front-door assumptions.",
        "claim_level": "causally_identified",
        "treatment": "X",
        "outcome": "Y",
        "mediators": ["M"],
        "dag": _frontdoor_graph(),
        "assumptions": [
            "M lies on the directed pathway from X to Y.",
            "There is no open backdoor path from X to M.",
            "All backdoor paths from M to Y are blocked by X.",
        ],
        "identification_strategy": "frontdoor via M",
        "falsification_tests": ["negative control outcome N", "future-X placebo test"],
        "measurable_predictions": ["Changing X should change M before Y changes."],
        "negative_controls": ["N"],
        "placebo_tests": ["future-X placebo test"],
        "sensitivity_checks": ["front-door mediator sensitivity check"],
        "data_requirements": ["measure X, M, Y, and negative control N in temporal order"],
        "test_plan": "Estimate front-door mediated effect and run falsification tests.",
    }


def test_scientific_veto_accepts_valid_frontdoor_only_as_candidate():
    result = evaluate_hypothesis(_complete_frontdoor_hypothesis())

    assert result["causal_status"] == "identified_candidate"
    assert result["identification"]["identified"] is True
    assert result["identification"]["identification_strategy"] == "validated_frontdoor_mediator"
    assert "VALID_FRONTDOOR_MEDIATOR_SET" in result["identification"]["reason_codes"]
    assert result["decision"] in {"FINAL_CANDIDATE", "TEST_MORE", "REVISE"}
    assert result["max_allowed_claim_level"]["index"] <= 4
    assert result["short_for_llm"]["scientific_rule"] == "Do not present FINAL_CANDIDATE as a confirmed law/proof; obey max_allowed_claim_level."
