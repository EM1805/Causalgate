from __future__ import annotations

import csv
from pathlib import Path

from causalgate.causal_core.estimation import EstimationEngine
from causalgate.causal_core.identification import IdentificationEngine
from causalgate.gate import DecisionGate


def _write_real_panel(path: Path) -> None:
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
            # Deliberately simple synthetic panel: the true direct effect is
            # approximately +1.0 after adjusting for baseline_quality.
            outcome = 0.20 + 1.00 * treatment + 0.15 * confounder
            writer.writerow(
                {
                    "agent_action": treatment,
                    "task_success": outcome,
                    "baseline_quality": confounder,
                }
            )


def _real_payload(data_path: Path) -> dict:
    return {
        "request_id": "step86-real-e2e",
        "user_message": "Evaluate whether the agent action improves task success.",
        "candidate_action": "agent_action",
        "action_name": "agent_action",
        "action_type": "analysis_only",
        "treatment": "agent_action",
        "outcome": "task_success",
        "adjustment_set": ["baseline_quality"],
        "risk_level": "low",
        "reversibility": "reversible",
        "requires_tool": False,
        "scm_graph": {
            "nodes": ["agent_action", "task_success", "baseline_quality"],
            "edges": [
                ["baseline_quality", "agent_action"],
                ["baseline_quality", "task_success"],
                ["agent_action", "task_success"],
            ],
        },
        "estimation_query": {
            "data_path": str(data_path),
            "treatment": "agent_action",
            "outcome": "task_success",
            "adjustment_set": ["baseline_quality"],
            "bootstrap_b": 20,
        },
    }


def test_real_identification_and_estimation_engines_on_small_csv(tmp_path):
    """No stubs: direct adapter-to-backend smoke over a real synthetic CSV."""

    data_path = tmp_path / "real_panel.csv"
    _write_real_panel(data_path)

    payload = _real_payload(data_path)
    id_result = IdentificationEngine().identify(payload).to_dict()
    assert id_result["identified"] is True
    assert id_result["identification_tier"] == "identified_graphical"
    assert id_result["full_id_claim_allowed"] == 1
    assert "SCM_ID_IDENTIFIED" in id_result["reason_codes"]

    est_payload = dict(payload["estimation_query"])
    est_payload.update(
        {
            "identification_result": id_result,
            "identified": True,
            "allowed_for_estimation": True,
            "authority_level": "identified_estimable",
        }
    )
    est_result = EstimationEngine().estimate(est_payload).to_dict()
    assert est_result["estimation_status"] == "estimated_with_estimation_parts"
    assert est_result["causal_estimate_available"] is True
    assert est_result["estimated"] is True
    assert est_result["effect_estimate"] is not None
    assert 0.85 <= est_result["effect_estimate"] <= 1.15
    assert est_result["association_estimate_available"] is False


def test_decision_gate_real_engines_chain_id_into_estimation_without_stubs(tmp_path):
    """No injected fake engines: DecisionGate uses real IdentificationEngine and EstimationEngine."""

    data_path = tmp_path / "real_panel.csv"
    _write_real_panel(data_path)

    result = DecisionGate(
        enable_counterfactual=False,
        enable_risk_policy=False,
        enable_recommender=False,
    ).evaluate(_real_payload(data_path)).to_dict()

    assert result["causal_identification"]["identified"] is True
    assert result["causal_identification"]["identification_tier"] == "identified_graphical"
    assert result["causal_identification"]["full_id_claim_allowed"] == 1

    assert result["causal_estimation"]["estimation_status"] == "estimated_with_estimation_parts"
    assert result["causal_estimation"]["causal_estimate_available"] is True
    assert result["causal_estimation"]["estimated"] is True
    assert 0.85 <= result["causal_estimation"]["effect_estimate"] <= 1.15
    assert result["causal_estimation"]["authority_level"] == "identified_estimable"
    assert result["causal_estimation"]["identification_status"] == "identified_graphical"

    assert "SCM_ID_IDENTIFIED" in result["reason_codes"]
    assert "ESTIMATION_AVAILABLE" in result["reason_codes"]
    assert result["decision"] in {"allow", "warn", "abstain"}
