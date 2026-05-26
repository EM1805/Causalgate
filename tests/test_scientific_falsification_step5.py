from __future__ import annotations

from pathlib import Path

from causalgate.scientific import (
    assess_falsification,
    evaluate_hypothesis,
    infer_evidence_requirements,
)
from causalgate.mcp.tools import call_tool, list_tools


def _valid_step5_hypothesis():
    return {
        "hypothesis_id": "hyp_step5_valid",
        "claim": "X may causally influence Y through M, controlling for Z.",
        "claim_level": "hypothesis_only",
        "variables": {
            "treatment": "X",
            "outcome": "Y",
            "mediators": ["M"],
            "confounders": ["Z"],
        },
        "dag": {"edges": [["Z", "X"], ["Z", "Y"], ["X", "M"], ["M", "Y"]]},
        "assumptions": ["Z is observed", "X occurs before Y", "no interference"],
        "adjustment_set": ["Z"],
        "measurable_predictions": [
            "If X increases, Y should increase within a 7-day lag after controlling for Z."
        ],
        "falsification_tests": [
            "negative control outcome",
            "future-X placebo temporal leakage test",
            "hidden confounding sensitivity check",
        ],
        "negative_controls": ["Outcome N should not change when X changes."],
        "placebo_tests": ["future-X should not predict past-Y."],
        "sensitivity_checks": ["hidden confounding sensitivity check"],
        "data_requirements": ["time ordered data", "observed X, M, Y, and Z", "7-day window"],
        "test_plan": "Estimate X->Y controlling for Z and compare with negative control and future-X placebo.",
    }


def test_falsification_gate_accepts_only_testable_candidate():
    result = evaluate_hypothesis(_valid_step5_hypothesis(), enable_identification=False)

    assert result["decision"] == "FINAL_CANDIDATE"
    assert result["claim_level"] == "testable_candidate"
    assert result["falsifiability_status"] == "testable"
    assert result["evidence_status"] == "ready_for_external_validation"
    assert result["short_for_llm"]["scientific_rule"]


def test_falsification_gate_revises_missing_measurable_prediction():
    weak = _valid_step5_hypothesis()
    weak.pop("measurable_predictions")

    result = evaluate_hypothesis(weak, enable_identification=False)

    assert result["decision"] == "REVISE"
    assert "MISSING_MEASURABLE_PREDICTION" in result["reason_codes"]
    assert "measurable_prediction" in result["missing_items"]


def test_falsification_gate_revises_missing_adjustment_set_for_confounding():
    weak = _valid_step5_hypothesis()
    weak.pop("adjustment_set")

    result = evaluate_hypothesis(weak, enable_identification=False)

    assert result["decision"] == "REVISE"
    assert "MISSING_ADJUSTMENT_SET_FOR_CONFOUNDING" in result["reason_codes"]
    assert "adjustment_set" in result["missing_items"]


def test_falsification_assessment_and_evidence_requirements():
    assessment = assess_falsification(_valid_step5_hypothesis())
    assert assessment["decision_hint"] == "FINAL_CANDIDATE"
    assert assessment["falsifiability_status"] == "testable"

    evidence = infer_evidence_requirements(_valid_step5_hypothesis())
    assert "measure treatment/cause variable: X" in evidence["required_observations"]
    assert "measure and adjust for confounder: Z" in evidence["required_controls"]


def test_mcp_exposes_step5_tools():
    names = [tool["name"] for tool in list_tools()["tools"]]
    assert "causalgate_assess_falsification" in names
    assert "causalgate_infer_evidence_requirements" in names

    assessment = call_tool("causalgate_assess_falsification", {"hypothesis": _valid_step5_hypothesis()})
    assert assessment["decision_hint"] == "FINAL_CANDIDATE"

    evidence = call_tool("causalgate_infer_evidence_requirements", {"hypothesis": _valid_step5_hypothesis()})
    assert evidence["required_validation_tests"]
