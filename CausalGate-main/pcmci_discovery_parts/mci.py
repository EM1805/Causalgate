
from runtime_env import configure_scientific_runtime
configure_scientific_runtime()

from .engine_common import *
import numpy as np
import pandas as pd


class MciMixin:
    def _lagged_control_array(self, values: np.ndarray, lag: int) -> np.ndarray:
        return _lagged_control_array(values, lag)


    def _parent_spec_to_control(self, spec: str, df: pd.DataFrame) -> tuple:
        return _parent_spec_to_control(spec, df)


    def _rank_source_parent_specs(self, source: str, target: str, df: pd.DataFrame) -> list:
        """Infer a small parent set for X when PC1 did not already expose one.

        The expensive temporal screen is run only after cheap non-null,
        variance, and quick-correlation prefilters. This keeps the auxiliary
        source-parent path bounded on wide dataframes.
        """
        if not bool(getattr(self.cfg, "mci_source_parent_enable", True)):
            return []
        if source not in df.columns:
            return []
        x_as_target = pd.to_numeric(df[source], errors="coerce").to_numpy(dtype=float)
        if not np.isfinite(np.nanstd(x_as_target)) or np.nanstd(x_as_target) <= 1e-12:
            return []

        max_lag = max(1, int(getattr(self.cfg, "mci_source_parent_max_lag", 2)))
        max_keep = max(0, int(getattr(self.cfg, "mci_source_parent_max_candidates", 3)))
        min_score = float(getattr(self.cfg, "mci_source_parent_min_score", 0.18))
        min_nonnull = max(12, int(getattr(self.cfg, "mci_source_parent_min_nonnull", 12)))
        min_std = float(getattr(self.cfg, "mci_source_parent_min_std", 1e-12))
        prefilter_top_k = int(
            getattr(self.cfg, "mci_source_parent_prefilter_top_k", max(24, max_keep * 8))
        )
        if max_keep <= 0:
            return []

        blocked = {source, target, _as_str(getattr(self.cfg, "date_col", "date"))}
        pre_candidates = []
        for col in df.columns:
            if col in blocked:
                continue
            vals = pd.to_numeric(df[col], errors="coerce")
            if int(vals.notna().sum()) < min_nonnull:
                continue
            z = vals.to_numpy(dtype=float)
            z_std = float(np.nanstd(z))
            if not np.isfinite(z_std) or z_std <= min_std:
                continue
            quick = abs(float(_corr(z, x_as_target)))
            pre_candidates.append((quick if np.isfinite(quick) else 0.0, col, z))
        pre_candidates.sort(key=lambda item: item[0], reverse=True)
        if prefilter_top_k > 0:
            pre_candidates = pre_candidates[:prefilter_top_k]

        candidates = []
        for _quick, col, z in pre_candidates:
            for parent_lag in range(1, max_lag + 1):
                summary = _temporal_conditional_signal(
                    z,
                    x_as_target,
                    [],
                    parent_lag,
                    ar_lags=max(1, int(getattr(self.cfg, "discovery_target_ar_lags", 2))),
                )
                score = float(summary.get("screen_score", 0.0) or 0.0)
                delta = float(summary.get("incremental_r2", np.nan))
                t_raw = float(summary.get("conditional_t", np.nan))
                t_abs = abs(t_raw) if np.isfinite(t_raw) else 0.0
                if score >= min_score and int(summary.get("pass", 0) or 0) == 1:
                    candidates.append((
                        score,
                        delta if np.isfinite(delta) else 0.0,
                        t_abs,
                        _parent_spec(col, parent_lag),
                    ))
        candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        selected = []
        seen_base = set()
        for _, _, _, spec in candidates:
            base, _lag = _parse_parent_spec(spec)
            if base in seen_base:
                continue
            selected.append(spec)
            seen_base.add(base)
            if len(selected) >= max_keep:
                break
        return selected


    def _pc1_parent_sets_from_rows(self, proposals: pd.DataFrame) -> dict:
        """Reconstruct PC1 parent sets already written on proposal rows."""
        required = {"target_col", "pc1_parent_set_all"}
        if proposals.empty or not required.issubset(set(proposals.columns)):
            return {}
        parent_sets = {}
        for target, grp in proposals.groupby("target_col", dropna=False, sort=False):
            target = _as_str(target) or _as_str(getattr(self.cfg, "target_col", ""))
            specs = []
            for value in grp["pc1_parent_set_all"].dropna().map(_as_str):
                specs = [s for s in value.split("|") if s]
                if specs:
                    break
            if not specs and "pc1_is_selected_parent" in grp.columns:
                selected = grp[grp["pc1_is_selected_parent"].astype(str).isin({"1", "1.0", "True", "true"})]
                specs = [s for s in selected.get("pc1_parent_spec", pd.Series(dtype=str)).map(_as_str) if s]
            if specs:
                parent_sets[target] = {
                    "selected_specs": list(dict.fromkeys(specs)),
                    "selected_sources": list(dict.fromkeys(specs)),
                    "source": "pc1_rows",
                }
        return parent_sets


    def _mci_pvalue_from_t(self, t_stat: float) -> float:
        if not np.isfinite(t_stat):
            return np.nan
        return float(min(1.0, max(0.0, math.erfc(abs(float(t_stat)) / math.sqrt(2.0)))))


    def _dedupe_specs(self, specs: Sequence[str]) -> list:
        out = []
        seen = set()
        for spec in specs or []:
            s = _as_str(spec)
            if not s or s in seen:
                continue
            out.append(s)
            seen.add(s)
        return out


    def _mci_test_summary(self, source: str, target: str, lag: int, y_parent_sources: Sequence[str], x_parent_sources: Sequence[str], df: pd.DataFrame) -> dict:
        """Run the PCMCI MCI gate for X(t-lag) -> Y(t).

        MCI conditions on the PC1-selected parents of Y and on parents of X
        shifted into the tested moment. The returned mci_val is the signed
        conditional-dependence value, not an intervention effect estimate.
        """
        missing = {
            "score": np.nan, "val": np.nan, "partial_corr": np.nan,
            "t_stat": np.nan, "p_value": np.nan, "delta_r2": np.nan,
            "n_eff": 0, "robustness": np.nan, "pass": 0,
            "controls": "", "source_parents": "",
            "conditioning_set_y": "", "conditioning_set_x": "",
            "parents_y_count": 0, "parents_x_count": 0,
            "gate_reason": "missing_column",
        }
        if source not in df.columns or target not in df.columns:
            return missing

        x = pd.to_numeric(df[source], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(df[target], errors="coerce").to_numpy(dtype=float)
        max_py = max(0, int(getattr(self.cfg, "mci_max_conds_py", getattr(self.cfg, "mci_max_target_parents", 4))))
        max_px = max(0, int(getattr(self.cfg, "mci_max_conds_px", getattr(self.cfg, "mci_source_parent_max_candidates", 3))))

        y_ctrls = []
        y_names = []
        for name in self._dedupe_specs(y_parent_sources)[:max_py]:
            ctrl, label = self._parent_spec_to_control(name, df)
            base = label.split("__lag", 1)[0] if label else ""
            if ctrl is not None and base not in {source, target} and label not in y_names:
                y_ctrls.append(ctrl)
                y_names.append(label)

        x_ctrls = []
        x_names = []
        max_x_ar = max(0, int(getattr(self.cfg, "mci_max_source_parents", 2)))
        source_arr = pd.to_numeric(df[source], errors="coerce").to_numpy(dtype=float)
        for j in range(1, max_x_ar + 1):
            if len(x_names) >= max_px:
                break
            label = f"{source}__lag{j}"
            x_ctrls.append(self._lagged_control_array(source_arr, j))
            x_names.append(label)

        for name in self._dedupe_specs(x_parent_sources):
            if len(x_names) >= max_px:
                break
            ctrl, label = self._parent_spec_to_control(name, df)
            base = label.split("__lag", 1)[0] if label else ""
            if ctrl is not None and base not in {source, target} and label not in y_names and label not in x_names:
                x_ctrls.append(ctrl)
                x_names.append(label)

        summary = _mci_signal(
            x, y, y_ctrls, x_ctrls, lag,
            ar_lags=max(1, int(getattr(self.cfg, "discovery_target_ar_lags", 2))),
        )
        score = float(summary.get("mci_score", 0.0) or 0.0)
        pc = float(summary.get("mci_partial_corr", np.nan))
        t_stat = float(summary.get("mci_t", np.nan))
        p_value = self._mci_pvalue_from_t(t_stat)
        delta_r2 = float(summary.get("mci_delta_r2", np.nan))
        n_eff = int(summary.get("mci_n_eff", 0) or 0)
        robustness = float(summary.get("mci_robustness", np.nan))

        gate_checks = []
        if not (score >= float(getattr(self.cfg, "mci_min_score", 0.52))):
            gate_checks.append("low_mci_score")
        if not (np.isfinite(pc) and abs(pc) >= float(getattr(self.cfg, "mci_min_partial_corr", 0.050))):
            gate_checks.append("low_mci_val")
        if not (np.isfinite(t_stat) and abs(t_stat) >= float(getattr(self.cfg, "mci_min_t_abs", 1.30))):
            gate_checks.append("low_mci_t")
        if not (not np.isfinite(delta_r2) or delta_r2 >= float(getattr(self.cfg, "mci_min_delta_r2", 0.006))):
            gate_checks.append("low_delta_r2")
        if not (n_eff >= int(getattr(self.cfg, "mci_min_n_eff", 24))):
            gate_checks.append("low_n_eff")
        if not (not np.isfinite(robustness) or robustness >= float(getattr(self.cfg, "mci_min_robustness", 0.45))):
            gate_checks.append("low_robustness")
        if int(summary.get("pass", 0) or 0) != 1:
            gate_checks.append("ci_helper_fail")

        survives = len(gate_checks) == 0
        return {
            "score": score,
            "val": pc if np.isfinite(pc) else np.nan,
            "partial_corr": pc if np.isfinite(pc) else np.nan,
            "t_stat": t_stat if np.isfinite(t_stat) else np.nan,
            "p_value": p_value if np.isfinite(p_value) else np.nan,
            "delta_r2": delta_r2 if np.isfinite(delta_r2) else np.nan,
            "n_eff": int(n_eff),
            "robustness": robustness if np.isfinite(robustness) else np.nan,
            "pass": int(survives),
            "controls": "|".join(y_names),
            "source_parents": "|".join(x_names),
            "conditioning_set_y": "|".join(y_names),
            "conditioning_set_x": "|".join(x_names),
            "parents_y_count": len(y_names),
            "parents_x_count": len(x_names),
            "gate_reason": "pass" if survives else "|".join(gate_checks),
        }


    def _pcmci_trend_strength(self, values) -> float:
        """Bounded trend/drift proxy used only for diagnostics."""
        try:
            arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
        except (TypeError, ValueError, OverflowError):
            return np.nan
        mask = np.isfinite(arr)
        arr = arr[mask]
        n = int(len(arr))
        if n < 12:
            return np.nan
        std = float(np.nanstd(arr))
        if not np.isfinite(std) or std <= 1e-12:
            return 0.0
        t = np.linspace(-0.5, 0.5, n)
        corr = float(np.corrcoef(t, arr)[0, 1]) if n > 2 else np.nan
        if not np.isfinite(corr):
            corr = 0.0
        mid = n // 2
        early = float(np.nanmean(arr[:mid])) if mid > 0 else np.nan
        late = float(np.nanmean(arr[mid:])) if mid < n else np.nan
        mean_shift = abs(late - early) / max(std, 1e-12) if np.isfinite(early) and np.isfinite(late) else 0.0
        return float(_clip01(0.65 * abs(corr) + 0.35 * min(1.0, mean_shift / 2.0)))


    def _pcmci_stationarity_warning(self, source: str, target: str, df: pd.DataFrame) -> dict:
        """Return audit-only drift/stationarity diagnostics for one candidate edge."""
        if source not in df.columns or target not in df.columns:
            return {
                "source_drift_score": np.nan,
                "target_drift_score": np.nan,
                "stationarity_warning": "missing_column",
            }
        src = self._pcmci_trend_strength(df[source])
        tgt = self._pcmci_trend_strength(df[target])
        combined = np.nanmax([src, tgt]) if np.isfinite(src) or np.isfinite(tgt) else np.nan
        warn_threshold = float(getattr(self.cfg, "pcmci_stationarity_warning_threshold", 0.45))
        drift_threshold = float(getattr(self.cfg, "pcmci_drift_warning_threshold", 0.35))
        if np.isfinite(combined) and combined >= warn_threshold:
            warning = "strong_nonstationarity_warning"
        elif (np.isfinite(src) and src >= drift_threshold) or (np.isfinite(tgt) and tgt >= drift_threshold):
            warning = "moderate_drift_warning"
        else:
            warning = "ok"
        return {
            "source_drift_score": float(src) if np.isfinite(src) else np.nan,
            "target_drift_score": float(tgt) if np.isfinite(tgt) else np.nan,
            "stationarity_warning": warning,
        }


    def _mci_conditioning_quality(self, selected_parents, fallback_peers, controls: str, source_parents: str) -> str:
        """Classify how credible MCI conditioning was for audit/debugging."""
        control_names = [c for c in _as_str(controls).split("|") if c]
        source_parent_names = [c for c in _as_str(source_parents).split("|") if c]
        selected_count = len([c for c in selected_parents if c])
        fallback_count = len([c for c in fallback_peers if c])
        total_controls = len(control_names) + len(source_parent_names)
        min_full = max(1, int(getattr(self.cfg, "pcmci_conditioning_min_controls_for_full", 2)))
        if selected_count >= min_full and source_parent_names:
            return "full_parent_conditioning"
        if selected_count > 0:
            return "partial_parent_conditioning"
        if fallback_count > 0 and total_controls > 0:
            return "fallback_peer_conditioning"
        if total_controls > 0:
            return "weak_conditioning"
        return "no_conditioning"


    def _apply_mci_test(self, proposals: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
        out = proposals.copy()
        out["mci_score"] = np.nan
        out["mci_val"] = np.nan
        out["mci_partial_corr"] = np.nan
        out["mci_t"] = np.nan
        out["mci_t_abs"] = np.nan
        out["mci_p_value"] = np.nan
        out["mci_pvalue"] = np.nan
        out["mci_q_value"] = np.nan
        out["mci_delta_r2"] = np.nan
        out["mci_n_eff"] = 0
        out["mci_robustness"] = np.nan
        out["mci_controls"] = ""
        out["mci_source_parents"] = ""
        out["mci_conditioning_set_y"] = ""
        out["mci_conditioning_set_x"] = ""
        out["mci_conditioning_set_used"] = ""
        out["mci_conditioning_set_size"] = 0
        out["mci_conditioning_quality"] = ""
        out["mci_conditioning_control_count"] = 0
        out["mci_conditioning_source_parent_count"] = 0
        out["mci_parents_y_count"] = 0
        out["mci_parents_x_count"] = 0
        out["mci_parent_source_mode"] = ""
        out["mci_gate_reason"] = "not_evaluated"
        out["mci_evaluated"] = 0
        out["mci_final_gate"] = 0
        out["pcmci_source_drift_score"] = np.nan
        out["pcmci_target_drift_score"] = np.nan
        out["pcmci_stationarity_warning"] = ""
        out["mci_pass"] = 0

        hard_tokens = {"LEAKAGE_BLOCK", "COLLIDER_PATTERN_PRUNE", "SENSITIVE_FEATURE", "BLOCKLISTED"}
        candidate_idx = []
        for _idx, _row in out.iterrows():
            _source = _as_str(_row.get("source", ""))
            _target = _as_str(_row.get("target_col", _row.get("target", self.cfg.target_col)))
            _blob = "|".join(_as_str(_row.get(c, "")) for c in ["exclusion_reasons", "reason_codes", "risk_flags", "drop_reason"]).upper()
            if _source and _target and _source in df.columns and _target in df.columns and not any(tok in _blob for tok in hard_tokens):
                candidate_idx.append(_idx)

        source_parent_sets = self._pc1_parent_sets_from_rows(out) if len(out) else {}
        allow_target_fallback = bool(getattr(self.cfg, "mci_allow_fallback_target_parents", False))
        source_rank_cache = {}

        for idx in candidate_idx:
            row = out.loc[idx]
            source = _as_str(row.get("source", ""))
            target = _as_str(row.get("target_col", self.cfg.target_col))
            lag = int(_safe_float(row.get("lag", np.nan), 1.0))
            selected = [s for s in _as_str(row.get("pc1_selected_parents", "")).split("|") if s]
            y_parents = selected[: max(0, int(getattr(self.cfg, "mci_max_conds_py", getattr(self.cfg, "mci_max_target_parents", 4))))]
            if not y_parents and allow_target_fallback:
                peers = []
                for jdx in candidate_idx:
                    if jdx == idx:
                        continue
                    other = out.loc[jdx]
                    if _as_str(other.get("target_col", self.cfg.target_col)) != target:
                        continue
                    if int(_safe_float(other.get("lag", np.nan), -1)) != lag:
                        continue
                    if _as_str(other.get("source", "")) == source:
                        continue
                    peers.append((jdx, float(_safe_float(other.get("selection_score", np.nan), _safe_float(other.get("priority_score", np.nan), 0.0)))))
                peers.sort(key=lambda x: x[1], reverse=True)
                y_parents = [_as_str(out.loc[jdx].get("pc1_parent_spec", "")) or _as_str(out.loc[jdx].get("source", "")) for jdx, _ in peers[: max(0, int(getattr(self.cfg, "mci_max_conds_py", 4)))]]

            x_parent_set = source_parent_sets.get(source, {}) if isinstance(source_parent_sets, dict) else {}
            x_parents = list(x_parent_set.get("selected_specs", []) or [])
            source_mode = "pc1_parent_set" if x_parents else "source_ar_only"
            if not x_parents and bool(getattr(self.cfg, "mci_source_parent_enable", True)):
                rank_key = (source, target)
                if rank_key not in source_rank_cache:
                    source_rank_cache[rank_key] = self._rank_source_parent_specs(source, target, df)
                x_parents = source_rank_cache.get(rank_key, [])
                if x_parents:
                    source_mode = "auxiliary_source_parent_screen"

            summary = self._mci_test_summary(source, target, lag, y_parents, x_parents, df)
            out.at[idx, "mci_evaluated"] = 1
            out.at[idx, "mci_score"] = float(summary.get("score", np.nan)) if np.isfinite(summary.get("score", np.nan)) else np.nan
            out.at[idx, "mci_val"] = float(summary.get("val", np.nan)) if np.isfinite(summary.get("val", np.nan)) else np.nan
            out.at[idx, "mci_partial_corr"] = float(summary.get("partial_corr", np.nan)) if np.isfinite(summary.get("partial_corr", np.nan)) else np.nan
            t_stat = float(summary.get("t_stat", np.nan)) if np.isfinite(summary.get("t_stat", np.nan)) else np.nan
            out.at[idx, "mci_t"] = t_stat
            out.at[idx, "mci_t_abs"] = abs(t_stat) if np.isfinite(t_stat) else np.nan
            p_value = float(summary.get("p_value", np.nan)) if np.isfinite(summary.get("p_value", np.nan)) else np.nan
            out.at[idx, "mci_p_value"] = p_value
            out.at[idx, "mci_pvalue"] = p_value
            out.at[idx, "mci_delta_r2"] = float(summary.get("delta_r2", np.nan)) if np.isfinite(summary.get("delta_r2", np.nan)) else np.nan
            out.at[idx, "mci_n_eff"] = int(summary.get("n_eff", 0) or 0)
            out.at[idx, "mci_robustness"] = float(summary.get("robustness", np.nan)) if np.isfinite(summary.get("robustness", np.nan)) else np.nan
            out.at[idx, "mci_controls"] = _as_str(summary.get("controls", ""))
            out.at[idx, "mci_source_parents"] = _as_str(summary.get("source_parents", ""))
            out.at[idx, "mci_conditioning_set_y"] = _as_str(summary.get("conditioning_set_y", ""))
            out.at[idx, "mci_conditioning_set_x"] = _as_str(summary.get("conditioning_set_x", ""))
            out.at[idx, "mci_parents_y_count"] = int(summary.get("parents_y_count", 0) or 0)
            out.at[idx, "mci_parents_x_count"] = int(summary.get("parents_x_count", 0) or 0)
            out.at[idx, "mci_parent_source_mode"] = source_mode
            out.at[idx, "mci_gate_reason"] = _as_str(summary.get("gate_reason", "fail"))
            mci_controls_s = _as_str(summary.get("controls", ""))
            mci_source_parents_s = _as_str(summary.get("source_parents", ""))
            conditioning_parts = []
            conditioning_parts.extend([c for c in mci_controls_s.split("|") if c])
            conditioning_parts.extend([c for c in mci_source_parents_s.split("|") if c])
            conditioning_parts = list(dict.fromkeys(conditioning_parts))
            out.at[idx, "mci_conditioning_set_used"] = "|".join(conditioning_parts)
            out.at[idx, "mci_conditioning_set_size"] = len(conditioning_parts)
            out.at[idx, "mci_conditioning_quality"] = self._mci_conditioning_quality(selected, [], mci_controls_s, mci_source_parents_s)
            out.at[idx, "mci_conditioning_control_count"] = len([c for c in mci_controls_s.split("|") if c])
            out.at[idx, "mci_conditioning_source_parent_count"] = len([c for c in mci_source_parents_s.split("|") if c])
            if bool(getattr(self.cfg, "pcmci_diagnostics_enable", True)):
                stationarity = self._pcmci_stationarity_warning(source, target, df)
                if np.isfinite(stationarity.get("source_drift_score", np.nan)):
                    out.at[idx, "pcmci_source_drift_score"] = float(stationarity.get("source_drift_score", np.nan))
                if np.isfinite(stationarity.get("target_drift_score", np.nan)):
                    out.at[idx, "pcmci_target_drift_score"] = float(stationarity.get("target_drift_score", np.nan))
                out.at[idx, "pcmci_stationarity_warning"] = _as_str(stationarity.get("stationarity_warning", ""))
            passed = int(summary.get("pass", 0) or 0)
            out.at[idx, "mci_pass"] = passed
            out.at[idx, "mci_final_gate"] = passed
            if passed != 1:
                rc = _as_str(out.at[idx, "reason_codes"]) if "reason_codes" in out.columns else ""
                if "MCI_FINAL_GATE_FAIL" not in rc.split("|"):
                    out.at[idx, "reason_codes"] = (rc + "|MCI_FINAL_GATE_FAIL").strip("|") if rc else "MCI_FINAL_GATE_FAIL"
                rf = _as_str(out.at[idx, "risk_flags"])
                if "mci_final_gate_fail" not in rf.split("|"):
                    out.at[idx, "risk_flags"] = (rf + "|mci_final_gate_fail").strip("|") if rf else "mci_final_gate_fail"
        return out


