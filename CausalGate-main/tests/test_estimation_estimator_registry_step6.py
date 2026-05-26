from __future__ import annotations

import numpy as np
import pandas as pd

from estimation_parts import estimator_registry as ER
from estimation_parts import effect_estimates as EE


def _identified_row(**overrides):
    row = {
        "plan_id": "p1",
        "insight_id": "i1",
        "source": "a",
        "target": "y",
        "treatment_col": "a",
        "outcome_col": "y",
        "lag": "0",
        "authority_level": "identified_estimable",
        "estimation_enabled": "1",
        "allowed_for_estimation": "1",
        "identified": "1",
        "identification_status": "identified",
        "estimation_status": "can_estimate_now",
        "identification_strategy": "backdoor",
        "adjustment_set_status": "valid_empty",
        "recommended_estimator": "backdoor_ridge_adjustment",
    }
    row.update(overrides)
    return pd.Series(row)


def test_effect_estimates_resolves_backdoor_registry_alias_to_compact_estimator():
    row = _identified_row()
    estimator, reason = ER.resolve_effect_estimator_for_row(row.to_dict())
    assert estimator == "lagged_backdoor_ols_bootstrap"
    assert reason == "OK_BACKDOOR_COMPACT_EFFECT_ESTIMATOR"


def test_effect_estimates_uses_registry_resolved_estimator():
    rng = np.random.default_rng(7)
    n = 80
    a = rng.normal(size=n)
    y = 1.5 * a + rng.normal(scale=0.2, size=n)
    df = pd.DataFrame({"a": a, "y": y})
    out = EE.estimate_plan_row(df, _identified_row(), bootstrap_b=30)
    assert out["estimator_used"] == "lagged_backdoor_ols_bootstrap"
    assert out["effect_claim_status"] in {
        "diagnostic_effect_estimate",
        "estimated_but_sensitivity_required",
        "estimated_but_uncertain_ci_crosses_zero",
    }


def test_effect_estimates_blocks_non_runnable_registry_estimator():
    df = pd.DataFrame({"a": range(40), "y": range(40)})
    row = _identified_row(
        recommended_estimator="frontdoor_limited_estimator",
        identification_strategy="frontdoor",
    )
    out = EE.estimate_plan_row(df, row, bootstrap_b=20)
    assert out["effect_claim_status"] == "identified_but_unestimated"
    assert "ESTIMATOR_STATUS_NOT_RUNNABLE" in out["reason_codes"]
