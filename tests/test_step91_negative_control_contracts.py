from causalgate.scientific import normalize_scientific_hypothesis
from causalgate.scientific.falsification_policy import FalsificationPolicy


def _node_ids(hyp):
    return {n.get("id") or n.get("node_id") for n in hyp.dag.get("nodes", [])}


def test_legacy_negative_control_sentence_is_not_dag_node():
    sentence = "N should not change when X changes."
    hyp = normalize_scientific_hypothesis(
        {
            "claim": "X may change Y under stated assumptions.",
            "treatment": "X",
            "outcome": "Y",
            "dag": {"edges": [["X", "Y"]]},
            "negative_controls": ["N", sentence],
        }
    )

    nodes = _node_ids(hyp)
    assert "X" in nodes
    assert "Y" in nodes
    assert "N" in nodes
    assert sentence not in nodes
    assert hyp.negative_controls == ["N"]
    assert hyp.negative_control_variables == ["N"]
    assert hyp.negative_control_tests == [sentence]


def test_explicit_negative_control_variables_and_tests_are_separated():
    hyp = normalize_scientific_hypothesis(
        {
            "claim": "X may change Y under stated assumptions.",
            "treatment": "X",
            "outcome": "Y",
            "dag": {"edges": [["X", "Y"]]},
            "negative_control_variables": ["N_outcome"],
            "negative_control_tests": ["N_outcome should remain unchanged after X."],
        }
    )

    nodes = _node_ids(hyp)
    assert "N_outcome" in nodes
    assert "N_outcome should remain unchanged after X." not in nodes
    assert hyp.negative_controls == ["N_outcome"]
    assert hyp.negative_control_variables == ["N_outcome"]
    assert hyp.negative_control_tests == ["N_outcome should remain unchanged after X."]


def test_falsification_policy_counts_negative_control_test_descriptions():
    hyp = normalize_scientific_hypothesis(
        {
            "claim": "X may increase Y in the next 7 days.",
            "treatment": "X",
            "outcome": "Y",
            "dag": {"edges": [["X", "Y"]]},
            "assumptions": ["No hidden confounding for this first-pass candidate."],
            "falsification_tests": ["future-X placebo leakage test"],
            "negative_controls": ["N should not change when X changes."],
            "placebo_tests": ["future-X placebo leakage test"],
            "sensitivity_checks": ["hidden-confounding sensitivity check"],
            "measurable_predictions": ["Y increases by at least 2% within 7 days after X."],
            "data_requirements": ["daily measurements of X, Y, and N for 90 days"],
            "test_plan": "Run placebo, negative-control, and sensitivity checks.",
        }
    )
    assessment = FalsificationPolicy().assess(hyp).to_dict()

    assert assessment["audit_payload"]["has_negative_control"] is True
    assert "MISSING_NEGATIVE_CONTROL" not in assessment["reason_codes"]
    assert assessment["audit_payload"]["negative_control_variables"] == []
    assert assessment["audit_payload"]["negative_control_tests"] == ["N should not change when X changes."]
