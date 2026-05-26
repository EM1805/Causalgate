from __future__ import annotations

import csv
import json
from pathlib import Path


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_causal_report_is_query_ledger_for_estimated_and_blocked_rows(tmp_path):
    from contracts.causal_report import write_causal_report

    out = tmp_path / "out"
    _write_csv(
        out / "causal_contract.csv",
        [
            "insight_id", "source", "target", "treatment_col", "outcome_col", "lag",
            "authority_level", "identification_status", "identified",
            "estimation_enabled", "allowed_for_estimation",
        ],
        [
            {
                "insight_id": "q_estimated",
                "source": "action_active",
                "target": "harm_event",
                "treatment_col": "action_active",
                "outcome_col": "harm_event",
                "lag": "0",
                "authority_level": "identified_estimable",
                "identification_status": "backdoor_identified",
                "identified": "1",
                "estimation_enabled": "1",
                "allowed_for_estimation": "1",
            },
            {
                "insight_id": "q_blocked",
                "source": "tool_call_rate",
                "target": "harm_event",
                "treatment_col": "tool_call_rate",
                "outcome_col": "harm_event",
                "lag": "1",
                "authority_level": "blocked_id_algorithm",
                "identification_status": "not_identified",
                "identified": "0",
                "estimation_enabled": "0",
                "allowed_for_estimation": "0",
            },
        ],
    )
    _write_csv(
        out / "estimation" / "estimation_plan.csv",
        [
            "plan_id", "insight_id", "source", "target", "treatment_col", "outcome_col", "lag",
            "authority_level", "identification_status", "identified", "estimation_enabled",
            "allowed_for_estimation", "estimation_status", "recommended_estimator", "reason",
        ],
        [
            {
                "plan_id": "estimation_plan::q_estimated",
                "insight_id": "q_estimated",
                "source": "action_active",
                "target": "harm_event",
                "treatment_col": "action_active",
                "outcome_col": "harm_event",
                "lag": "0",
                "authority_level": "identified_estimable",
                "identification_status": "backdoor_identified",
                "identified": "1",
                "estimation_enabled": "1",
                "allowed_for_estimation": "1",
                "estimation_status": "can_estimate_now",
                "recommended_estimator": "backdoor_ridge_adjustment",
                "reason": "",
            },
            {
                "plan_id": "estimation_plan::q_blocked",
                "insight_id": "q_blocked",
                "source": "tool_call_rate",
                "target": "harm_event",
                "treatment_col": "tool_call_rate",
                "outcome_col": "harm_event",
                "lag": "1",
                "authority_level": "blocked_id_algorithm",
                "identification_status": "not_identified",
                "identified": "0",
                "estimation_enabled": "0",
                "allowed_for_estimation": "0",
                "estimation_status": "blocked",
                "recommended_estimator": "skip",
                "reason": "causal_query_not_identified_by_scm_id",
            },
        ],
    )
    _write_csv(
        out / "estimation" / "effect_estimates.csv",
        [
            "effect_id", "plan_id", "insight_id", "source", "target", "treatment_col",
            "outcome_col", "lag", "effect_claim_status", "effect_estimate",
            "ci_low", "ci_high", "authority_level", "identification_status",
            "estimation_status", "reason_codes",
        ],
        [
            {
                "effect_id": "effect::q_estimated",
                "plan_id": "estimation_plan::q_estimated",
                "insight_id": "q_estimated",
                "source": "action_active",
                "target": "harm_event",
                "treatment_col": "action_active",
                "outcome_col": "harm_event",
                "lag": "0",
                "effect_claim_status": "diagnostic_effect_estimate",
                "effect_estimate": "0.42",
                "ci_low": "0.1",
                "ci_high": "0.7",
                "authority_level": "identified_estimable",
                "identification_status": "backdoor_identified",
                "estimation_status": "can_estimate_now",
                "reason_codes": "",
            },
            {
                "effect_id": "effect::q_blocked",
                "plan_id": "estimation_plan::q_blocked",
                "insight_id": "q_blocked",
                "source": "tool_call_rate",
                "target": "harm_event",
                "treatment_col": "tool_call_rate",
                "outcome_col": "harm_event",
                "lag": "1",
                "effect_claim_status": "not_estimated_contract_gate",
                "effect_estimate": "",
                "ci_low": "",
                "ci_high": "",
                "authority_level": "blocked_id_algorithm",
                "identification_status": "not_identified",
                "estimation_status": "blocked",
                "reason_codes": "NO_ESTIMATE_ID_NOT_IDENTIFIED",
            },
        ],
    )

    paths = write_causal_report(out_dir=str(out))
    report_rows = list(csv.DictReader(open(paths["causal_report_csv"], encoding="utf-8")))
    by_id = {row["insight_id"]: row for row in report_rows}

    assert by_id["q_estimated"]["query_status"] == "estimated"
    assert by_id["q_estimated"]["estimated"] == "1"
    assert by_id["q_estimated"]["id_gate_status"] == "identified"
    assert by_id["q_blocked"]["query_status"] == "blocked"
    assert by_id["q_blocked"]["estimated"] == "0"
    assert by_id["q_blocked"]["id_gate_status"] == "blocked_not_identified"
    assert by_id["q_blocked"]["estimation_gate_status"] == "blocked_by_contract_gate"

    manifest = json.loads(Path(paths["causal_report_manifest_json"]).read_text(encoding="utf-8"))
    assert manifest["n_numeric_estimates"] == 1
    assert manifest["query_status_counts"]["estimated"] == 1
    assert manifest["query_status_counts"]["blocked"] == 1
