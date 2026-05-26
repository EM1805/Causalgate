from __future__ import annotations

import csv
from pathlib import Path

from causalgate.causal_core.estimation import EstimationEngine
from causalgate.gate import DecisionGate


def _write_correlated_panel(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["agent_action", "task_success", "baseline_quality"],
        )
        writer.writeheader()
        for i in range(80):
            treatment = i % 2
            confounder = (i % 10) / 10.0
            # Strong association on purpose. The negative tests verify that a
            # strong CSV signal is still not promoted to a causal estimate
            # without ID/contract authority.
            outcome = 0.20 + 1.25 * treatment + 0.40 * confounder
            writer.writerow(
                {
                    "agent_action": treatment,
                    "task_success": outcome,
                    "baseline_quality": confounder,
                }
            )


def _base_payload(data_path: Path) -> dict:
    return {
        "request_id": "step87-negative-e2e",
        "user_message": "Check whether the action improves task success.",
        "candidate_action": "agent_action",
        "action_name": "agent_action",
        "action_type": "analysis_only",
        "treatment": "agent_action",
        "outcome": "task_success",
        "adjustment_set": ["baseline_quality"],
        "risk_level": "low",
        "reversibility": "reversible",
        "requires_tool": False,
        "estimation_query": {
            "data_path": str(data_path),
            "treatment": "agent_action",
            "outcome": "task_success",
            "adjustment_set": ["baseline_quality"],
            "bootstrap_b": 20,
        },
    }


def test_plain_csv_without_id_contract_remains_diagnostic_only(tmp_path):
    data_path = tmp_path / "correlated_panel.csv"
    _write_correlated_panel(data_path)

    result = EstimationEngine().estimate(
        {
            "data_path": str(data_path),
            "treatment": "agent_action",
            "outcome": "task_success",
            "adjustment_set": ["baseline_quality"],
        }
    ).to_dict()

    assert result["estimated"] is False
    assert result["causal_estimate_available"] is False
    assert result["association_estimate_available"] is True
    assert result["allowed_for_decision"] is False
    assert result["effect_estimate"] is None
    assert result["association_estimate"] is not None
    assert result["estimation_status"] == "diagnostic_association_only"
    assert "NON_CAUSAL_DIAGNOSTIC_ASSOCIATION" in result["reason_codes"]
    assert "NO_ID_CONTRACT_AUTHORITY_FOR_CAUSAL_ESTIMATION" in result["reason_codes"]


def test_decision_gate_without_graph_does_not_upgrade_csv_to_causal_claim(tmp_path):
    data_path = tmp_path / "correlated_panel.csv"
    _write_correlated_panel(data_path)

    payload = _base_payload(data_path)
    # No scm_graph / causal_query is supplied, so the gate must not invent ID.
    result = DecisionGate(
        enable_counterfactual=False,
        enable_risk_policy=False,
        enable_recommender=False,
    ).evaluate(payload).to_dict()

    assert not result.get("causal_identification")
    assert "SCM_ID_IDENTIFIED" not in result["reason_codes"]

    estimation = result["causal_estimation"]
    assert estimation["estimated"] is False
    assert estimation["causal_estimate_available"] is False
    assert estimation["association_estimate_available"] is True
    assert estimation["allowed_for_decision"] is False
    assert estimation["effect_estimate"] is None
    assert estimation["estimation_status"] == "diagnostic_association_only"
    assert "NO_ID_CONTRACT_AUTHORITY_FOR_CAUSAL_ESTIMATION" in estimation["reason_codes"]
    assert "DIAGNOSTIC_ASSOCIATION_AVAILABLE" in result["reason_codes"]
    assert "ESTIMATION_UNAVAILABLE" in result["reason_codes"]


def test_decision_gate_failed_id_does_not_authorize_backend_estimation(tmp_path):
    data_path = tmp_path / "correlated_panel.csv"
    _write_correlated_panel(data_path)

    payload = _base_payload(data_path)
    payload["scm_graph"] = {
        "nodes": ["unrelated_action", "unrelated_outcome"],
        "edges": [["unrelated_action", "unrelated_outcome"]],
    }

    result = DecisionGate(
        enable_counterfactual=False,
        enable_risk_policy=False,
        enable_recommender=False,
    ).evaluate(payload).to_dict()

    identification = result["causal_identification"]
    assert identification["identified"] is False
    assert identification["identification_tier"] == "unidentified"
    assert "QUERY_NODE_NOT_IN_GRAPH" in identification["reason_codes"]
    assert "SCM_ID_UNIDENTIFIED" in result["reason_codes"]
    assert "SCM_ID_IDENTIFIED" not in result["reason_codes"]

    estimation = result["causal_estimation"]
    assert estimation["estimated"] is False
    assert estimation["causal_estimate_available"] is False
    assert estimation["association_estimate_available"] is True
    assert estimation["allowed_for_decision"] is False
    assert estimation["authority_level"] != "identified_estimable"
    assert "NO_ID_CONTRACT_AUTHORITY_FOR_CAUSAL_ESTIMATION" in estimation["reason_codes"]
    assert "DIAGNOSTIC_ASSOCIATION_AVAILABLE" in result["reason_codes"]
    assert "ESTIMATION_UNAVAILABLE" in result["reason_codes"]
