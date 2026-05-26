import csv
from pathlib import Path

from causalgate.causal_core.estimation import EstimationEngine
from causalgate.gate import DecisionGate


def _write_data(path: Path):
    rows = [
        {"action_active": 1, "task_success": 1.0},
        {"action_active": 1, "task_success": 0.9},
        {"action_active": 1, "task_success": 0.8},
        {"action_active": 1, "task_success": 1.0},
        {"action_active": 1, "task_success": 0.7},
        {"action_active": 0, "task_success": 0.4},
        {"action_active": 0, "task_success": 0.5},
        {"action_active": 0, "task_success": 0.3},
        {"action_active": 0, "task_success": 0.6},
        {"action_active": 0, "task_success": 0.4},
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["action_active", "task_success"])
        writer.writeheader()
        writer.writerows(rows)


def test_estimation_adapter_stdlib_csv_difference(tmp_path):
    data_path = tmp_path / "data.csv"
    _write_data(data_path)
    result = EstimationEngine().estimate({
        "treatment": "action_active",
        "outcome": "task_success",
        "data_path": str(data_path),
    }).to_dict()
    assert result["estimated"] is False
    assert result["causal_estimate_available"] is False
    assert result["association_estimate_available"] is True
    assert result["estimate_type"] == "diagnostic_association"
    assert result["allowed_for_decision"] is False
    assert result["estimator_used"] == "csv_difference_in_means"
    assert round(result["association_estimate"], 2) == 0.44
    assert result["effect_estimate"] is None
    assert "NON_CAUSAL_DIAGNOSTIC_ASSOCIATION" in result["reason_codes"]
    assert result["treated_n"] == 5
    assert result["control_n"] == 5


def test_estimation_adapter_manual_effect():
    result = EstimationEngine().estimate({
        "effect_estimate": 0.17,
        "ci_low": 0.05,
        "ci_high": 0.28,
        "robustness_status": "medium",
    }).to_dict()
    assert result["estimated"] is True
    assert result["estimation_status"] == "loaded_manual_effect"
    assert result["effect_estimate"] == 0.17


def test_decision_gate_enriches_with_estimation(tmp_path):
    data_path = tmp_path / "data.csv"
    _write_data(data_path)
    payload = {
        "candidate_action": "answer_directly",
        "action_name": "answer_directly",
        "action_type": "communication",
        "target_resource": "conversation",
        "environment": "development",
        "risk_level": "low",
        "estimation_query": {
            "treatment": "action_active",
            "outcome": "task_success",
            "data_path": str(data_path),
        },
    }
    result = DecisionGate(enable_identification=False).evaluate(payload).to_dict()
    assert result["decision"] == "allow"
    assert result["causal_estimation"]["estimated"] is False
    assert result["causal_estimation"]["association_estimate_available"] is True
    assert "DIAGNOSTIC_ASSOCIATION_AVAILABLE" in result["reason_codes"]
    assert "ESTIMATION_AVAILABLE" not in result["reason_codes"]
