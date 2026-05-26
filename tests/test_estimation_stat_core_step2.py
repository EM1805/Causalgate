import numpy as np
import pandas as pd

from estimation_parts import effect_estimates as EE
from estimation_parts import stat_core as SC


def test_stat_core_linear_treatment_effect_smoke():
    rng = np.random.default_rng(42)
    n = 80
    a = rng.normal(size=n)
    z = rng.normal(size=(n, 1))
    y = 2.0 * a + 0.4 * z[:, 0] + rng.normal(scale=0.05, size=n)

    result = SC.linear_treatment_effect(a, y, z)

    assert result.status == "ok"
    assert result.n == n
    assert abs(result.effect - 2.0) < 0.15


def test_effect_estimates_uses_stat_core_path_smoke():
    rng = np.random.default_rng(7)
    n = 90
    treatment = rng.normal(size=n)
    covariate = rng.normal(size=n)
    outcome = 1.25 * pd.Series(treatment).shift(1).fillna(0).to_numpy() + 0.2 * covariate + rng.normal(scale=0.05, size=n)
    data = pd.DataFrame({"treatment": treatment, "covariate": covariate, "outcome": outcome})
    plan = pd.DataFrame([
        {
            "plan_id": "plan::1",
            "insight_id": "insight::1",
            "source": "treatment",
            "target": "outcome",
            "treatment_col": "treatment",
            "outcome_col": "outcome",
            "lag": 1,
            "candidate_adjustment_set": "covariate",
            "adjustment_set": "covariate",
            "estimand_type": "ATE",
            "authority_level": "identified_estimable",
            "identification_status": "identified",
            "estimation_status": "can_estimate_now",
            "estimation_enabled": "1",
            "allowed_for_estimation": "1",
            "identified": "1",
            "sensitivity_status": "",
        }
    ])

    effects = EE.build_effect_estimates(data, plan, bootstrap_b=20)

    assert len(effects) == 1
    row = effects.iloc[0]
    assert row["effect_claim_status"] == "diagnostic_effect_estimate"
    assert int(row["support_n"]) >= 80
    assert abs(float(row["effect_estimate"]) - 1.25) < 0.2
    assert row["used_adjustment_set"] == "covariate"
