from __future__ import annotations

import pandas as pd

from estimation_parts import estimator_registry as ER
from estimation_parts import handoff_reader as HR


def test_estimator_registry_catalog_has_core_estimators():
    names = set(ER.estimator_names())
    assert "backdoor_ridge_adjustment" in names
    assert "lagged_backdoor_ols_bootstrap" in names
    assert "diagnostic_lagged_regression_only" in names
    assert ER.is_estimator_decision_safe("backdoor_ridge_adjustment") is True
    assert ER.is_estimator_diagnostic_only("diagnostic_lagged_regression_only") is True


def test_registry_selects_backdoor_for_identified_estimable_row():
    row = {
        "authority_level": "identified_estimable",
        "estimation_enabled": "true",
        "allowed_for_estimation": "true",
        "identified": "true",
        "identification_strategy": "backdoor",
        "adjustment_set_status": "valid_nonempty",
        "adjustment_set": "z1,z2",
    }
    estimator, authority = ER.select_estimator_for_row(row)
    assert estimator == "backdoor_ridge_adjustment"
    assert authority == "formal_identification_required"
    ok, reason = ER.validate_estimator_for_row(estimator, row)
    assert ok is True
    assert reason == "OK"


def test_registry_keeps_discovery_only_rows_diagnostic_or_skipped():
    row = {
        "authority_level": "raw_discovery_only",
        "estimation_enabled": "false",
        "identified": "false",
        "scm_role_hint": "temporal_parent_candidate",
        "mci_status": "diagnostic_support",
    }
    estimator, authority = ER.select_estimator_for_row(row)
    assert estimator == "diagnostic_lagged_regression_only"
    assert authority == "diagnostic_only"
    assert ER.is_estimator_decision_safe(estimator) is False


def test_handoff_reader_uses_registry_selection():
    handoff = pd.DataFrame([
        {
            "insight_id": "i1",
            "source": "a",
            "target": "y",
            "treatment_col": "a",
            "outcome_col": "y",
            "authority_level": "identified_estimable",
            "estimation_enabled": "1",
            "allowed_for_estimation": "1",
            "identified": "1",
            "identification_strategy": "backdoor",
            "adjustment_set_status": "valid_empty",
        }
    ])
    plan = HR.build_estimation_plan(handoff)
    assert len(plan) == 1
    assert plan.loc[0, "recommended_estimator"] == "backdoor_ridge_adjustment"
    assert plan.loc[0, "estimator_authority"] == "formal_identification_required"
