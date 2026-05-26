from runtime_env import configure_scientific_runtime
configure_scientific_runtime()

from .engine_common import *
import numpy as np
import pandas as pd


class Pc1Mixin:
    """PCMCI-style PC1 parent-selection mixin.

    PC1 is intentionally limited to parent-set discovery.  It does not estimate
    causal effects and it does not create public insights by itself.  The output
    of this layer is a lag-aware parent set per target plus transparent audit
    fields consumed by MCI, SCM and estimation bridges.
    """

    def _pc1_parent_spec(self, source: str, lag: int) -> str:
        return _parent_spec(source, lag)

    def _pc1_parse_parent_spec(self, spec: str) -> tuple[str, int]:
        return _parse_parent_spec(spec)

    def _pc1_lagged_control_array(self, values: np.ndarray, lag: int) -> np.ndarray:
        return _lagged_control_array(values, lag)

    def _pc1_parent_spec_to_control(
        self,
        spec: str,
        df: pd.DataFrame,
    ) -> tuple[np.ndarray | None, str]:
        return _parent_spec_to_control(spec, df)

    def _pc1_pvalue_from_t(self, t_stat: float) -> float:
        if not np.isfinite(t_stat):
            return np.nan
        return float(min(1.0, max(0.0, math.erfc(abs(float(t_stat)) / math.sqrt(2.0)))))

    def _pc1_candidate_effect_abs(self, row) -> float:
        """Return a conservative absolute effect proxy for PC1 pre-screening only."""
        vals = []
        for col in (
            "causal_effect_std", "conditional_beta_std", "innovation_beta_std",
            "adjusted_delta_test", "delta_test", "beta_k", "lag0_corr",
        ):
            try:
                v = _safe_float(row.get(col, np.nan), np.nan)
            except (TypeError, ValueError, OverflowError):
                v = np.nan
            if np.isfinite(v):
                vals.append(abs(float(v)))
        return float(max(vals)) if vals else 0.0

    def _pc1_effect_abs_series(self, frame: pd.DataFrame) -> pd.Series:
        """Vectorized version of the PC1 effect proxy used for pre-screening."""
        cols = [
            c for c in (
                "causal_effect_std",
                "conditional_beta_std",
                "innovation_beta_std",
                "adjusted_delta_test",
                "delta_test",
                "beta_k",
                "lag0_corr",
            )
            if c in frame.columns
        ]
        if not cols:
            return pd.Series(0.0, index=frame.index, dtype=float)
        numeric = frame[cols].apply(pd.to_numeric, errors="coerce").abs()
        return numeric.max(axis=1).fillna(0.0).astype(float)

    def _pc1_stability_summary(self, source: str, target: str, lag: int, df: pd.DataFrame) -> dict:
        """Bounded stability diagnostic for a candidate parent X(t-lag) -> Y(t)."""
        if source not in df.columns or target not in df.columns:
            return {"pass_rate": np.nan, "sign_consistency": np.nan, "n_segments": 0, "pass": 1}
        if not bool(getattr(self.cfg, "pc1_stability_enable", True)):
            return {"pass_rate": np.nan, "sign_consistency": np.nan, "n_segments": 0, "pass": 1}
        n = int(len(df))
        splits = max(1, int(getattr(self.cfg, "pc1_stability_splits", 3)))
        min_n = max(int(lag) + 8, int(getattr(self.cfg, "pc1_stability_min_segment_n", 24)))
        if n < max(min_n, splits * max(8, int(lag) + 4)):
            return {"pass_rate": np.nan, "sign_consistency": np.nan, "n_segments": 0, "pass": 1}
        pass_count = 0
        signs = []
        used = 0
        for seg in np.array_split(np.arange(n), splits):
            if len(seg) < min_n:
                continue
            part = df.iloc[seg]
            x = pd.to_numeric(part[source], errors="coerce").to_numpy(dtype=float)
            y = pd.to_numeric(part[target], errors="coerce").to_numpy(dtype=float)
            if len(x) <= lag + 8 or len(y) <= lag + 8:
                continue
            summary = _temporal_conditional_signal(
                x,
                y,
                [],
                lag,
                ar_lags=max(1, int(getattr(self.cfg, "discovery_target_ar_lags", 2))),
            )
            score = float(summary.get("screen_score", summary.get("score", 0.0)) or 0.0)
            pc = float(summary.get("partial_corr", summary.get("beta_std", np.nan)))
            if not np.isfinite(pc):
                pc = float(summary.get("conditional_beta_std", 0.0) or 0.0)
            used += 1
            if score >= float(getattr(self.cfg, "pc1_stability_min_score", 0.18)):
                pass_count += 1
            if np.isfinite(pc) and abs(pc) > 1e-12:
                signs.append(1 if pc > 0 else -1)
        if used <= 0:
            return {"pass_rate": np.nan, "sign_consistency": np.nan, "n_segments": 0, "pass": 1}
        pass_rate = float(pass_count / used)
        if signs:
            pos = sum(1 for x in signs if x > 0)
            neg = sum(1 for x in signs if x < 0)
            sign_consistency = float(max(pos, neg) / max(1, len(signs)))
        else:
            sign_consistency = 0.0
        passed = (
            pass_rate >= float(getattr(self.cfg, "pc1_stability_min_pass_rate", 0.55))
            and sign_consistency >= float(getattr(self.cfg, "pc1_stability_min_sign_consistency", 0.60))
        )
        return {
            "pass_rate": pass_rate,
            "sign_consistency": sign_consistency,
            "n_segments": int(used),
            "pass": int(passed),
        }

    def _pc1_prepare_active_candidates(self, active: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
        """Apply bounded pre-screens before formal PC1 parent selection."""
        if active.empty:
            return active
        out = active.copy()
        out["_pc1_effect_abs"] = self._pc1_effect_abs_series(out)
        min_effect = float(getattr(self.cfg, "pc1_min_effect_abs", 0.030))
        if min_effect > 0:
            out = out[out["_pc1_effect_abs"] >= min_effect].copy()
        if out.empty:
            return out
        if bool(getattr(self.cfg, "pc1_stability_enable", True)):
            pass_rates = []
            sign_cons = []
            seg_counts = []
            passes = []
            for _, row in out.iterrows():
                source = _as_str(row.get("source", ""))
                target = _as_str(row.get("target_col", self.cfg.target_col)) or self.cfg.target_col
                lag = int(_safe_float(row.get("lag", np.nan), 1.0))
                summary = self._pc1_stability_summary(source, target, lag, df)
                pass_rates.append(float(summary.get("pass_rate", np.nan)) if np.isfinite(summary.get("pass_rate", np.nan)) else np.nan)
                sign_cons.append(float(summary.get("sign_consistency", np.nan)) if np.isfinite(summary.get("sign_consistency", np.nan)) else np.nan)
                seg_counts.append(int(summary.get("n_segments", 0) or 0))
                passes.append(int(summary.get("pass", 1) or 0))
            out["_pc1_stability_pass_rate"] = pass_rates
            out["_pc1_stability_sign_consistency"] = sign_cons
            out["_pc1_stability_segments"] = seg_counts
            out["_pc1_stability_pass"] = passes
            out = out[out["_pc1_stability_pass"].astype(int) == 1].copy()
        if out.empty:
            return out
        if bool(getattr(self.cfg, "pc1_best_lag_per_source", True)):
            top_k = max(1, int(getattr(self.cfg, "pc1_lag_top_k_per_source", 1)))
            sort_cols = [c for c in ["priority_score", "discovery_evidence_score", "selection_score", "score"] if c in out.columns]
            if sort_cols:
                out = out.sort_values(sort_cols, ascending=[False] * len(sort_cols)).copy()
            keep_idx = []
            for _, grp in out.groupby(["target_col", "source"], dropna=False):
                keep_idx.extend(list(grp.head(top_k).index))
            out = out.loc[keep_idx].copy()
        return out

    def _pc1_parent_selection_summary(self, source: str, target: str, lag: int, control_specs: Sequence[str], df: pd.DataFrame) -> dict:
        """Test whether X(t-lag) remains a plausible parent of Y(t) under controls."""
        if source not in df.columns or target not in df.columns:
            return {"score": np.nan, "partial_corr": np.nan, "t_stat": np.nan, "p_value": np.nan, "pass": 0, "controls": "", "subset_size": 0}
        x = pd.to_numeric(df[source], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(df[target], errors="coerce").to_numpy(dtype=float)
        ctrls = []
        keep_names = []
        for spec in control_specs:
            ctrl, label = self._pc1_parent_spec_to_control(spec, df)
            base, _lag = self._pc1_parse_parent_spec(label)
            if ctrl is not None and base not in {source, target} and label not in keep_names:
                ctrls.append(ctrl)
                keep_names.append(label)
        summary = _conditional_independence_signal(
            x,
            y,
            ctrls,
            max(1, int(lag)),
            ar_lags=max(1, int(getattr(self.cfg, "discovery_target_ar_lags", 2))),
        )
        pc = float(summary.get("partial_corr", np.nan))
        t_stat = float(summary.get("t_stat", np.nan))
        score = float(summary.get("ci_score", summary.get("screen_score", 0.0)) or 0.0)
        p_value = self._pc1_pvalue_from_t(t_stat)
        alpha = float(getattr(self.cfg, "pc1_alpha", 0.20))
        min_score = float(getattr(self.cfg, "ci_prune_min_score", 0.50))
        min_pc = float(getattr(self.cfg, "ci_prune_min_partial_corr", 0.045))
        min_t = float(getattr(self.cfg, "ci_prune_min_t_abs", 1.25))
        survives = (
            int(summary.get("pass", 0) or 0) == 1
            and np.isfinite(pc)
            and abs(pc) >= min_pc
            and np.isfinite(t_stat)
            and abs(t_stat) >= min_t
            and score >= min_score
            and (not np.isfinite(p_value) or p_value <= alpha)
        )
        return {
            "score": score,
            "partial_corr": pc if np.isfinite(pc) else np.nan,
            "t_stat": t_stat if np.isfinite(t_stat) else np.nan,
            "p_value": p_value if np.isfinite(p_value) else np.nan,
            "pass": int(survives),
            "controls": "|".join(keep_names),
            "subset_size": len(keep_names),
        }

    def _pc1_candidate_records(self, proposals: pd.DataFrame, df: pd.DataFrame) -> tuple[pd.DataFrame, set[int]]:
        active = proposals.copy()
        if active.empty:
            return active.iloc[0:0].copy(), set()
        active = active[active["discovery_track"] != "dropped"].copy()
        if active.empty:
            return active, set()
        prepared = self._pc1_prepare_active_candidates(active, df)
        return prepared, set(prepared.index.tolist())

    def _build_pc1_parent_sets(
        self,
        proposals: pd.DataFrame,
        df: pd.DataFrame,
        active: pd.DataFrame | None = None,
    ) -> dict:
        """Return formal lag-aware PC1 parent sets keyed by target.

        Shape:
          {target: {selected_specs, selected_meta, candidates, pval_max, val_min, iterations}}
        """
        if active is None:
            active, _eligible_idx = self._pc1_candidate_records(proposals, df)
        else:
            active = active.copy()
        if active.empty:
            return {}
        parent_sets: dict = {}
        max_keep = max(1, int(getattr(self.cfg, "pc1_max_parents", 4)))
        max_conds_dim = max(0, int(getattr(self.cfg, "pc1_max_conds_dim", 2)))
        min_priority = float(getattr(self.cfg, "pc1_min_priority", 0.48))
        sort_cols = [c for c in ["priority_score", "discovery_evidence_score", "selection_score", "score"] if c in active.columns]
        for target, grp in active.groupby("target_col", dropna=False, sort=False):
            target = _as_str(target) or self.cfg.target_col
            if sort_cols:
                grp = grp.sort_values(sort_cols, ascending=[False] * len(sort_cols)).copy()
            candidates = []
            seen_specs = set()
            for idx, row in grp.iterrows():
                source = _as_str(row.get("source", ""))
                lag = max(1, int(_safe_float(row.get("lag", np.nan), 1.0)))
                spec = self._pc1_parent_spec(source, lag)
                priority = float(_safe_float(row.get("priority_score", np.nan), 0.0))
                if not source or source not in df.columns or spec in seen_specs or priority < min_priority:
                    continue
                seen_specs.add(spec)
                candidates.append({
                    "idx": idx,
                    "source": source,
                    "lag": lag,
                    "spec": spec,
                    "priority": priority,
                    "effect_abs": float(row.get("_pc1_effect_abs", np.nan)) if np.isfinite(row.get("_pc1_effect_abs", np.nan)) else np.nan,
                    "stability_pass_rate": float(row.get("_pc1_stability_pass_rate", np.nan)) if np.isfinite(row.get("_pc1_stability_pass_rate", np.nan)) else np.nan,
                    "stability_sign_consistency": float(row.get("_pc1_stability_sign_consistency", np.nan)) if np.isfinite(row.get("_pc1_stability_sign_consistency", np.nan)) else np.nan,
                    "history": [],
                    "removed": False,
                    "remove_reason": "",
                })
            if not candidates:
                parent_sets[target] = {"selected_specs": [], "selected_meta": [], "candidates": [], "pval_max": np.nan, "val_min": np.nan, "iterations": 0}
                continue
            active_specs = [c["spec"] for c in candidates]
            iterations = 0
            for cond_dim in range(0, max_conds_dim + 1):
                if not active_specs:
                    break
                # Reorder by the latest retained value where available, otherwise priority.
                score_lookup = {}
                for c in candidates:
                    latest = c["history"][-1] if c["history"] else {}
                    val = abs(float(latest.get("partial_corr", np.nan))) if np.isfinite(latest.get("partial_corr", np.nan)) else np.nan
                    score_lookup[c["spec"]] = val if np.isfinite(val) else float(c.get("priority", 0.0))
                active_specs = sorted(active_specs, key=lambda s: score_lookup.get(s, 0.0), reverse=True)
                for cand in candidates:
                    if cand["spec"] not in active_specs:
                        continue
                    control_specs = [s for s in active_specs if s != cand["spec"]]
                    control_specs = control_specs[:cond_dim]
                    summary = self._pc1_parent_selection_summary(cand["source"], target, cand["lag"], control_specs, df)
                    iterations += 1
                    hist = {
                        "cond_dim": int(cond_dim),
                        "controls": _as_str(summary.get("controls", "")),
                        "subset_size": int(summary.get("subset_size", 0) or 0),
                        "score": float(summary.get("score", np.nan)) if np.isfinite(summary.get("score", np.nan)) else np.nan,
                        "partial_corr": float(summary.get("partial_corr", np.nan)) if np.isfinite(summary.get("partial_corr", np.nan)) else np.nan,
                        "t_stat": float(summary.get("t_stat", np.nan)) if np.isfinite(summary.get("t_stat", np.nan)) else np.nan,
                        "p_value": float(summary.get("p_value", np.nan)) if np.isfinite(summary.get("p_value", np.nan)) else np.nan,
                        "pass": int(summary.get("pass", 0) or 0),
                    }
                    cand["history"].append(hist)
                    if hist["pass"] != 1:
                        cand["removed"] = True
                        cand["remove_reason"] = f"independent_at_cond_dim_{cond_dim}"
                        active_specs = [s for s in active_specs if s != cand["spec"]]
                if len(active_specs) <= max_keep and cond_dim >= max_conds_dim:
                    break
            survivors = [c for c in candidates if c["spec"] in active_specs and not c.get("removed")]
            def _candidate_strength(c):
                vals = [abs(float(h.get("partial_corr", np.nan))) for h in c.get("history", []) if np.isfinite(h.get("partial_corr", np.nan))]
                return (min(vals) if vals else 0.0, float(c.get("priority", 0.0)))
            survivors = sorted(survivors, key=_candidate_strength, reverse=True)
            selected = survivors[:max_keep]
            selected_specs = [c["spec"] for c in selected]
            selected_meta = []
            for rank, cand in enumerate(selected):
                hist = cand.get("history", [])
                pvals = [float(h.get("p_value", np.nan)) for h in hist if np.isfinite(h.get("p_value", np.nan))]
                vals = [abs(float(h.get("partial_corr", np.nan))) for h in hist if np.isfinite(h.get("partial_corr", np.nan))]
                last = hist[-1] if hist else {}
                selected_meta.append({
                    "idx": cand["idx"],
                    "source": cand["source"],
                    "lag": cand["lag"],
                    "spec": cand["spec"],
                    "controls": _as_str(last.get("controls", "")),
                    "subset_size": int(last.get("subset_size", 0) or 0),
                    "score": float(last.get("score", np.nan)) if np.isfinite(last.get("score", np.nan)) else np.nan,
                    "partial_corr": float(last.get("partial_corr", np.nan)) if np.isfinite(last.get("partial_corr", np.nan)) else np.nan,
                    "t_stat": float(last.get("t_stat", np.nan)) if np.isfinite(last.get("t_stat", np.nan)) else np.nan,
                    "p_value": float(last.get("p_value", np.nan)) if np.isfinite(last.get("p_value", np.nan)) else np.nan,
                    "pval_max": max(pvals) if pvals else np.nan,
                    "val_min": min(vals) if vals else np.nan,
                    "effect_abs": cand.get("effect_abs", np.nan),
                    "stability_pass_rate": cand.get("stability_pass_rate", np.nan),
                    "stability_sign_consistency": cand.get("stability_sign_consistency", np.nan),
                    "iteration": int(rank),
                    "iterations": len(hist),
                })
            all_p = [m["pval_max"] for m in selected_meta if np.isfinite(m.get("pval_max", np.nan))]
            all_v = [m["val_min"] for m in selected_meta if np.isfinite(m.get("val_min", np.nan))]
            parent_sets[target] = {
                "selected_specs": selected_specs,
                "selected_sources": selected_specs,  # compatibility: now lag-aware specs
                "selected_meta": selected_meta,
                "candidates": candidates,
                "pval_max": max(all_p) if all_p else np.nan,
                "val_min": min(all_v) if all_v else np.nan,
                "iterations": int(iterations),
            }
        return parent_sets

    def _apply_pc1_pruning(self, proposals: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
        """Attach formal PC1 parent-set metadata to proposal rows.

        PC1 still runs candidate-by-candidate for the conditional tests, but the
        final row annotations are batched to avoid thousands of ``out.at`` writes
        on large proposal tables.
        """
        out = proposals.copy()
        defaults = {
            "pc1_parent_spec": "",
            "pc1_selected_parents": "",
            "pc1_parent_set_all": "",
            "pc1_is_selected_parent": 0,
            "pc1_parent_rank": -1,
            "pc1_parent_support_status": "not_evaluated",
            "pc1_parent_iteration": -1,
            "pc1_iterations": 0,
            "pc1_controls": "",
            "pc1_subset_size": 0,
            "pc1_score": np.nan,
            "pc1_partial_corr": np.nan,
            "pc1_t": np.nan,
            "pc1_p_value": np.nan,
            "pc1_pval_max": np.nan,
            "pc1_val_min": np.nan,
            "pc1_alpha": float(getattr(self.cfg, "pc1_alpha", 0.20)),
            "pc1_max_conds_dim": int(getattr(self.cfg, "pc1_max_conds_dim", 2)),
            "pc1_pass": 0,
            "pc1_effect_abs": np.nan,
            "pc1_stability_pass_rate": np.nan,
            "pc1_stability_sign_consistency": np.nan,
            "pc1_stability_segments": 0,
            "pc1_gate_pass": 0,
            "pc1_gate_reason": "not_evaluated",
        }
        for col, default in defaults.items():
            out[col] = default

        candidate_idx = out.index[out["discovery_track"] != "dropped"].tolist()
        eligible_frame, pc1_eligible_idx = self._pc1_candidate_records(out, df)
        parent_sets = self._build_pc1_parent_sets(out, df, active=eligible_frame)
        eligible_lookup = eligible_frame.to_dict("index") if not eligible_frame.empty else {}
        effect_lookup = self._pc1_effect_abs_series(out.loc[candidate_idx]) if candidate_idx else pd.Series(dtype=float)
        updates: dict = {}

        for idx in candidate_idx:
            row = out.loc[idx]
            source = _as_str(row.get("source", ""))
            target = _as_str(row.get("target_col", self.cfg.target_col)) or self.cfg.target_col
            lag = max(1, int(_safe_float(row.get("lag", np.nan), 1.0)))
            spec = self._pc1_parent_spec(source, lag) if source else ""
            update = {"pc1_parent_spec": spec}

            prepared_row = eligible_lookup.get(idx, {})
            effect_abs = float(effect_lookup.get(idx, 0.0)) if len(effect_lookup) else 0.0
            update["pc1_effect_abs"] = effect_abs

            if prepared_row:
                pass_rate = _safe_float(prepared_row.get("_pc1_stability_pass_rate", np.nan), np.nan)
                sign_cons = _safe_float(prepared_row.get("_pc1_stability_sign_consistency", np.nan), np.nan)
                segments = int(_safe_float(prepared_row.get("_pc1_stability_segments", 0), 0))
                stability_pass = int(_safe_float(prepared_row.get("_pc1_stability_pass", 1), 1))
            else:
                stability = self._pc1_stability_summary(source, target, lag, df)
                pass_rate = _safe_float(stability.get("pass_rate", np.nan), np.nan)
                sign_cons = _safe_float(stability.get("sign_consistency", np.nan), np.nan)
                segments = int(stability.get("n_segments", 0) or 0)
                stability_pass = int(stability.get("pass", 1) or 0)
            if np.isfinite(pass_rate):
                update["pc1_stability_pass_rate"] = float(pass_rate)
            if np.isfinite(sign_cons):
                update["pc1_stability_sign_consistency"] = float(sign_cons)
            update["pc1_stability_segments"] = segments

            if idx not in pc1_eligible_idx:
                reasons = []
                if effect_abs < float(getattr(self.cfg, "pc1_min_effect_abs", 0.030)):
                    reasons.append("WEAK_EFFECT")
                if stability_pass != 1:
                    reasons.append("UNSTABLE_SIGNAL")
                reason = "+".join(reasons or ["PRE_SCREEN_NOT_ELIGIBLE"])
                update["pc1_gate_reason"] = reason
                update["pc1_parent_support_status"] = "pre_screen_rejected"
                if bool(getattr(self.cfg, "pc1_as_main_selector", False)):
                    ex = _as_str(row.get("exclusion_reasons", ""))
                    rf = _as_str(row.get("risk_flags", ""))
                    update["exclusion_reasons"] = (
                        ex + "|PC1_PARENT_SELECTION_FAIL"
                    ).strip("|") if ex else "PC1_PARENT_SELECTION_FAIL"
                    update["risk_flags"] = (
                        rf + "|pc1_parent_selection_fail"
                    ).strip("|") if rf else "pc1_parent_selection_fail"
                updates[idx] = update
                continue

            parent_info = parent_sets.get(target, {})
            selected_specs = [s for s in parent_info.get("selected_specs", []) if s]
            selected_for_row = [s for s in selected_specs if s != spec]
            update["pc1_parent_set_all"] = "|".join(selected_specs)
            update["pc1_selected_parents"] = "|".join(selected_for_row)
            update["pc1_iterations"] = int(parent_info.get("iterations", 0) or 0)
            if np.isfinite(parent_info.get("pval_max", np.nan)):
                update["pc1_pval_max"] = float(parent_info.get("pval_max"))
            if np.isfinite(parent_info.get("val_min", np.nan)):
                update["pc1_val_min"] = float(parent_info.get("val_min"))

            selected_meta = parent_info.get("selected_meta", [])
            matched_meta = next(
                (meta for meta in selected_meta if _as_str(meta.get("spec", "")) == spec),
                None,
            )
            if matched_meta is None:
                update["pc1_parent_support_status"] = "not_in_parent_set"
                update["pc1_gate_reason"] = "NOT_SELECTED_BY_PC1"
                if bool(getattr(self.cfg, "pc1_as_main_selector", False)):
                    ex = _as_str(row.get("exclusion_reasons", ""))
                    rf = _as_str(row.get("risk_flags", ""))
                    update["exclusion_reasons"] = (
                        ex + "|PC1_PARENT_SELECTION_FAIL"
                    ).strip("|") if ex else "PC1_PARENT_SELECTION_FAIL"
                    update["risk_flags"] = (
                        rf + "|pc1_parent_selection_fail"
                    ).strip("|") if rf else "pc1_parent_selection_fail"
                updates[idx] = update
                continue

            update.update({
                "pc1_is_selected_parent": 1,
                "pc1_pass": 1,
                "pc1_gate_pass": 1,
                "pc1_gate_reason": "selected_parent",
                "pc1_parent_support_status": "selected_parent",
                "pc1_controls": _as_str(matched_meta.get("controls", "")),
                "pc1_subset_size": int(matched_meta.get("subset_size", 0) or 0),
            })
            try:
                iteration = int(matched_meta.get("iteration", -1))
            except (TypeError, ValueError, OverflowError):
                iteration = -1
            update["pc1_parent_iteration"] = iteration
            update["pc1_parent_rank"] = int(iteration + 1) if iteration >= 0 else -1
            for src_key, dst_key in [
                ("score", "pc1_score"),
                ("partial_corr", "pc1_partial_corr"),
                ("t_stat", "pc1_t"),
                ("p_value", "pc1_p_value"),
                ("pval_max", "pc1_pval_max"),
                ("val_min", "pc1_val_min"),
            ]:
                val = matched_meta.get(src_key, np.nan)
                update[dst_key] = float(val) if np.isfinite(val) else np.nan
            update["pc1_iterations"] = int(
                matched_meta.get("iterations", update.get("pc1_iterations", 0)) or 0
            )
            updates[idx] = update

        if updates:
            update_frame = pd.DataFrame.from_dict(updates, orient="index")
            for col in update_frame.columns:
                out.loc[update_frame.index, col] = update_frame[col]
        return out

