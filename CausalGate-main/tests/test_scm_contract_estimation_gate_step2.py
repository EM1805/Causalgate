import csv
from pathlib import Path

import pandas as pd


def test_estimation_plan_blocks_identified_needs_estimation_plan_only():
    from estimation_parts.handoff_reader import build_estimation_plan

    handoff = pd.DataFrame([
        {
            "insight_id": "q_needs",
            "source": "action_active",
            "target": "harm_event",
            "treatment_col": "action_active",
            "outcome_col": "harm_event",
            "authority_level": "identified_needs_estimation",
            "identification_status": "observed_dag_truncated_factorization",
            "identified": "1",
            "estimation_enabled": "0",
            "allowed_for_estimation": "0",
        }
    ])
    plan = build_estimation_plan(handoff)
    row = plan.iloc[0]
    assert row["estimation_status"] == "needs_estimator_or_data"
    assert row["allowed_for_estimation"] == "0"
    assert row["estimator_authority"] == "plan_only"


def test_effect_estimates_do_not_estimate_without_contract_allowed_flag():
    from estimation_parts.effect_estimates import build_effect_estimates

    data = pd.DataFrame({
        "action_active": [0, 1] * 20,
        "harm_event": [0.0, 1.0] * 20,
        "context_load": list(range(40)),
    })
    plan = pd.DataFrame([
        {
            "plan_id": "estimation_plan::q_blocked",
            "insight_id": "q_blocked",
            "source": "action_active",
            "target": "harm_event",
            "treatment_col": "action_active",
            "outcome_col": "harm_event",
            "authority_level": "identified_needs_estimation",
            "identification_status": "observed_dag_truncated_factorization",
            "identified": "1",
            "estimation_enabled": "0",
            "allowed_for_estimation": "0",
            "estimation_status": "needs_estimator_or_data",
            "adjustment_set": "context_load",
        }
    ])
    effects = build_effect_estimates(data, plan, bootstrap_b=20)
    row = effects.iloc[0]
    assert row["effect_claim_status"] == "not_estimated_contract_gate"
    assert row["effect_estimate"] == ""
    assert row["reason_codes"] == "NO_ESTIMATE_NOT_IDENTIFIED_ESTIMABLE"


def test_causal_contract_writes_allowed_for_estimation_zero_for_hard_block(tmp_path):
    from contracts.causal_contract import build_causal_contract

    out = tmp_path / "out"
    scm = out / "scm"
    scm.mkdir(parents=True)
    path = scm / "id_algorithm_audit.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "treatment", "outcome", "id_strategy", "identifiable",
            "possible_hedge", "hedge_status", "symbolic_formula_status",
            "id_algorithm_level", "reason_codes",
        ])
        writer.writeheader()
        writer.writerow({
            "treatment": "action_active",
            "outcome": "harm_event",
            "id_strategy": "blocked_possible_hedge",
            "identifiable": "0",
            "possible_hedge": "1",
            "hedge_status": "possible_hedge_detected",
            "symbolic_formula_status": "blocked_possible_hedge",
            "id_algorithm_level": "recursive_id",
            "reason_codes": "POSSIBLE_HEDGE",
        })
    rows, manifest = build_causal_contract(out_dir=str(out))
    assert len(rows) == 1
    assert rows[0]["authority_level"] == "blocked_id_algorithm"
    assert rows[0]["estimation_enabled"] == "0"
    assert rows[0]["allowed_for_estimation"] == "0"
