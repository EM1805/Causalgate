from __future__ import annotations

from runtime_env import configure_scientific_runtime
configure_scientific_runtime()


import argparse
import json
import math
import os
import re
import sys
from itertools import combinations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from runtime_compat import assert_scientific_stack
assert_scientific_stack()


from .config import ProposalConfig
from . import calibration as CAL
from .utils import (
    OfflinePriorGraph,
    _action_family,
    _as_str,
    _best_lag_metrics,
    _clip01,
    _corr,
    _adjusted_effect_metrics,
    _ensure_out,
    _feature_family,
    _future_leakage_score,
    _is_intervenible,
    _is_sensitive,
    _mechanism_hint,
    _norm_abs,
    _regime_awareness_metrics,
    _rolling_stability,
    _safe_float,
    _temporal_conditional_signal,
    _residual_competition_signal,
    _edge_orientation_signal,
    _conditional_independence_signal,
    _mci_signal,
    _residualize,
)


def _parent_spec(source: str, lag: int) -> str:
    """Return the canonical lag-aware parent spec used by PC1 and MCI."""
    source = _as_str(source)
    lag = max(1, int(lag))
    return f"{source}__lag{lag}"


def _parse_parent_spec(spec: str) -> tuple[str, int]:
    """Parse canonical parent specs like ``x__lag2`` into (name, lag)."""
    raw = _as_str(spec)
    if not raw:
        return "", 0
    if "__lag" not in raw:
        return raw, 0
    base, _, lag_s = raw.rpartition("__lag")
    try:
        return base, max(0, int(float(lag_s)))
    except (TypeError, ValueError, OverflowError):
        return raw, 0


def _lagged_control_array(values: np.ndarray, lag: int) -> np.ndarray:
    """Shift a vector so column(t-lag) can be used as a conditioning control."""
    lag = max(0, int(lag))
    arr = np.asarray(values, dtype=float)
    if lag <= 0:
        return arr.copy()
    out = np.full_like(arr, np.nan, dtype=float)
    if len(arr) > lag:
        out[lag:] = arr[:-lag]
    return out


def _parent_spec_to_control(spec: str, df: pd.DataFrame) -> tuple[np.ndarray | None, str]:
    """Convert a parent spec into a lagged control array and canonical label."""
    name, lag = _parse_parent_spec(spec)
    if not name or name not in df.columns:
        return None, ""
    arr = pd.to_numeric(df[name], errors="coerce").to_numpy(dtype=float)
    label = _parent_spec(name, lag) if lag > 0 else name
    return _lagged_control_array(arr, lag), label


@dataclass
class DiscoveryContext:
    """Stateless discovery context.

    The former estimation-to-discovery feedback memory loop was removed in
    0.2.21. Discovery is now deterministic from data + config only.
    """
    metadata: Dict[str, Any] | None = None


@dataclass
class SourceMetrics:
    source: str
    lag: int
    corr: float
    delta: float
    stability: float
    stability_windows: int
    relation_sign: float
    lag_meta: Dict[str, float]
    regime: Dict[str, float]
    testability_score: float
    test_meta: Dict[str, float]
    causal_plausibility: float
    intervention_value: float
    downside_action_score: float
    validation_readiness: float
    structural_risk_score: float
    safety_scores: Dict[str, float | str]
    design: Dict[str, object]
    action_name: str
    action_type: str
    expected_direction_num: int
    expected_direction_label: str
    downside_mechanism: str
    dag_ann: Dict[str, object]
    supporting: str
    confound_hint: str
    adjusted_confounders: List[str]
    adjusted_corr: float
    adjusted_delta: float
    attenuation_ratio: float
    confounding_risk_score: float
    adjusted_support: int
    causal_effect: float
    causal_effect_std: float
    causal_effect_ci_low: float
    causal_effect_ci_high: float
    effect_persistence_score: float
    ci_signal_score: float
    ci_raw_strength: float
    ci_adjusted_strength: float
    parent_competition_score: float
    parent_competition_pass: int
    causal_screen_score: float
    incremental_r2: float
    conditional_beta: float
    conditional_beta_std: float
    conditional_t: float
    causal_screen_pass: int
    residual_competition_score: float
    innovation_corr: float
    innovation_beta_std: float
    innovation_t: float
    innovation_pass: int
    orientation_score: float
    orientation_dominance: float
    orientation_pass: int
    consensus_score: float
    consensus_pass_rate: float
    consensus_sign_consistency: float
    consensus_segments: int
    consensus_pass: int
    mediator_hint: str
    forbidden_adjustment_hint: str
    risk_flags: List[str]
    exclusion_reasons: List[str]
    reason_codes: List[str]
    priority: float
    safety_precheck: str


# Keep the wildcard import surface explicit.
#
# The Discovery mixins still use ``from .engine_common import *`` for backward
# compatibility, but the exported namespace must be intentional.  Downstream
# SCM/estimation/runtime bridges are intentionally not exported here; those
# optional integrations are loaded lazily by dedicated bridge modules.
__all__ = [
    # stdlib modules/helpers used by mixins
    "argparse",
    "json",
    "math",
    "os",
    "re",
    "sys",
    "combinations",
    "dataclass",
    # typing aliases used in annotations
    "Dict",
    "List",
    "Optional",
    "Sequence",
    "Tuple",
    # config/calibration
    "ProposalConfig",
    "CAL",
    "_parent_spec",
    "_parse_parent_spec",
    "_lagged_control_array",
    "_parent_spec_to_control",
    # shared dataclasses
    "DiscoveryContext",
    "SourceMetrics",
    # discovery helpers
    "OfflinePriorGraph",
    "_action_family",
    "_as_str",
    "_best_lag_metrics",
    "_clip01",
    "_corr",
    "_adjusted_effect_metrics",
    "_ensure_out",
    "_feature_family",
    "_future_leakage_score",
    "_is_intervenible",
    "_is_sensitive",
    "_mechanism_hint",
    "_norm_abs",
    "_regime_awareness_metrics",
    "_rolling_stability",
    "_safe_float",
    "_temporal_conditional_signal",
    "_residual_competition_signal",
    "_edge_orientation_signal",
    "_conditional_independence_signal",
    "_mci_signal",
    "_residualize",
]
