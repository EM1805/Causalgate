from __future__ import annotations

import math

import numpy as np
import pandas as pd

from estimation_parts import stat_core as SC
from estimation_parts import placebo, negative_controls, pearl_backdoor


def test_stat_core_normal_approx_p_from_t():
    assert 0.0 <= SC.normal_approx_p_from_t(0.0) <= 1.0
    assert SC.normal_approx_p_from_t(3.0) < SC.normal_approx_p_from_t(1.0)
    assert math.isnan(SC.normal_approx_p_from_t(float("nan")))


def test_placebo_and_negative_controls_share_stat_core_smoke():
    n = 80
    df = pd.DataFrame({
        "a": [0, 1] * 40,
        "y": np.linspace(0, 1, n),
        "negative_control_outcome": np.random.default_rng(1).normal(0, 1, n),
        "z": np.linspace(1, 2, n),
    })
    row = pd.Series({"source": "a", "target": "y", "treatment_col": "a", "outcome_col": "y", "lag": 0})
    pb = placebo.evaluate_future_placebo(df, row, main_effect=1.0, used_covariates=["z"])
    nc = negative_controls.evaluate_negative_control(df, row, main_effect=1.0, used_covariates=["z"])
    assert "placebo_status" in pb
    assert "negative_control_status" in nc


def test_pearl_backdoor_uses_authorized_contract_smoke():
    n = 60
    df = pd.DataFrame({
        "a": [0, 1] * 30,
        "y": np.array([0, 1] * 30, dtype=float) + np.random.default_rng(2).normal(0, 0.01, n),
        "z": np.linspace(0, 1, n),
    })
    row = pd.Series({
        "insight_id": "a_to_y",
        "treatment_col": "a",
        "outcome_col": "y",
        "authority_level": "identified_estimable",
        "estimation_enabled": "true",
        "identified": 1,
        "identification_strategy": "backdoor",
        "adjustment_set_status": "valid_nonempty",
        "adjustment_set": "z",
    })
    out = pearl_backdoor.estimate_backdoor_effect(df, row, bootstrap_b=20)
    assert out["causal_claim_status"] == "identified_estimated_backdoor"
    assert np.isfinite(float(out["effect_estimate"]))
