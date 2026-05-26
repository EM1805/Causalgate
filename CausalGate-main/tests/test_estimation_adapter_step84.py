import csv
from pathlib import Path

from causalgate.causal_core.estimation import EstimationEngine


def _write_linear_data(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["a", "y", "z"])
        writer.writeheader()
        for i in range(60):
            a = i % 2
            z = i / 60.0
            y = 1.0 * a + 0.1 * z
            writer.writerow({"a": a, "y": y, "z": z})


def test_estimation_adapter_keeps_plain_csv_diagnostic_only(tmp_path):
    path = tmp_path / "data.csv"
    _write_linear_data(path)
    result = EstimationEngine().estimate({
        "treatment": "a",
        "outcome": "y",
        "data_path": str(path),
    }).to_dict()
    assert result["estimated"] is False
    assert result["causal_estimate_available"] is False
    assert result["association_estimate_available"] is True
    assert result["estimation_status"] == "diagnostic_association_only"


def test_estimation_adapter_runs_backend_only_with_id_contract_authority(tmp_path):
    path = tmp_path / "data.csv"
    _write_linear_data(path)
    result = EstimationEngine().estimate({
        "treatment": "a",
        "outcome": "y",
        "data_path": str(path),
        "adjustment_set": ["z"],
        "identified": True,
        "allowed_for_estimation": True,
        "authority_level": "identified_estimable",
        "identification_strategy": "backdoor",
        "bootstrap_b": 20,
    }).to_dict()
    assert result["estimation_status"] == "estimated_with_estimation_parts"
    assert result["causal_estimate_available"] is True
    assert result["estimator_used"] == "lagged_backdoor_ols_bootstrap"
    assert result["effect_estimate"] is not None


def test_estimation_adapter_loads_effect_estimates_file(tmp_path):
    path = tmp_path / "effect_estimates.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "treatment", "outcome", "effect_estimate", "ci_low", "ci_high",
            "support_n", "estimator_used", "effect_claim_status", "reason_codes",
        ])
        writer.writeheader()
        writer.writerow({
            "treatment": "discount",
            "outcome": "conversion",
            "effect_estimate": "0.12",
            "ci_low": "0.03",
            "ci_high": "0.20",
            "support_n": "120",
            "estimator_used": "provided_effect",
            "effect_claim_status": "validated_effect",
            "reason_codes": "OK",
        })
    result = EstimationEngine().estimate({
        "treatment": "discount",
        "outcome": "conversion",
        "effect_estimates_path": str(path),
    }).to_dict()
    assert result["estimated"] is True
    assert result["effect_estimate"] == 0.12
    assert result["estimation_status"] == "loaded_effect_estimates_row"
