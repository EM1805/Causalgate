from __future__ import annotations

from runtime_env import configure_scientific_runtime
configure_scientific_runtime()


import math
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np
from runtime_compat import assert_scientific_stack
assert_scientific_stack()
import pandas as pd

from .config import ProposalConfig

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

# Offline prior graph support was removed from the public input contract.
OfflinePriorGraph = None  # type: ignore


def _ensure_out(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _safe_float(x, default: float = np.nan) -> float:
    try:
        v = float(x)
        return v if np.isfinite(v) else float(default)
    except (TypeError, ValueError, OverflowError):
        return float(default)


def _as_str(x) -> str:
    try:
        return "" if x is None else str(x)
    except (TypeError, ValueError):
        return ""


def _clip01(x: float) -> float:
    if not np.isfinite(x):
        return 0.0
    return float(min(1.0, max(0.0, x)))


def _norm_abs(x: float, scale: float) -> float:
    if not np.isfinite(x) or scale <= 0:
        return 0.0
    return _clip01(abs(float(x)) / float(scale))


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    m = np.isfinite(a) & np.isfinite(b)
    if int(m.sum()) < 8:
        return np.nan
    aa = a[m]
    bb = b[m]
    if np.nanstd(aa) < 1e-12 or np.nanstd(bb) < 1e-12:
        return np.nan
    return float(np.corrcoef(aa, bb)[0, 1])


@lru_cache(maxsize=4)
def _load_family_map(path_str: str) -> dict:
    """Load optional external family mapping.

    Expected YAML shape:
      feature_families:
        context_load: [task_complexity, prompt_load]
      action_families:
        governance: [require_approval, enable_guardrails]

    Missing or invalid files fall back to an empty mapping so Discovery keeps its
    built-in behavior.
    """
    if not path_str or yaml is None:
        return {"feature_families": {}, "action_families": {}}
    path = Path(path_str)
    if not path.exists():
        return {"feature_families": {}, "action_families": {}}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, TypeError, ValueError):
        return {"feature_families": {}, "action_families": {}}
    if not isinstance(data, dict):
        return {"feature_families": {}, "action_families": {}}
    out = {"feature_families": {}, "action_families": {}}
    for section in ("feature_families", "action_families"):
        raw = data.get(section, {})
        if not isinstance(raw, dict):
            continue
        normalized = {}
        for fam, pats in raw.items():
            if isinstance(pats, (list, tuple)):
                normalized[str(fam)] = tuple(str(p).strip().lower() for p in pats if str(p).strip())
            elif pats is not None:
                normalized[str(fam)] = (str(pats).strip().lower(),)
        out[section] = normalized
    return out


def _resolve_family_map_path(cfg: Optional[ProposalConfig]) -> str:
    if cfg is None:
        return ""
    path = _as_str(getattr(cfg, "family_map_path", "")).strip()
    if not path:
        return ""
    if os.path.isabs(path) or os.path.exists(path):
        return path
    out_dir = _as_str(getattr(cfg, "out_dir", "")).strip()
    if out_dir:
        candidate = os.path.join(out_dir, path)
        if os.path.exists(candidate):
            return candidate
    return path


def _match_family_from_map(name: str, mapping: dict) -> Optional[str]:
    low = _as_str(name).strip().lower()
    if not low:
        return None
    for fam, pats in mapping.items():
        if any(p and p in low for p in pats):
            return str(fam)
    return None


def _residualize(vec: np.ndarray, controls: Sequence[np.ndarray]) -> np.ndarray:
    y = np.asarray(vec, dtype=float)
    if len(controls) == 0:
        return y.copy()
    mats = [np.asarray(c, dtype=float) for c in controls]
    mask = np.isfinite(y)
    for c in mats:
        mask &= np.isfinite(c)
    if int(mask.sum()) < max(8, len(mats) + 3):
        return np.full_like(y, np.nan, dtype=float)
    X = np.column_stack([np.ones(int(mask.sum()))] + [c[mask] for c in mats])
    yy = y[mask]
    try:
        beta, *_ = np.linalg.lstsq(X, yy, rcond=None)
        fitted = X @ beta
    except np.linalg.LinAlgError:
        return np.full_like(y, np.nan, dtype=float)
    out = np.full_like(y, np.nan, dtype=float)
    out[mask] = yy - fitted
    return out


def _adjusted_effect_metrics(x: np.ndarray, y: np.ndarray, controls: Sequence[np.ndarray], lag: int) -> dict:
    if lag < 1 or len(x) <= lag + 8:
        return {
            "adjusted_corr": np.nan, "adjusted_delta": np.nan, "n_eff": 0,
            "control_strength_x": np.nan, "control_strength_y": np.nan,
            "causal_effect": np.nan, "causal_effect_std": np.nan,
            "causal_effect_ci_low": np.nan, "causal_effect_ci_high": np.nan,
            "effect_persistence_score": np.nan,
        }
    x_lag = np.asarray(x[:-lag], dtype=float)
    y_fwd = np.asarray(y[lag:], dtype=float)
    ctrl = [np.asarray(c[:-lag], dtype=float) for c in controls]
    x_res = _residualize(x_lag, ctrl)
    y_res = _residualize(y_fwd, ctrl)
    mask = np.isfinite(x_res) & np.isfinite(y_res)
    n_eff = int(mask.sum())
    if n_eff < 8:
        return {
            "adjusted_corr": np.nan, "adjusted_delta": np.nan, "n_eff": n_eff,
            "control_strength_x": np.nan, "control_strength_y": np.nan,
            "causal_effect": np.nan, "causal_effect_std": np.nan,
            "causal_effect_ci_low": np.nan, "causal_effect_ci_high": np.nan,
            "effect_persistence_score": np.nan,
        }
    adj_corr = _corr(x_res, y_res)
    xv = x_res[mask]
    yv = y_res[mask]
    hi = xv >= np.nanmedian(xv)
    lo = xv < np.nanmedian(xv)
    if int(np.sum(hi)) < 4 or int(np.sum(lo)) < 4:
        adj_delta = np.nan
    else:
        adj_delta = float(np.nanmean(yv[hi]) - np.nanmean(yv[lo]))

    beta = np.nan
    beta_std = np.nan
    ci_low = np.nan
    ci_high = np.nan
    persistence = np.nan
    x_var = float(np.nanvar(xv))
    if n_eff >= 10 and x_var > 1e-12:
        xm = float(np.nanmean(xv))
        ym = float(np.nanmean(yv))
        cov_xy = float(np.nanmean((xv - xm) * (yv - ym)))
        beta = cov_xy / x_var
        x_sd = float(np.nanstd(xv))
        y_sd = float(np.nanstd(yv))
        if x_sd > 1e-12 and y_sd > 1e-12:
            beta_std = beta * (x_sd / y_sd)
        resid = yv - beta * xv
        dof = max(1, n_eff - 2)
        s2 = float(np.nansum(resid ** 2) / dof)
        se_beta = math.sqrt(s2 / max(np.nansum((xv - xm) ** 2), 1e-12))
        ci_low = beta - 1.96 * se_beta
        ci_high = beta + 1.96 * se_beta
        if np.isfinite(ci_low) and np.isfinite(ci_high):
            width = abs(ci_high - ci_low)
            persistence = _clip01(abs(beta) / max(abs(beta) + width, 1e-9))
    cx = np.nan
    cy = np.nan
    if len(ctrl) > 0:
        xr0 = _residualize(x_lag, [])
        yr0 = _residualize(y_fwd, [])
        cx = 1.0 - (np.nanvar(x_res[mask]) / max(np.nanvar(xr0[mask]), 1e-9))
        cy = 1.0 - (np.nanvar(y_res[mask]) / max(np.nanvar(yr0[mask]), 1e-9))
    return {
        "adjusted_corr": float(adj_corr) if np.isfinite(adj_corr) else np.nan,
        "adjusted_delta": float(adj_delta) if np.isfinite(adj_delta) else np.nan,
        "n_eff": n_eff,
        "control_strength_x": float(_clip01(cx)) if np.isfinite(cx) else np.nan,
        "control_strength_y": float(_clip01(cy)) if np.isfinite(cy) else np.nan,
        "causal_effect": float(beta) if np.isfinite(beta) else np.nan,
        "causal_effect_std": float(beta_std) if np.isfinite(beta_std) else np.nan,
        "causal_effect_ci_low": float(ci_low) if np.isfinite(ci_low) else np.nan,
        "causal_effect_ci_high": float(ci_high) if np.isfinite(ci_high) else np.nan,
        "effect_persistence_score": float(persistence) if np.isfinite(persistence) else np.nan,
    }



def _edge_orientation_signal(x: np.ndarray, y: np.ndarray, controls: Sequence[np.ndarray], lag: int, ar_lags: int = 2) -> dict:
    """Compare forward x(t-lag)->y(t) against reverse y(t-lag)->x(t).

    This is not full structure learning, but it is a stronger orientation cue than
    raw name heuristics because it checks whether the forward signal survives the
    same temporal/conditional screen better than the reverse direction.
    """
    fwd = _temporal_conditional_signal(x, y, controls, lag, ar_lags=ar_lags)
    rev = _temporal_conditional_signal(y, x, controls, lag, ar_lags=ar_lags)
    fwd_score = float(fwd.get("screen_score", 0.0) or 0.0)
    rev_score = float(rev.get("screen_score", 0.0) or 0.0)
    dominance = fwd_score - rev_score
    orientation_score = _clip01(0.5 + 0.5 * dominance)
    return {
        "forward_score": fwd_score,
        "reverse_score": rev_score,
        "dominance": float(dominance),
        "orientation_score": float(orientation_score),
        "pass": int((int(fwd.get("pass", 0) or 0) == 1) and (dominance > 0.0)),
    }


def _ols_r2(y: np.ndarray, X_cols: Sequence[np.ndarray]) -> dict:
    yy = np.asarray(y, dtype=float)
    cols = [np.asarray(c, dtype=float) for c in X_cols]
    mask = np.isfinite(yy)
    for c in cols:
        mask &= np.isfinite(c)
    n_eff = int(mask.sum())
    p = len(cols) + 1
    if n_eff < max(10, p + 3):
        return {"ok": False, "n_eff": n_eff}
    X = np.column_stack([np.ones(n_eff)] + [c[mask] for c in cols])
    yv = yy[mask]
    try:
        beta, *_ = np.linalg.lstsq(X, yv, rcond=None)
        fitted = X @ beta
    except np.linalg.LinAlgError:
        return {"ok": False, "n_eff": n_eff}
    resid = yv - fitted
    sse = float(np.nansum(resid ** 2))
    sst = float(np.nansum((yv - np.nanmean(yv)) ** 2))
    r2 = 0.0 if sst <= 1e-12 else float(max(0.0, 1.0 - sse / sst))
    return {
        "ok": True,
        "n_eff": n_eff,
        "X": X,
        "y": yv,
        "beta": np.asarray(beta, dtype=float),
        "r2": r2,
        "sse": sse,
    }


def _temporal_conditional_signal(x: np.ndarray, y: np.ndarray, controls: Sequence[np.ndarray], lag: int, ar_lags: int = 2) -> dict:
    if lag < 1 or len(x) <= lag + max(12, ar_lags + 6):
        return {
            "incremental_r2": np.nan,
            "conditional_beta": np.nan,
            "conditional_beta_std": np.nan,
            "conditional_t": np.nan,
            "n_eff": 0,
            "screen_score": 0.0,
            "pass": 0,
        }
    start = max(int(lag), int(ar_lags))
    y_t = np.asarray(y[start:], dtype=float)
    if len(y_t) < 12:
        return {
            "incremental_r2": np.nan,
            "conditional_beta": np.nan,
            "conditional_beta_std": np.nan,
            "conditional_t": np.nan,
            "n_eff": 0,
            "screen_score": 0.0,
            "pass": 0,
        }
    base_cols = []
    for j in range(1, int(ar_lags) + 1):
        base_cols.append(np.asarray(y[start - j: len(y) - j], dtype=float))
    ctrl_cols = []
    for c in controls:
        arr = np.asarray(c, dtype=float)
        ctrl_cols.append(np.asarray(arr[start - lag: len(arr) - lag], dtype=float))
    x_lag = np.asarray(x[start - lag: len(x) - lag], dtype=float)
    restricted = _ols_r2(y_t, base_cols + ctrl_cols)
    full = _ols_r2(y_t, base_cols + ctrl_cols + [x_lag])
    if not restricted.get("ok") or not full.get("ok"):
        return {
            "incremental_r2": np.nan,
            "conditional_beta": np.nan,
            "conditional_beta_std": np.nan,
            "conditional_t": np.nan,
            "n_eff": int(max(restricted.get("n_eff", 0), full.get("n_eff", 0))),
            "screen_score": 0.0,
            "pass": 0,
        }
    delta_r2 = max(0.0, float(full["r2"]) - float(restricted["r2"]))
    beta = float(full["beta"][-1])
    x_masked = x_lag[np.isfinite(x_lag) & np.isfinite(y_t)]
    y_masked = y_t[np.isfinite(x_lag) & np.isfinite(y_t)]
    beta_std = np.nan
    if len(x_masked) >= 8:
        sx = float(np.nanstd(x_masked))
        sy = float(np.nanstd(y_masked))
        if sx > 1e-12 and sy > 1e-12:
            beta_std = float(beta * sx / sy)
    n_eff = int(full["n_eff"])
    p = int(full["X"].shape[1])
    dof = max(1, n_eff - p)
    s2 = float(full["sse"]) / dof
    xtx_inv = np.linalg.pinv(full["X"].T @ full["X"])
    se_beta = float(np.sqrt(max(xtx_inv[-1, -1] * s2, 0.0)))
    t_stat = float(beta / se_beta) if se_beta > 1e-12 else np.nan
    t_score = 0.0 if not np.isfinite(t_stat) else _clip01(abs(t_stat) / 3.5)
    beta_score = 0.0 if not np.isfinite(beta_std) else _clip01(abs(beta_std) / 0.20)
    r2_score = _clip01(delta_r2 / 0.03)
    screen_score = float(_clip01(0.45 * r2_score + 0.35 * beta_score + 0.20 * t_score))
    return {
        "incremental_r2": float(delta_r2),
        "conditional_beta": float(beta),
        "conditional_beta_std": float(beta_std) if np.isfinite(beta_std) else np.nan,
        "conditional_t": float(t_stat) if np.isfinite(t_stat) else np.nan,
        "n_eff": n_eff,
        "screen_score": screen_score,
        "pass": int(delta_r2 >= 0.008 and ((np.isfinite(beta_std) and abs(beta_std) >= 0.03) or (np.isfinite(beta) and abs(beta) >= 1e-6))),
    }



def _conditional_independence_signal(x: np.ndarray, y: np.ndarray, controls: Sequence[np.ndarray], lag: int, ar_lags: int = 2) -> dict:
    """Lightweight conditional-independence screen for pruning.

    The candidate is considered to retain a structural edge only if it still shows
    meaningful association with the outcome after conditioning on:
    - target autoregressive lags
    - a small set of already-kept parent candidates
    """
    summary = _temporal_conditional_signal(x, y, controls, lag, ar_lags=ar_lags)
    x_lag = np.asarray(x[:-lag], dtype=float) if lag >= 1 else np.asarray(x, dtype=float)
    y_fwd = np.asarray(y[lag:], dtype=float) if lag >= 1 else np.asarray(y, dtype=float)
    ctrl = [np.asarray(c[:-lag], dtype=float) for c in controls] if lag >= 1 else [np.asarray(c, dtype=float) for c in controls]
    ar_ctrl = []
    if lag >= 1 and ar_lags > 0:
        for k in range(1, max(1, ar_lags) + 1):
            yy = np.asarray(y[(lag-k):-k], dtype=float) if lag-k >= 0 else None
            if yy is not None and len(yy) == len(y_fwd):
                ar_ctrl.append(yy)
    all_ctrl = list(ctrl) + ar_ctrl
    x_res = _residualize(x_lag, all_ctrl)
    y_res = _residualize(y_fwd, all_ctrl)
    pcorr = _corr(x_res, y_res)
    beta_std = float(summary.get('conditional_beta_std', np.nan))
    t_val = float(summary.get('conditional_t', np.nan))
    score = _clip01(0.50 * abs(pcorr if np.isfinite(pcorr) else 0.0) / 0.20 + 0.50 * float(summary.get('screen_score', 0.0) or 0.0))
    return {
        'partial_corr': float(pcorr) if np.isfinite(pcorr) else np.nan,
        'beta_std': beta_std if np.isfinite(beta_std) else np.nan,
        't_stat': t_val if np.isfinite(t_val) else np.nan,
        'screen_score': float(summary.get('screen_score', 0.0) or 0.0),
        'pass': int(summary.get('pass', 0) or 0),
        'ci_score': float(score),
    }
def _mci_signal(
    x: np.ndarray,
    y: np.ndarray,
    y_parent_controls: Sequence[np.ndarray],
    x_parent_controls: Sequence[np.ndarray],
    lag: int,
    ar_lags: int = 2,
) -> dict:
    """PCMCI-lite momentary conditional independence signal.

    Tests whether x(t-lag) retains signal for y(t) after conditioning on
    parents(Y) and parents(X), in addition to autoregressive lags of Y.

    Returns a stronger summary than the old implementation by exposing:
    - effective sample size after conditioning
    - incremental R^2 retained under conditioning
    - robustness of the source signal when moving from Y-parent controls
      to the full conditioning set
    """
    y_only = _conditional_independence_signal(x, y, list(y_parent_controls), lag, ar_lags=ar_lags)
    controls = list(y_parent_controls) + list(x_parent_controls)
    summary = _conditional_independence_signal(x, y, controls, lag, ar_lags=ar_lags)
    pcorr = float(summary.get("partial_corr", np.nan))
    t_stat = float(summary.get("t_stat", np.nan))
    screen_score = float(summary.get("screen_score", 0.0) or 0.0)
    ci_score = float(summary.get("ci_score", 0.0) or 0.0)

    temporal_full = _temporal_conditional_signal(x, y, controls, lag, ar_lags=ar_lags)
    temporal_y_only = _temporal_conditional_signal(x, y, list(y_parent_controls), lag, ar_lags=ar_lags)
    delta_r2 = float(temporal_full.get("incremental_r2", np.nan))
    n_eff = int(temporal_full.get("n_eff", 0) or 0)
    if (not np.isfinite(t_stat)) and np.isfinite(pcorr) and n_eff > 3 and abs(pcorr) < 0.999999:
        denom = max(1e-12, 1.0 - float(pcorr) ** 2)
        t_stat = float(pcorr * np.sqrt(max(1.0, float(n_eff - 2)) / denom))
    y_only_ci = float(y_only.get("ci_score", 0.0) or 0.0)
    robustness = np.nan
    if np.isfinite(ci_score) and np.isfinite(y_only_ci):
        robustness = 1.0 - min(1.0, abs(ci_score - y_only_ci) / max(0.20, abs(y_only_ci), abs(ci_score), 1e-6))
    robustness_score = _clip01(robustness if np.isfinite(robustness) else 0.0)
    n_eff_score = _clip01((float(n_eff) - 16.0) / 36.0)
    delta_r2_score = _clip01((delta_r2 if np.isfinite(delta_r2) else 0.0) / 0.02)
    pcorr_score = _clip01(abs(pcorr) / 0.18 if np.isfinite(pcorr) else 0.0)
    score = _clip01(
        0.38 * ci_score
        + 0.18 * screen_score
        + 0.16 * pcorr_score
        + 0.16 * delta_r2_score
        + 0.12 * robustness_score
        + 0.00 * n_eff_score
    )
    return {
        "mci_score": float(score),
        "mci_partial_corr": pcorr if np.isfinite(pcorr) else np.nan,
        "mci_t": t_stat if np.isfinite(t_stat) else np.nan,
        "mci_screen_score": screen_score,
        "mci_delta_r2": float(delta_r2) if np.isfinite(delta_r2) else np.nan,
        "mci_n_eff": int(n_eff),
        "mci_robustness": float(robustness) if np.isfinite(robustness) else np.nan,
        "mci_y_only_score": float(y_only_ci),
        "pass": int(summary.get("pass", 0) or 0),
    }


def _residual_competition_signal(x: np.ndarray, y: np.ndarray, rival_controls: Sequence[np.ndarray], lag: int, ar_lags: int = 2) -> dict:
    """Compare source innovation against autoregressive target dynamics and rival parents.

    The idea is stronger than a plain lagged correlation: source must explain target
    innovation after accounting for target history *and* rival lagged candidates.
    """
    if lag < 1 or len(x) <= lag + max(12, ar_lags + 6):
        return {
            "innovation_corr": np.nan,
            "innovation_beta": np.nan,
            "innovation_beta_std": np.nan,
            "innovation_t": np.nan,
            "innovation_r2": np.nan,
            "screen_score": 0.0,
            "pass": 0,
            "n_eff": 0,
        }
    start = max(int(lag), int(ar_lags))
    y_t = np.asarray(y[start:], dtype=float)
    if len(y_t) < 12:
        return {
            "innovation_corr": np.nan,
            "innovation_beta": np.nan,
            "innovation_beta_std": np.nan,
            "innovation_t": np.nan,
            "innovation_r2": np.nan,
            "screen_score": 0.0,
            "pass": 0,
            "n_eff": 0,
        }
    base_cols = []
    for j in range(1, int(ar_lags) + 1):
        base_cols.append(np.asarray(y[start - j: len(y) - j], dtype=float))
    rival_cols = []
    for c in rival_controls:
        arr = np.asarray(c, dtype=float)
        rival_cols.append(np.asarray(arr[start - lag: len(arr) - lag], dtype=float))
    x_lag = np.asarray(x[start - lag: len(x) - lag], dtype=float)
    y_res = _residualize(y_t, base_cols + rival_cols)
    x_res = _residualize(x_lag, rival_cols)
    mask = np.isfinite(x_res) & np.isfinite(y_res)
    n_eff = int(mask.sum())
    if n_eff < max(12, len(rival_cols) + ar_lags + 5):
        return {
            "innovation_corr": np.nan,
            "innovation_beta": np.nan,
            "innovation_beta_std": np.nan,
            "innovation_t": np.nan,
            "innovation_r2": np.nan,
            "screen_score": 0.0,
            "pass": 0,
            "n_eff": n_eff,
        }
    xv = x_res[mask]
    yv = y_res[mask]
    innovation_corr = _corr(xv, yv)
    fit = _ols_r2(yv, [xv])
    if not fit.get('ok'):
        return {
            "innovation_corr": float(innovation_corr) if np.isfinite(innovation_corr) else np.nan,
            "innovation_beta": np.nan,
            "innovation_beta_std": np.nan,
            "innovation_t": np.nan,
            "innovation_r2": np.nan,
            "screen_score": 0.0,
            "pass": 0,
            "n_eff": n_eff,
        }
    beta = float(fit['beta'][-1])
    r2 = float(fit['r2'])
    sx = float(np.nanstd(xv))
    sy = float(np.nanstd(yv))
    beta_std = np.nan
    if sx > 1e-12 and sy > 1e-12:
        beta_std = float(beta * sx / sy)
    p = int(fit['X'].shape[1])
    dof = max(1, n_eff - p)
    s2 = float(fit['sse']) / dof
    xtx_inv = np.linalg.pinv(fit['X'].T @ fit['X'])
    se_beta = float(np.sqrt(max(xtx_inv[-1, -1] * s2, 0.0)))
    t_stat = float(beta / se_beta) if se_beta > 1e-12 else np.nan
    corr_score = 0.0 if not np.isfinite(innovation_corr) else _clip01(abs(float(innovation_corr)) / 0.18)
    r2_score = _clip01(r2 / 0.02)
    t_score = 0.0 if not np.isfinite(t_stat) else _clip01(abs(float(t_stat)) / 3.0)
    screen_score = float(_clip01(0.45 * corr_score + 0.30 * r2_score + 0.25 * t_score))
    passed = bool((np.isfinite(innovation_corr) and abs(float(innovation_corr)) >= 0.06) and (np.isfinite(beta_std) and abs(float(beta_std)) >= 0.025 or np.isfinite(t_stat) and abs(float(t_stat)) >= 1.4))
    return {
        "innovation_corr": float(innovation_corr) if np.isfinite(innovation_corr) else np.nan,
        "innovation_beta": float(beta),
        "innovation_beta_std": float(beta_std) if np.isfinite(beta_std) else np.nan,
        "innovation_t": float(t_stat) if np.isfinite(t_stat) else np.nan,
        "innovation_r2": float(r2),
        "screen_score": screen_score,
        "pass": int(passed),
        "n_eff": n_eff,
    }


def _robust_z(arr: np.ndarray) -> np.ndarray:
    x = np.asarray(arr, dtype=float)
    med = np.nanmedian(x)
    mad = np.nanmedian(np.abs(x - med))
    scale = 1.4826 * mad if np.isfinite(mad) and mad > 1e-8 else np.nanstd(x)
    if not np.isfinite(scale) or scale < 1e-8:
        scale = 1.0
    return (x - med) / scale


def _rolling_windows(n: int, window: int, stride: int) -> Iterable[Tuple[int, int]]:
    if window <= 0 or stride <= 0 or n <= 0:
        return []
    out: List[Tuple[int, int]] = []
    s = 0
    while s + window <= n:
        out.append((s, s + window))
        s += stride
    if not out and n >= max(10, window // 2):
        out.append((0, n))
    return out


def _best_lag_metrics(x: np.ndarray, y: np.ndarray, max_lag: int) -> dict:
    best = {"lag": np.nan, "corr": np.nan, "delta_test": np.nan, "n_eff": 0}
    yz = _robust_z(y)
    best_score = -1.0
    for lag in range(1, int(max_lag) + 1):
        if len(x) <= lag + 8:
            continue
        x_lag = np.asarray(x[:-lag], dtype=float)
        y_fwd = np.asarray(y[lag:], dtype=float)
        mask = np.isfinite(x_lag) & np.isfinite(y_fwd)
        n_eff = int(mask.sum())
        if n_eff < 8:
            continue
        corr = _corr(x_lag, y_fwd)
        if not np.isfinite(corr):
            continue
        x_valid = x_lag[mask]
        y_valid_z = yz[lag:][mask]
        high = x_valid >= np.nanmedian(x_valid)
        low = x_valid < np.nanmedian(x_valid)
        if int(np.sum(high)) < 4 or int(np.sum(low)) < 4:
            delta = np.nan
        else:
            delta = float(np.nanmean(y_valid_z[high]) - np.nanmean(y_valid_z[low]))
        score = abs(corr) + 0.35 * abs(delta) if np.isfinite(delta) else abs(corr)
        if score > best_score:
            best_score = score
            best = {
                "lag": int(lag),
                "corr": float(corr),
                "delta_test": float(delta) if np.isfinite(delta) else np.nan,
                "n_eff": int(n_eff),
            }
    return best


def _rolling_stability(x: np.ndarray, y: np.ndarray, lag: int, window: int, stride: int) -> Tuple[float, int, float]:
    vals: List[float] = []
    deltas: List[float] = []
    for s, e in _rolling_windows(len(x), window, stride):
        xx = x[s:e]
        yy = y[s:e]
        if len(xx) <= lag + 8:
            continue
        met = _best_lag_metrics(xx, yy, lag)
        if np.isfinite(met["corr"]):
            vals.append(float(met["corr"]))
        if np.isfinite(met["delta_test"]):
            deltas.append(float(met["delta_test"]))
    if len(vals) == 0:
        return np.nan, 0, np.nan
    signs = np.sign(vals)
    nonzero = signs[signs != 0]
    sign_consistency = abs(float(np.nanmean(nonzero))) if len(nonzero) else 0.0
    dispersion = np.nanstd(vals)
    stability = float(max(0.0, sign_consistency * (1.0 - min(1.0, dispersion / 0.35))))
    return stability, int(len(vals)), float(np.nanmean(deltas)) if len(deltas) else np.nan


def _future_leakage_score(x: np.ndarray, y: np.ndarray, lag: int) -> dict:
    same = _corr(x, y)
    future = np.nan
    past = np.nan
    if len(x) > lag + 8:
        future = _corr(x[lag:], y[:-lag])
        past = _corr(x[:-lag], y[lag:])
    gap = np.nan
    if np.isfinite(future) and np.isfinite(past):
        gap = abs(future) - abs(past)
    score = 0.0
    if np.isfinite(same):
        score += max(0.0, abs(same) - 0.85) / 0.15
    if np.isfinite(gap):
        score += max(0.0, gap) / 0.25
    return {
        "lag0_corr": same,
        "future_corr": future,
        "past_corr": past,
        "leakage_score": float(min(1.5, score)),
    }


def _is_intervenible(col: str, cfg: ProposalConfig) -> Tuple[bool, List[str]]:
    name = col.strip().lower()
    is_negative_control = name == "negative_control_outcome"
    reasons: List[str] = []
    if not name:
        reasons.append("EMPTY_NAME")
    if name == cfg.target_col.strip().lower():
        reasons.append("IS_TARGET")
    if name == cfg.date_col.strip().lower():
        reasons.append("IS_DATE")
    for token in cfg.candidate_name_blocklist:
        if token and token in name:
            reasons.append("NON_ACTIONABLE_NAME")
            break
    if name.endswith("_prev") or name.startswith("prev_"):
        reasons.append("LAGGED_PROXY")
    for pat in cfg.hard_block_name_patterns:
        if is_negative_control:
            break
        if pat and pat in name and pat not in ("post",):
            reasons.append("LEAKAGE_NAME_PATTERN")
            break
    if (not is_negative_control) and "post" in name and "posture" not in name:
        reasons.append("LEAKAGE_NAME_PATTERN")
    return len(reasons) == 0, reasons


def _is_sensitive(col: str, cfg: ProposalConfig) -> bool:
    low = col.lower()
    return any(pat in low for pat in cfg.sensitive_name_patterns)


def _action_name(col: str, sign: float) -> Tuple[str, str]:
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", col.strip().lower()).strip("_")
    if not base:
        base = "signal"
    if sign > 0:
        return f"increase_{base}", "increase"
    if sign < 0:
        return f"reduce_{base}", "reduce"
    return f"adjust_{base}", "adjust"


def _mechanism_hint(col: str, lag: int, corr: float) -> str:
    direction = "increase" if corr > 0 else "decrease"
    return f"lagged_{col}_change_may_{direction}_target_within_{int(lag)}d_if_relation_is_stable"


def _feature_family(name: str, cfg: Optional[ProposalConfig] = None) -> str:
    low = _as_str(name).strip().lower()
    fmap = _load_family_map(_resolve_family_map_path(cfg)).get("feature_families", {})
    mapped = _match_family_from_map(low, fmap)
    if mapped:
        return mapped
    # Built-in fallback heuristics stay intentionally simple, but are now
    # oriented to agent-policy telemetry rather than wellbeing naming.
    for fam, pats in {
        "guardrail": ("guardrail", "approval", "review", "override"),
        "tooling": ("tool", "retry", "latency", "memory"),
        "policy_action": ("action", "rollback", "novel", "policy"),
        "workload": ("context", "ambiguity", "load", "risk"),
        "outcome": ("harm", "incident", "failure", "blast", "recovery"),
    }.items():
        if any(p in low for p in pats):
            return fam
    toks = [t for t in re.split(r"[_\W]+", low) if t]
    return toks[0] if toks else "other"


def _action_family(action_name: str, cfg: Optional[ProposalConfig] = None) -> str:
    low = _as_str(action_name).strip().lower()
    fmap = _load_family_map(_resolve_family_map_path(cfg)).get("action_families", {})
    mapped = _match_family_from_map(low, fmap)
    if mapped:
        return mapped
    low = re.sub(r"^(increase|reduce|adjust)_", "", low)
    return _feature_family(low, cfg=cfg)


def _utc_now_ts() -> pd.Timestamp:
    ts = pd.Timestamp.utcnow()
    try:
        return ts.tz_localize(None)
    except TypeError:
        return ts.tz_convert(None) if ts.tzinfo is not None else ts


def _coerce_ts_series(s: pd.Series) -> pd.Series:
    dt = pd.to_datetime(s, errors="coerce")
    try:
        return dt.dt.tz_localize(None)
    except (TypeError, AttributeError):
        return dt


def _days_ago(ts: pd.Timestamp, ref: Optional[pd.Timestamp] = None) -> float:
    ref = ref if ref is not None else _utc_now_ts()
    if ts is None or pd.isna(ts):
        return np.nan
    return float((ref - ts).total_seconds() / 86400.0)


def _exp_decay_weight(days_ago: float, half_life_days: float) -> float:
    if not np.isfinite(days_ago):
        return 1.0
    hl = max(1e-6, float(half_life_days))
    return float(0.5 ** (max(0.0, days_ago) / hl))


def _regime_awareness_metrics(x: np.ndarray, y: np.ndarray, lag: int, recent_frac: float, min_recent_n: int) -> dict:
    n = len(x)
    recent_n = max(int(round(n * float(recent_frac))), int(min_recent_n))
    if n < max(40, 2 * (lag + 10)):
        return {"regime_shift_score": np.nan, "regime_alignment_score": 0.5, "recent_corr": np.nan, "past_corr": np.nan, "recent_delta": np.nan, "past_delta": np.nan}
    recent_n = min(recent_n, n - (lag + 10))
    if recent_n <= lag + 8:
        return {"regime_shift_score": np.nan, "regime_alignment_score": 0.5, "recent_corr": np.nan, "past_corr": np.nan, "recent_delta": np.nan, "past_delta": np.nan}
    split = n - recent_n
    past = _best_lag_metrics(x[:split], y[:split], lag)
    recent = _best_lag_metrics(x[split:], y[split:], lag)
    pc = float(past.get("corr", np.nan))
    rc = float(recent.get("corr", np.nan))
    pdl = float(past.get("delta_test", np.nan))
    rdl = float(recent.get("delta_test", np.nan))
    if not np.isfinite(pc) or not np.isfinite(rc):
        return {"regime_shift_score": np.nan, "regime_alignment_score": 0.5, "recent_corr": rc, "past_corr": pc, "recent_delta": rdl, "past_delta": pdl}
    shift_mag = min(1.0, abs(rc - pc) / 0.35)
    sign_flip = 1.0 if np.sign(rc) != np.sign(pc) and abs(rc) > 0.05 and abs(pc) > 0.05 else 0.0
    delta_shift = min(1.0, abs(rdl - pdl) / 0.75) if np.isfinite(rdl) and np.isfinite(pdl) else 0.0
    shift = _clip01(0.55 * shift_mag + 0.25 * sign_flip + 0.20 * delta_shift)
    align = _clip01(1.0 - shift)
    return {"regime_shift_score": float(shift), "regime_alignment_score": float(align), "recent_corr": rc, "past_corr": pc, "recent_delta": rdl, "past_delta": pdl}
