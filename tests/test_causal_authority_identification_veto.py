"""Protocol Genesis: falsify score-only authority under missing identification."""
from causalgate import CausalEvidence, score_causal_authority

STRONG = {
    "identified": True,
    "identification_status": "identified",
    "estimand_type": "total_effect",
    "effect_estimated": True,
    "estimate": 0.18,
    "confidence_interval": [0.09, 0.27],
    "confidence": "high",
    "diagnostics_passed": 5,
    "diagnostics_total": 6,
    "sensitivity_risk": "low",
    "hidden_confounding_risk": "low",
    "sample_size": 1460,
    "scm_available": True,
    "discovery_graph_available": True,
    "placebo_passed": True,
    "negative_controls_passed": True,
    "stability_score": 0.86,
}


def test_positive_control_strong_identified_evidence_passes():
    result = score_causal_authority(STRONG, risk_level="high")
    assert result.authority_score >= 80
    assert result.authority_decision == "PASS"


def test_missing_identification_cannot_be_compensated_by_score():
    data = {**STRONG, "identified": False, "identification_status": "not_identified"}
    for risk_level in ("low", "medium", "high", "critical"):
        result = score_causal_authority(data, risk_level=risk_level)
        assert result.authority_score >= 70  # This is why a veto is required.
        assert result.authority_decision == "HARD_BLOCK"
        assert result.authority_level == "unidentified"
        assert result.required_next_steps


def test_contradictory_identification_fields_fail_closed():
    for identified, status in (
        (False, "identified"), (True, "failed"), (True, "unidentified"),
        (False, "success"), (False, "not_identified")
    ):
        data = {**STRONG, "identified": identified, "identification_status": status}
        evidence = CausalEvidence.from_mapping(data)
        assert evidence.identified is False, (identified, status)
        assert score_causal_authority(data, risk_level="high").authority_decision == "HARD_BLOCK"


def test_legacy_status_only_identification_still_supported():
    data = dict(STRONG)
    data.pop("identified")
    data["identification_status"] = "identified"
    ev = CausalEvidence.from_mapping(data)
    assert ev.identified is True
    assert score_causal_authority(data, risk_level="high").authority_decision == "PASS"


def test_explicit_informational_mode_preserved():
    data = {**STRONG, "identified": False, "identification_status": "not_identified"}
    result = score_causal_authority(data, risk_level="low", require_evidence=False)
    assert result.authority_score >= 70
    assert result.authority_decision == "PASS"
