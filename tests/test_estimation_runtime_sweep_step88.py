from __future__ import annotations

import csv
from pathlib import Path

from causalgate.causal_core.estimation import EstimationEngine


def _write_panel(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["action", "outcome", "baseline"])
        writer.writeheader()
        for i in range(50):
            action = i % 2
            baseline = (i % 5) / 5.0
            outcome = 0.3 + 0.75 * action + 0.2 * baseline
            writer.writerow({"action": action, "outcome": outcome, "baseline": baseline})


def test_step88_authorized_estimation_is_dependency_light_and_contract_safe(tmp_path):
    path = tmp_path / "panel.csv"
    _write_panel(path)

    result = EstimationEngine().estimate({
        "treatment": "action",
        "outcome": "outcome",
        "data_path": str(path),
        "adjustment_set": ["baseline"],
        "identified": True,
        "allowed_for_estimation": True,
        "authority_level": "identified_estimable",
        "identification_status": "identified_graphical",
    }).to_dict()

    assert result["estimation_status"] == "estimated_with_estimation_parts"
    assert result["estimator_used"] == "lagged_backdoor_ols_bootstrap"
    assert result["causal_estimate_available"] is True
    assert 0.70 <= result["effect_estimate"] <= 0.80
    assert "ID_CONTRACT_AUTHORIZED_ESTIMATION" in result["reason_codes"]
    assert result["raw_estimation_result"]["backend"] == "adapter_pure_python_linear_effect"


def test_step88_same_csv_without_id_stays_diagnostic_only(tmp_path):
    path = tmp_path / "panel.csv"
    _write_panel(path)

    result = EstimationEngine().estimate({
        "treatment": "action",
        "outcome": "outcome",
        "data_path": str(path),
        "adjustment_set": ["baseline"],
    }).to_dict()

    assert result["estimated"] is False
    assert result["causal_estimate_available"] is False
    assert result["association_estimate_available"] is True
    assert "NO_ID_CONTRACT_AUTHORITY_FOR_CAUSAL_ESTIMATION" in result["reason_codes"]
