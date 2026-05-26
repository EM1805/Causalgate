
from runtime_env import configure_scientific_runtime
configure_scientific_runtime()

from .engine_common import *
from .mci import MciMixin
from .pc1 import Pc1Mixin
import numpy as np
import pandas as pd


class PcmciPrunerMixin(Pc1Mixin, MciMixin):
    def _conditional_independence_prune_summary(self, challenge_source: str, control_sources: Sequence[str], df: pd.DataFrame, lag: int) -> dict:
        if challenge_source not in df.columns or len(control_sources) == 0:
            return {"score": np.nan, "partial_corr": np.nan, "t_stat": np.nan, "pass": 1, "controls": ""}
        x = pd.to_numeric(df[challenge_source], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(df[self.cfg.target_col], errors="coerce").to_numpy(dtype=float)
        ctrls = []
        keep_names = []
        for name in control_sources:
            if name and name in df.columns and name != challenge_source:
                ctrls.append(pd.to_numeric(df[name], errors="coerce").to_numpy(dtype=float))
                keep_names.append(name)
        if len(ctrls) == 0:
            return {"score": np.nan, "partial_corr": np.nan, "t_stat": np.nan, "pass": 1, "controls": ""}
        summary = _conditional_independence_signal(
            x, y, ctrls, lag,
            ar_lags=max(1, int(getattr(self.cfg, "discovery_target_ar_lags", 2)))
        )
        partial_corr = float(summary.get("partial_corr", np.nan))
        t_stat = float(summary.get("t_stat", np.nan))
        score = float(summary.get("ci_score", 0.0) or 0.0)
        survives = (
            score >= float(getattr(self.cfg, "ci_prune_min_score", 0.50))
            and abs(partial_corr) >= float(getattr(self.cfg, "ci_prune_min_partial_corr", 0.045))
            and abs(t_stat) >= float(getattr(self.cfg, "ci_prune_min_t_abs", 1.25))
            and int(summary.get("pass", 0) or 0) == 1
        )
        return {
            "score": score,
            "partial_corr": partial_corr,
            "t_stat": t_stat,
            "pass": int(survives),
            "controls": "|".join(keep_names),
        }







    def _apply_conditional_independence_pruning(self, proposals: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
        out = proposals.copy()
        out["ci_prune_score"] = np.nan
        out["ci_prune_partial_corr"] = np.nan
        out["ci_prune_t"] = np.nan
        out["ci_prune_pass"] = 1
        out["ci_prune_controls"] = ""
        out["ci_prune_reason"] = ""
        candidate_idx = out.index[out["discovery_track"] != "dropped"].tolist()
        conditioned_kept = []
        for idx in candidate_idx:
            row = out.loc[idx]
            challenger = _as_str(row.get("source", ""))
            lag = int(_safe_float(row.get("lag", np.nan), 1.0))
            eligible = []
            for prev_idx in conditioned_kept:
                prev = out.loc[prev_idx]
                if _as_str(prev.get("target_col", self.cfg.target_col)) != _as_str(row.get("target_col", self.cfg.target_col)):
                    continue
                if int(_safe_float(prev.get("lag", np.nan), -1)) != lag:
                    continue
                eligible.append(prev_idx)
            if eligible:
                eligible = sorted(eligible, key=lambda i: float(_safe_float(out.loc[i].get("priority_score", np.nan), 0.0)), reverse=True)
                max_par = max(1, int(getattr(self.cfg, "ci_prune_max_conditioning_parents", 3)))
                control_sources = [_as_str(out.loc[i].get("source", "")) for i in eligible[:max_par]]
                summary = self._conditional_independence_prune_summary(challenger, control_sources, df, lag)
                out.at[idx, "ci_prune_score"] = float(summary.get("score", np.nan))
                out.at[idx, "ci_prune_partial_corr"] = float(summary.get("partial_corr", np.nan)) if np.isfinite(summary.get("partial_corr", np.nan)) else np.nan
                out.at[idx, "ci_prune_t"] = float(summary.get("t_stat", np.nan)) if np.isfinite(summary.get("t_stat", np.nan)) else np.nan
                out.at[idx, "ci_prune_controls"] = _as_str(summary.get("controls", ""))
                if int(summary.get("pass", 0) or 0) != 1:
                    out.at[idx, "ci_prune_pass"] = 0
                    # Step 184 / PCMCI cleanup B: this is now only a
                    # lightweight pre-MCI diagnostic. MCI is the main
                    # conditional test, so CI pre-screen must not add
                    # CI_PRUNE or remove a candidate by itself.
                    out.at[idx, "ci_prune_reason"] = "CI_PRESCREEN_DIAGNOSTIC_FAIL"
                    rf = _as_str(out.at[idx, "risk_flags"])
                    flag = "ci_prescreen_diagnostic_fail"
                    out.at[idx, "risk_flags"] = (rf + "|" + flag).strip("|") if rf else flag
            conditioned_kept.append(idx)
        return out
