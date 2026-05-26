from causalgate.scientific import assess_falsification, normalize_scientific_hypothesis


def _complete_candidate():
    return {
        "hypothesis_id": "H_canonical_fields_1",
        "domain": "empirical_causal",
        "hypothesis_kind": "empirical_hypothesis",
        "domain_diagnostic": {"detected_domain": "empirical_causal", "domain_mismatch": False},
        "claim": "Tutoring may be associated with improved post-test scores after adjustment.",
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
        "confounders": ["PriorScore", "SES"],
        "adjustment_set": ["PriorScore", "SES"],
        "observed_confounder_measurements": {
            "PriorScore": "Measured at baseline using the pre-test score.",
            "SES": "Measured at baseline using household income and parent education.",
        },
        "assumptions": ["No unmeasured confounding after the stated adjustment set."],
        "mechanism_plausible": "Tutoring may increase practice time and targeted feedback.",
        "identification_strategy": "Back-door adjustment using PriorScore and SES.",
        "estimation_plan": "Estimate adjusted follow-up score differences with baseline score controls.",
        "counterfactual_query": "E[PostScore|do(TutoringProgram=1)] - E[PostScore|do(TutoringProgram=0)].",
        "measurable_predictions": ["After 12 weeks, tutored students will have higher measured post-test scores than comparable controls."],
        "falsification_tests": ["The adjusted association disappears or reverses in the target outcome."],
        "negative_control_tests": ["A prespecified unrelated outcome should show no adjusted association."],
        "placebo_tests": ["Future tutoring assignment should not predict earlier pre-test scores."],
        "sensitivity_checks": ["Run hidden-confounding robustness checks."],
        "data_requirements": ["Student-level treatment, outcome, PriorScore, and SES measured at baseline/follow-up."],
        "external_evidence_quality": {"status": "not_checked", "reason": "No external evidence supplied."},
        "test_plan": "Run adjusted regression and falsification checks before any stronger conclusion.",
    }


def test_normalize_preserves_canonical_metadata_fields():
    hyp = normalize_scientific_hypothesis(_complete_candidate())

    assert hyp.hypothesis_kind == "empirical_hypothesis"
    assert hyp.domain_diagnostic["detected_domain"] == "empirical_causal"
    assert hyp.mechanism_plausible.startswith("Tutoring may")
    assert hyp.observed_confounder_measurements["PriorScore"].startswith("Measured")
    assert hyp.estimation_plan.startswith("Estimate adjusted")
    assert hyp.counterfactual_query.startswith("E[PostScore")
    assert hyp.external_evidence_quality["status"] == "not_checked"


def test_observed_confounder_measurements_satisfy_falsification_policy():
    assessment = assess_falsification(_complete_candidate())

    assert "CONFOUNDER_OBSERVATION_NOT_SPECIFIED" not in assessment["reason_codes"]
    assert "observed_confounder_measurements" not in assessment["missing_items"]
    assert assessment["audit_payload"]["observed_confounder_measurements"]["SES"].startswith("Measured")
