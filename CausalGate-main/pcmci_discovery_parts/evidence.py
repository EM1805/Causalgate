
from runtime_env import configure_scientific_runtime
configure_scientific_runtime()

from .engine_common import *
from contracts.discovery_routing import apply_signal_and_safety_scores
import numpy as np
import pandas as pd


class EvidenceScorerMixin:
    def _actionability_score(self, source: str) -> float:
        low = source.lower()
        if any(p in low for p in self.cfg.actionable_high_patterns):
            return CAL.ACTIONABILITY_HIGH
        if any(k in low for k in CAL.ACTIONABILITY_LOW_NAME_TOKENS):
            return CAL.ACTIONABILITY_LOW
        return CAL.ACTIONABILITY_BASE


    def _harm_action_from_relation(self, source: str, relation_sign: float) -> Tuple[str, str, int, str]:
        """Translate an observed source->target relation into a downside action candidate.
        Positive relation => reducing source is the harmful action for the target.
        Negative relation => increasing source is the harmful action for the target.
        """
        base = re.sub(r"[^a-zA-Z0-9_]+", "_", source.strip().lower()).strip("_") or "signal"
        if relation_sign > 0:
            return f"reduce_{base}", "reduce", -1, "reducing_source_expected_to_lower_target"
        if relation_sign < 0:
            return f"increase_{base}", "increase", -1, "increasing_source_expected_to_lower_target"
        return f"adjust_{base}", "adjust", -1, "relation_sign_unclear_downside_candidate"


    def _testability_score(self, df: pd.DataFrame, source: str, lag: int) -> Tuple[float, dict]:
        cfg = self.cfg
        s = pd.to_numeric(df[source], errors="coerce")
        y = pd.to_numeric(df[cfg.target_col], errors="coerce")
        coverage = float((s.notna() & y.notna()).mean())
        timestamp_ok = 1.0 if (cfg.date_col in df.columns and pd.to_datetime(df[cfg.date_col], errors="coerce").notna().mean() > CAL.TESTABILITY_GOOD_TS_COVERAGE) else CAL.TESTABILITY_MID_TS_SCORE
        uniq = float(s.nunique(dropna=True))
        action_defined = 1.0 if uniq >= CAL.TESTABILITY_ACTION_DEFINED_HIGH_UNIQ else CAL.TESTABILITY_ACTION_DEFINED_MID_SCORE if uniq >= CAL.TESTABILITY_ACTION_DEFINED_MID_UNIQ else CAL.TESTABILITY_ACTION_DEFINED_LOW_SCORE
        window_ok = 1.0 if int(lag) >= 1 and int(lag) <= max(1, cfg.max_lag) else 0.0
        covariate_count = 0
        for c in df.columns:
            if c in (cfg.target_col, cfg.date_col, source):
                continue
            sc = pd.to_numeric(df[c], errors="coerce")
            if sc.notna().mean() > CAL.TESTABILITY_COVARIATE_MIN_COVERAGE and sc.nunique(dropna=True) >= cfg.min_unique:
                covariate_count += 1
        cov_support = _clip01(covariate_count / CAL.TESTABILITY_COV_SUPPORT_DENOM)
        actionability = self._actionability_score(source)
        score = (
            CAL.TESTABILITY_COV_WEIGHT * _clip01((coverage - cfg.testability_min_coverage) / (1.0 - cfg.testability_min_coverage + 1e-9))
            + CAL.TESTABILITY_TIMESTAMP_WEIGHT * timestamp_ok
            + CAL.TESTABILITY_ACTION_DEFINED_WEIGHT * action_defined
            + CAL.TESTABILITY_WINDOW_WEIGHT * window_ok
            + CAL.TESTABILITY_COV_SUPPORT_WEIGHT * cov_support
            + CAL.TESTABILITY_ACTIONABILITY_WEIGHT * actionability
        )
        meta = {
            "coverage": coverage,
            "timestamp_ok": timestamp_ok,
            "action_defined": action_defined,
            "window_ok": window_ok,
            "covariate_support": cov_support,
            "actionability": actionability,
        }
        return float(score), meta


    def _multioutcome_scores(self, df: pd.DataFrame, source: str, lag: int, corr: float, delta: float, stability: float, leakage_score: float) -> dict:
        """Lightweight downside evidence summary.

        Keep this as annotation metadata rather than a dominant ranking driver.
        """
        cfg = self.cfg
        x = pd.to_numeric(df[source], errors="coerce").to_numpy(dtype=float)
        relation_strength = _norm_abs(delta if np.isfinite(delta) else corr, 1.0)
        benefit = float(_clip01(CAL.BENEFIT_RELATION_WEIGHT * relation_strength + CAL.BENEFIT_CORR_WEIGHT * _norm_abs(corr, CAL.BENEFIT_CORR_SCALE)))
        harm_candidates: List[float] = []
        harm_metrics: List[str] = []
        for c in df.columns:
            if c in (source, cfg.target_col, cfg.date_col):
                continue
            low = c.lower()
            if low == "negative_control_outcome" or any(p in low for p in cfg.harm_name_patterns):
                z = pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float)
                hz = _corr(x[:-lag], z[lag:]) if len(z) > lag + 8 else np.nan
                if np.isfinite(hz):
                    harm_candidates.append(abs(hz))
                    harm_metrics.append(c)
        harm = _clip01(float(np.nanmax(harm_candidates)) / CAL.HARM_SCALE) if harm_candidates else CAL.HARM_DEFAULT
        instability = 1.0 - _clip01(stability) if np.isfinite(stability) else CAL.INSTABILITY_DEFAULT
        leakage = _clip01(leakage_score)
        uncertainty = _clip01(CAL.UNCERTAINTY_INSTABILITY_WEIGHT * instability + CAL.UNCERTAINTY_LEAKAGE_WEIGHT * leakage)
        net = _clip01(CAL.SAFETY_NET_BENEFIT_WEIGHT * benefit + CAL.SAFETY_NET_HARM_WEIGHT * (1.0 - harm) + CAL.SAFETY_NET_UNCERTAINTY_WEIGHT * (1.0 - uncertainty))
        return {
            "benefit_score": float(benefit),
            "harm_risk_score": float(harm),
            "uncertainty_score": float(uncertainty),
            "safety_net_score": float(net),
            "safety_metrics": "|".join(harm_metrics[:5]),
        }


    def _trial_design_hints(self, source: str, lag: int, testability_meta: dict, safety_scores: dict) -> dict:
        coverage = float(testability_meta.get("coverage", 0.0))
        actionability = float(testability_meta.get("actionability", 0.5))
        window = int(max(1, lag))
        if safety_scores["uncertainty_score"] > 0.60:
            min_trials = 5
        elif safety_scores["harm_risk_score"] > 0.45:
            min_trials = 4
        else:
            min_trials = 3
        if actionability >= 0.85:
            dose = "small_daily_adjustment"
        elif actionability >= 0.60:
            dose = "moderate_step_change"
        else:
            dose = "manual_review_before_test"
        if coverage < 0.70:
            design = "sparse_data_short_window"
        elif window <= 2:
            design = "short_horizon_ab_test"
        elif window <= 5:
            design = "weekly_n_of_1"
        else:
            design = "longer_window_monitoring"
        return {
            "recommended_window_days": int(window),
            "recommended_dose": dose,
            "min_trials_recommended": int(min_trials),
            "trial_design_hint": design,
            "primary_metric": self.cfg.target_col,
        }


    def _normal_two_sided_pvalue(self, t_stat: float) -> float:
        if not np.isfinite(t_stat):
            return np.nan
        return float(min(1.0, max(0.0, math.erfc(abs(float(t_stat)) / math.sqrt(2.0)))))


    def _bh_adjust_qvalues(self, pvals: pd.Series) -> pd.Series:
        ser = pd.to_numeric(pvals, errors="coerce")
        qvals = pd.Series(np.nan, index=ser.index, dtype=float)
        valid = ser[np.isfinite(ser)].clip(lower=0.0, upper=1.0)
        m = int(len(valid))
        if m == 0:
            return qvals
        order = valid.sort_values().index.tolist()
        ordered = valid.loc[order].to_numpy(dtype=float)
        raw = ordered * float(m) / np.arange(1, m + 1, dtype=float)
        adj = np.minimum.accumulate(raw[::-1])[::-1]
        adj = np.clip(adj, 0.0, 1.0)
        qvals.loc[order] = adj
        return qvals


    def _apply_mci_multiple_testing(self, proposals: pd.DataFrame) -> pd.DataFrame:
        out = proposals.copy()
        if len(out) == 0:
            if "mci_p_value" not in out.columns:
                out["mci_p_value"] = np.nan
            if "mci_q_value" not in out.columns:
                out["mci_q_value"] = np.nan
            return out
        if "mci_p_value" not in out.columns:
            out["mci_p_value"] = np.nan
        if "mci_q_value" not in out.columns:
            out["mci_q_value"] = np.nan
        out["mci_p_value"] = out["mci_t"].apply(self._normal_two_sided_pvalue)
        out["mci_pvalue"] = out["mci_p_value"]
        if "mci_val" not in out.columns and "mci_partial_corr" in out.columns:
            out["mci_val"] = out["mci_partial_corr"]
        if bool(getattr(self.cfg, "mci_use_bh_fdr", True)):
            out["mci_q_value"] = self._bh_adjust_qvalues(out["mci_p_value"])
        else:
            out["mci_q_value"] = out["mci_p_value"]
        if bool(getattr(self.cfg, "mci_require_q_value", True)):
            max_q = float(getattr(self.cfg, "mci_max_q_value", getattr(self.cfg, "mci_bh_alpha", 0.15)))
            diagnostic_q = float(getattr(self.cfg, "mci_diagnostic_q_value", max(0.20, max_q)))
            q_values = pd.to_numeric(out["mci_q_value"], errors="coerce")
            bad_q = q_values > max_q
            for idx in out.index[bad_q.fillna(False)]:
                out.at[idx, "mci_pass"] = 0
                if "mci_final_gate" in out.columns:
                    out.at[idx, "mci_final_gate"] = 0
                if "mci_gate_reason" in out.columns:
                    prev_reason = _as_str(out.at[idx, "mci_gate_reason"])
                    out.at[idx, "mci_gate_reason"] = (prev_reason + "|q_value_fail").strip("|") if prev_reason and prev_reason != "pass" else "q_value_fail"
                rc = _as_str(out.at[idx, "reason_codes"]) if "reason_codes" in out.columns else ""
                token = "MCI_Q_DIAGNOSTIC_SUPPORT" if q_values.loc[idx] <= diagnostic_q else "MCI_Q_FINAL_GATE_FAIL"
                if token not in rc.split("|"):
                    out.at[idx, "reason_codes"] = (rc + "|" + token).strip("|") if rc else token
                rf = _as_str(out.at[idx, "risk_flags"])
                rtoken = "mci_q_diagnostic_support" if q_values.loc[idx] <= diagnostic_q else "mci_q_final_gate_fail"
                if rtoken not in rf.split("|"):
                    out.at[idx, "risk_flags"] = (rf + "|" + rtoken).strip("|") if rf else rtoken
        return out


    def _structural_risk_score(self, *, leakage_score: float, dag_review_flag: int, dag_known: int, regime_shift_score: float, risk_flags: Sequence[str], exclusion_reasons: Sequence[str]) -> float:
        score = 0.0
        if np.isfinite(leakage_score):
            score += min(CAL.STRUCT_RISK_LEAKAGE_CAP, max(0.0, float(leakage_score)) * CAL.STRUCT_RISK_LEAKAGE_WEIGHT)
        if int(dag_review_flag) == 1:
            score += CAL.STRUCT_RISK_DAG_REVIEW
        if int(dag_known) != 1:
            score += CAL.STRUCT_RISK_DAG_UNKNOWN
        if np.isfinite(regime_shift_score):
            score += min(CAL.STRUCT_RISK_REGIME_CAP, max(0.0, float(regime_shift_score)) * CAL.STRUCT_RISK_REGIME_WEIGHT)
        rf = set(risk_flags)
        ex = set(exclusion_reasons)
        if "future_stronger_than_lead" in rf or "leakage_suspect" in rf or "near_identity_to_target" in rf:
            score += CAL.STRUCT_RISK_SENSITIVE_DOMAIN
        if "LEAKAGE_BLOCK" in ex:
            score += CAL.STRUCT_RISK_HARD_EXCLUSION
        if "instability" in rf:
            score += CAL.STRUCT_RISK_DAG_UNKNOWN
        return float(_clip01(score))


    def _compute_keep_mask(self, out: pd.DataFrame) -> pd.Series:
        cfg = self.cfg
        if len(out) == 0:
            return pd.Series([], dtype=bool)
        mask = pd.Series(True, index=out.index)
        selection = pd.to_numeric(out.get("selection_score", out.get("priority_score", 0.0)), errors="coerce").fillna(0.0)
        evidence = pd.to_numeric(out.get("discovery_evidence_score", 0.0), errors="coerce").fillna(0.0)
        mask &= selection >= min(getattr(cfg, "keep_min_selection_score", 0.46), 0.40)
        mask &= evidence >= min(getattr(cfg, "keep_min_evidence_score", 0.40), 0.36)
        mask &= pd.to_numeric(out["priority_score"], errors="coerce").fillna(0.0) >= min(cfg.keep_min_priority, 0.34)
        mask &= pd.to_numeric(out["downside_action_score"], errors="coerce").fillna(0.0) >= CAL.KEEP_MIN_DOWNSIDE
        mask &= pd.to_numeric(out["testability_score"], errors="coerce").fillna(0.0) >= min(cfg.keep_min_testability, CAL.KEEP_MIN_TESTABILITY_FLOOR)
        mask &= pd.to_numeric(out.get("structural_risk_score", 0.0), errors="coerce").fillna(1.0) <= CAL.KEEP_MAX_STRUCTURAL_RISK
        if bool(getattr(cfg, "mci_as_final_gate", True)) and "mci_evaluated" in out.columns and "mci_pass" in out.columns:
            evaluated = pd.to_numeric(out["mci_evaluated"], errors="coerce").fillna(0).astype(int) == 1
            mask &= (~evaluated) | (pd.to_numeric(out["mci_pass"], errors="coerce").fillna(0).astype(int) == 1)
        if bool(getattr(cfg, "pc1_as_main_selector", False)) and "pc1_pass" in out.columns:
            mask &= pd.to_numeric(out["pc1_pass"], errors="coerce").fillna(0).astype(int) == 1
        if bool(getattr(cfg, "mci_require_q_value", True)) and "mci_q_value" in out.columns:
            max_q = float(getattr(cfg, "mci_max_q_value", getattr(cfg, "mci_bh_alpha", 0.10)))
            mask &= pd.to_numeric(out["mci_q_value"], errors="coerce").fillna(1.0) <= max_q
        if "temporal_consensus_pass" in out.columns:
            mask &= pd.to_numeric(out["temporal_consensus_pass"], errors="coerce").fillna(0).astype(int) == 1
        mask &= ~out["exclusion_reasons"].astype(str).str.contains("LEAKAGE_BLOCK", na=False)
        weak_signal = out["exclusion_reasons"].astype(str).str.contains("WEAK_SIGNAL", na=False)
        very_low_signal = pd.to_numeric(out["causal_plausibility_score"], errors="coerce").fillna(0.0) < CAL.VERY_LOW_CAUSAL_MAX
        mask &= ~(weak_signal & very_low_signal)
        return mask


    def _component_signal_strength(self, row: pd.Series) -> float:
        beta = abs(_safe_float(row.get("beta_k", np.nan), 0.0))
        delta = abs(_safe_float(row.get("delta_test", np.nan), 0.0))
        return float(_clip01(0.65 * _clip01(beta / 0.35) + 0.35 * _clip01(delta / 0.35)))


    def _refresh_evidence_and_selection(self, proposals: pd.DataFrame) -> pd.DataFrame:
        cfg = self.cfg
        evidence_df = proposals.apply(lambda r: pd.Series(self._weighted_discovery_evidence(r)), axis=1)
        for col in evidence_df.columns:
            proposals[col] = evidence_df[col]
        proposals["selection_score"] = (
            float(getattr(cfg, "selection_blend_priority", 0.55)) * pd.to_numeric(proposals["priority_score"], errors="coerce").fillna(0.0)
            + float(getattr(cfg, "selection_blend_evidence", 0.45)) * pd.to_numeric(proposals["discovery_evidence_score"], errors="coerce").fillna(0.0)
        )
        def _tier(row):
            sel = _safe_float(row.get("selection_score", np.nan), 0.0)
            evid = _safe_float(row.get("discovery_evidence_score", np.nan), 0.0)
            red = int(_safe_float(row.get("discovery_hard_red_flags", np.nan), 0.0))
            if red == 0 and sel >= float(getattr(cfg, "track_high_selection_score", 0.72)) and evid >= 0.68:
                return "high"
            if red <= 1 and sel >= float(getattr(cfg, "track_medium_selection_score", 0.58)) and evid >= 0.52:
                return "medium"
            return "low"
        proposals["discovery_confidence_tier"] = proposals.apply(_tier, axis=1)
        proposals = apply_signal_and_safety_scores(proposals, cfg=cfg)
        return proposals


    def _weighted_discovery_evidence(self, row: pd.Series) -> dict:
        cfg = self.cfg
        support_sum = 0.0
        penalty_sum = 0.0
        total_weight = 0.0
        support_votes = 0
        contradiction_votes = 0
        hard_red_flags = 0
        support_details = []
        penalty_details = []
        exclusion = _as_str(row.get("exclusion_reasons", ""))

        def add_component(name: str, score: float, weight: float, pass_flag: Optional[int] = None, fail_hard: bool = False, fail_penalty_scale: float = 0.85, weak_fail_scale: float = 0.35):
            nonlocal support_sum, penalty_sum, total_weight, support_votes, contradiction_votes, hard_red_flags
            if weight <= 0:
                return
            score = float(_clip01(score if np.isfinite(score) else 0.5))
            total_weight += weight
            if pass_flag is None:
                support = weight * score
                penalty = weight * max(0.0, 0.5 - score) * weak_fail_scale
                if score >= 0.60:
                    support_votes += 1
                    support_details.append((name, support))
                elif score <= 0.35:
                    contradiction_votes += 1
                    penalty_details.append((name, weight * max(0.20, 1.0 - score) * weak_fail_scale))
            elif int(pass_flag) == 1:
                support = weight * (0.55 + 0.45 * score)
                penalty = 0.0
                support_votes += 1
                support_details.append((name, support))
            else:
                support = weight * 0.10 * score
                penalty = weight * (fail_penalty_scale if fail_hard else 0.50) * max(0.35, 1.0 - score)
                contradiction_votes += 1
                penalty_details.append((name, penalty))
                if fail_hard:
                    hard_red_flags += 1
            support_sum += support
            penalty_sum += penalty
        add_component("stability", _safe_float(row.get("rolling_stability", np.nan), 0.0), getattr(cfg, "ev_weight_stability", 0.06), pass_flag=None, weak_fail_scale=0.30)
        add_component("causal_screen", _safe_float(row.get("causal_screen_score", np.nan), 0.0), getattr(cfg, "ev_weight_causal_screen", 0.10), pass_flag=int(_safe_float(row.get("causal_screen_pass", np.nan), 0.0)))
        add_component("parent_competition", _safe_float(row.get("parent_competition_score", np.nan), 0.0), getattr(cfg, "ev_weight_parent_competition", 0.12), pass_flag=int(_safe_float(row.get("parent_competition_pass", np.nan), 0.0)), weak_fail_scale=0.25)
        add_component("innovation", _safe_float(row.get("residual_competition_score", np.nan), 0.0), getattr(cfg, "ev_weight_innovation", 0.10), pass_flag=int(_safe_float(row.get("innovation_pass", np.nan), 0.0)))
        add_component("orientation", _safe_float(row.get("orientation_score", np.nan), 0.0), getattr(cfg, "ev_weight_orientation", 0.03), pass_flag=None, weak_fail_scale=0.15)
        # Negative-control evidence is deliberately not part of Discovery
        # ranking anymore. Estimation owns negative-control falsification and
        # writes negative_control_checks.csv/effect_estimates.csv.
        mci_score = _safe_float(row.get("mci_score", np.nan), 0.5)
        mci_pass = int(_safe_float(row.get("mci_pass", np.nan), 0.0))
        # MCI is the final PCMCI-style Discovery gate when mci_as_final_gate=True.
        # It is still Discovery evidence, not an intervention-effect estimate.
        add_component("mci", mci_score, getattr(cfg, "ev_weight_mci", getattr(cfg, "mci_weight", 0.16)), pass_flag=mci_pass, fail_hard=bool(getattr(cfg, "mci_as_final_gate", True)), fail_penalty_scale=0.85)
        add_component("temporal_consensus", _safe_float(row.get("temporal_consensus_score", np.nan), 0.0), getattr(cfg, "ev_weight_temporal_consensus", 0.09), pass_flag=int(_safe_float(row.get("temporal_consensus_pass", np.nan), 0.0)))
        ci_score = max(_safe_float(row.get("ci_prune_score", np.nan), 0.5), _safe_float(row.get("ci_signal_score", np.nan), 0.0))
        ci_pass = int(_safe_float(row.get("ci_prune_pass", np.nan), 1.0))
        # Step 184 / PCMCI cleanup B: CI prune is only a pre-MCI
        # diagnostic. Keep a very small evidence contribution for audit
        # continuity, but never let it create a hard red flag or veto.
        add_component("ci_prescreen", ci_score, getattr(cfg, "ev_weight_ci", 0.03), pass_flag=ci_pass, fail_hard=False, fail_penalty_scale=0.20)
        pc1_score = _safe_float(row.get("pc1_score", np.nan), 0.5)
        pc1_pass = int(_safe_float(row.get("pc1_pass", np.nan), 1.0)) if "PC1_PRUNE" not in exclusion else 0
        add_component("pc1", pc1_score, getattr(cfg, "ev_weight_pc1", 0.06), pass_flag=pc1_pass, fail_hard=(pc1_pass == 0), fail_penalty_scale=0.80)
        # Local pattern and nonlinear evidence were removed from Discovery core.
        # PC1 and MCI now provide the structural conditional evidence here.

        normalized_support = support_sum / max(total_weight, 1e-9)
        normalized_penalty = penalty_sum / max(total_weight, 1e-9)
        base = 0.50 + 0.55 * normalized_support - 0.75 * normalized_penalty
        if hard_red_flags >= 1:
            base -= 0.06 * hard_red_flags
        evidence_score = float(_clip01(base))
        support_details.sort(key=lambda x: x[1], reverse=True)
        penalty_details.sort(key=lambda x: x[1], reverse=True)
        return {
            "discovery_evidence_score": evidence_score,
            "discovery_support_sum": float(normalized_support),
            "discovery_penalty_sum": float(normalized_penalty),
            "discovery_support_votes": int(support_votes),
            "discovery_contradiction_votes": int(contradiction_votes),
            "discovery_hard_red_flags": int(hard_red_flags),
            "top_supporters": "|".join(name for name, _ in support_details[:4]),
            "top_penalties": "|".join(name for name, _ in penalty_details[:4]),
        }


    def _base_scores(self, corr: float, delta: float, stability: float, testability_score: float, lag: int, stability_windows: int, causal_screen_score: float = 0.0) -> Dict[str, float]:
        cfg = self.cfg
        signal_score = CAL.SIGNAL_CORR_WEIGHT * _norm_abs(corr, CAL.SIGNAL_CORR_SCALE) + CAL.SIGNAL_DELTA_WEIGHT * _norm_abs(delta, CAL.SIGNAL_DELTA_SCALE)
        stability_score = _clip01(stability)
        direction_score = CAL.DIRECTION_MATCH_SCORE if np.sign(delta if np.isfinite(delta) else corr) == np.sign(corr) else CAL.DIRECTION_MISMATCH_SCORE
        lag_shape_score = CAL.MECHANISM_NEAR_LAG_SCORE if abs(lag) <= CAL.MECHANISM_NEAR_LAG_MAX else CAL.MECHANISM_MID_LAG_SCORE if abs(lag) <= CAL.MECHANISM_MID_LAG_MAX else CAL.MECHANISM_FAR_LAG_SCORE
        mechanism_score = 0.55 * lag_shape_score + 0.45 * _clip01(causal_screen_score)
        causal_plausibility = (
            cfg.w_signal * signal_score
            + cfg.w_stability * stability_score
            + cfg.w_direction * direction_score
            + cfg.w_mechanism * mechanism_score
        )
        intervention_value = CAL.INTERVENTION_SIGNAL_WEIGHT * _norm_abs(delta if np.isfinite(delta) else corr, 1.0) + CAL.INTERVENTION_CORR_WEIGHT * _norm_abs(corr, CAL.BENEFIT_CORR_SCALE)
        validation_readiness = CAL.READINESS_TESTABILITY_WEIGHT * testability_score + CAL.READINESS_STABILITY_WEIGHT * stability_score + CAL.READINESS_WINDOWS_WEIGHT * (CAL.READINESS_WINDOWS_GOOD_SCORE if stability_windows >= cfg.min_stability_windows else CAL.READINESS_WINDOWS_PARTIAL_SCORE)
        return {
            "signal_score": signal_score,
            "stability_score": stability_score,
            "direction_score": direction_score,
            "mechanism_score": mechanism_score,
            "causal_plausibility": causal_plausibility,
            "intervention_value": intervention_value,
            "validation_readiness": validation_readiness,
        }


    def _derive_action_metadata(self, source: str, relation_sign: float, dag_ann: Dict[str, object]) -> Tuple[str, str, int, str, str]:
        action_name, action_type, expected_direction_num, downside_mechanism = self._harm_action_from_relation(source, relation_sign)
        if int(dag_ann.get("dag_known", 0)) == 1 and int(dag_ann.get("dag_intervenable", 0)) != 1:
            return "", "", 0, "", "skip_non_intervenable_dag_node"
        dag_action_name = _as_str(dag_ann.get("dag_action_name", "")).strip()
        if dag_action_name:
            action_name = dag_action_name
            action_type = "dag_action"
        expected_direction_label = "decrease"
        return action_name, action_type, expected_direction_num, downside_mechanism, expected_direction_label


    def _collect_hints(self, df: pd.DataFrame, source: str, candidates: Sequence[str], lag: int, dag_ann: Dict[str, object]) -> Dict[str, str]:
        cfg = self.cfg
        supporting = self._supporting_features(source, candidates)
        confound_hint = self._confounder_hint(source, df, candidates, lag)
        mediator_hint = self._mediator_hint(source, candidates)
        forbidden_adjustment_hint = self._forbidden_adjustment_hint(source, mediator_hint)
        if self.dag is not None and int(dag_ann.get("dag_known", 0)) == 1:
            l32_ann = self.dag.l32_annotation(source, cfg.target_col)
            confound_hint = confound_hint or _as_str(l32_ann.get("dag_adjustment_set", ""))
            forbidden_adjustment_hint = forbidden_adjustment_hint or _as_str(l32_ann.get("dag_forbidden_adjustments", ""))
        return {
            "supporting": supporting,
            "confound_hint": confound_hint,
            "mediator_hint": mediator_hint,
            "forbidden_adjustment_hint": forbidden_adjustment_hint,
        }


    def _apply_discovery_context_adjustment(
        self,
        source: str,
        action_name: str,
        adjustment_set: str,
        forbidden_adjustments: str,
        causal_plausibility: float,
        validation_readiness: float,
        discovery_ctx: DiscoveryContext,
        reason_codes: List[str],
    ) -> Tuple[float, float, List[str]]:
        """Return scores unchanged.

        The estimation-to-discovery feedback memory loop was removed in 0.2.21,
        so Discovery no longer reads historical estimation outcomes or applies
        feedback multipliers.
        """
        return causal_plausibility, validation_readiness, reason_codes


    def _classify_risks(
        self,
        source: str,
        corr: float,
        delta: float,
        stability: float,
        lag_meta: Dict[str, float],
        regime: Dict[str, float],
        test_meta: Dict[str, float],
        dag_ann: Dict[str, object],
        safety_scores: Dict[str, float | str],
        name_is_leaklike: bool,
    ) -> Tuple[List[str], List[str], List[str]]:
        cfg = self.cfg
        risk_flags: List[str] = []
        exclusion_reasons: List[str] = []
        reason_codes: List[str] = []
        name_low = source.strip().lower()
        if abs(corr) >= cfg.min_abs_corr:
            reason_codes.append("LAGGED_SIGNAL")
        if np.isfinite(delta) and abs(delta) >= cfg.min_abs_delta_z:
            reason_codes.append("DIRECTIONAL_DELTA")
        if np.isfinite(stability) and stability >= CAL.STABILITY_GOOD_THRESHOLD:
            reason_codes.append("ROLLING_STABILITY")
        if stability is not None and np.isfinite(stability):
            pass
        if _is_sensitive(source, cfg):
            risk_flags.append("sensitive_domain")
        if name_is_leaklike:
            risk_flags.append("leakage_name_pattern")
            exclusion_reasons.append("LEAKAGE_BLOCK")
        if int(dag_ann.get("dag_review_flag", 0)) == 1:
            risk_flags.append("dag_review")
        if _as_str(dag_ann.get("dag_risk_paths", "")):
            risk_flags.append("dag_risk_path")
            reason_codes.append("DAG_RISK_PATH")
        if source.strip().lower() != "negative_control_outcome" and any(p in name_low for p in cfg.hard_block_name_patterns):
            risk_flags.append("leakage_name_pattern")
        if np.isfinite(lag_meta["leakage_score"]) and lag_meta["leakage_score"] >= 1.0:
            risk_flags.append("leakage_suspect")
        if np.isfinite(lag_meta["lag0_corr"]) and abs(float(lag_meta["lag0_corr"])) >= CAL.LEAKAGE_VERY_HIGH_LAG0:
            risk_flags.append("near_identity_to_target")
        if np.isfinite(lag_meta["future_corr"]) and np.isfinite(lag_meta["past_corr"]):
            if abs(float(lag_meta["future_corr"])) > abs(float(lag_meta["past_corr"])) + CAL.LEAKAGE_FUTURE_MARGIN:
                risk_flags.append("future_stronger_than_lead")
        if np.isfinite(stability) and stability < CAL.STABILITY_BAD_THRESHOLD:
            risk_flags.append("instability")
        if test_meta["coverage"] < cfg.testability_min_coverage:
            risk_flags.append("low_coverage")
        if abs(corr) < cfg.min_abs_corr and (not np.isfinite(delta) or abs(delta) < cfg.min_abs_delta_z):
            exclusion_reasons.append("WEAK_SIGNAL")
        if (("leakage_suspect" in risk_flags) or ("leakage_name_pattern" in risk_flags) or ("future_stronger_than_lead" in risk_flags)) and cfg.block_leakage_hard:
            exclusion_reasons.append("LEAKAGE_BLOCK")
        if float(safety_scores["harm_risk_score"]) >= CAL.HARM_REVIEW_THRESHOLD:
            risk_flags.append("harm_risk")
        if float(safety_scores["uncertainty_score"]) >= CAL.UNCERTAINTY_REVIEW_THRESHOLD:
            risk_flags.append("high_uncertainty")
        if np.isfinite(regime["regime_shift_score"]) and regime["regime_shift_score"] >= cfg.regime_shift_review_threshold:
            risk_flags.append("regime_shift")
            reason_codes.append("REGIME_SHIFT_RISK")
        elif np.isfinite(regime["regime_alignment_score"]) and regime["regime_alignment_score"] >= CAL.REGIME_ALIGNMENT_GOOD_THRESHOLD:
            reason_codes.append("REGIME_STABLE")
        return risk_flags, exclusion_reasons, reason_codes


    def _adjust_scores_for_regime(
        self,
        causal_plausibility: float,
        intervention_value: float,
        downside_action_score: float,
        validation_readiness: float,
        stability_windows: int,
        regime: Dict[str, float],
    ) -> Tuple[float, float, float, float]:
        cfg = self.cfg
        if np.isfinite(regime["regime_shift_score"]) and regime["regime_shift_score"] > 0:
            causal_plausibility *= 1.0 - regime["regime_shift_score"] * (1.0 - cfg.regime_shift_penalty)
            validation_readiness *= 1.0 - regime["regime_shift_score"] * CAL.REGIME_READINESS_PENALTY
        if np.isfinite(regime["regime_alignment_score"]) and regime["regime_alignment_score"] >= CAL.REGIME_ALIGNMENT_BONUS_THRESHOLD:
            intervention_value *= cfg.regime_alignment_bonus
            downside_action_score *= cfg.regime_alignment_bonus
        validation_readiness = CAL.VALIDATION_READINESS_NOOP_BLEND * validation_readiness + 0.0 * stability_windows  # preserve scale, no behavior change
        return causal_plausibility, intervention_value, downside_action_score, validation_readiness


    def _safety_precheck(self, exclusion_reasons: Sequence[str], risk_flags: Sequence[str], safety_scores: Dict[str, float | str]) -> str:
        if "LEAKAGE_BLOCK" in exclusion_reasons:
            return "block"
        if "sensitive_domain" in risk_flags or "dag_review" in risk_flags or float(safety_scores["harm_risk_score"]) > CAL.HARM_BLOCK_THRESHOLD:
            return "review"
        if "instability" in risk_flags or "regime_shift" in risk_flags or float(safety_scores["uncertainty_score"]) > CAL.UNCERTAINTY_BLOCK_THRESHOLD:
            return "review"
        return "ok"


    def _infer_harm_hypothesis(self, metrics: SourceMetrics) -> tuple[str, str, str, str]:
        source_low = metrics.source.lower()
        action_low = metrics.action_name.lower()
        dag_paths = _as_str(metrics.dag_ann.get("dag_risk_paths", ""))
        if dag_paths:
            parts = [p for p in dag_paths.split("|") if p]
            top = parts[0]
            harm = top.split(">")[-1].strip() if ">" in top else top.strip()
            harm_node = harm or "harm_unknown"
            harm_label = harm_node.replace("harm_", "") or "unknown"
            return harm_node, harm_label, "dag_path", top
        if any(k in source_low or k in action_low for k in ("email", "external", "share", "attachment", "recipient")):
            return "harm_leakage", "leakage", "pattern", "external data handling may cross trust boundary"
        if any(k in source_low or k in action_low for k in ("delete", "drop", "purge", "remove")):
            return "harm_data_loss", "data_loss", "pattern", "destructive mutation may remove recoverable state"
        if any(k in source_low or k in action_low for k in ("permission", "access", "role", "privilege")):
            return "harm_unauthorized_access", "unauthorized_access", "pattern", "capability change may widen access surface"
        if any(k in source_low or k in action_low for k in ("config", "deploy", "rollout", "stress", "latency")):
            return "harm_operational_failure", "operational_failure", "pattern", "change may destabilize runtime behavior"
        if metrics.relation_sign < 0:
            return "harm_target_degradation", "target_degradation", "relation", "observed source increase is associated with lower target"
        return "harm_target_regression", "target_regression", "relation", "observed source reduction is associated with lower target"


    def _derive_path_payload(self, row: dict) -> dict:
        source = _as_str(row.get("source", ""))
        action_name = _as_str(row.get("action_name", ""))
        harm_node, harm_label, harm_origin, harm_rationale = self._infer_harm_hypothesis(SourceMetrics(
            source=source, lag=int(row.get("lag", 1) or 1), corr=float(row.get("beta_k", 0.0) or 0.0),
            delta=float(row.get("delta_test", 0.0) or 0.0), stability=float(row.get("rolling_stability", 0.0) or 0.0),
            stability_windows=int(row.get("stability_windows", 0) or 0), relation_sign=float(row.get("relation_sign_observed", 0.0) or 0.0),
            lag_meta={"lag0_corr":0.0,"future_corr":0.0,"past_corr":0.0,"leakage_score":0.0}, regime={"regime_shift_score":0.0,"regime_alignment_score":0.0,"recent_corr":0.0,"past_corr":0.0},
            testability_score=float(row.get("testability_score", 0.0) or 0.0), test_meta={"coverage":float(row.get("coverage", 0.0) or 0.0),"timestamp_ok":float(row.get("timestamp_ok", 0.0) or 0.0),"action_defined":float(row.get("action_defined", 0.0) or 0.0),"window_ok":float(row.get("window_ok", 0.0) or 0.0),"covariate_support":float(row.get("covariate_support", 0.0) or 0.0),"actionability":float(row.get("actionability_score", 0.0) or 0.0)},
            causal_plausibility=float(row.get("causal_plausibility_score", 0.0) or 0.0), intervention_value=float(row.get("intervention_value_score", 0.0) or 0.0), downside_action_score=float(row.get("downside_action_score", 0.0) or 0.0), validation_readiness=float(row.get("validation_readiness_score", 0.0) or 0.0), structural_risk_score=float(row.get("structural_risk_score", 0.0) or 0.0), safety_scores={"benefit_score":0.0,"harm_risk_score":float(row.get("harm_risk_score", 0.0) or 0.0),"uncertainty_score":float(row.get("uncertainty_score", 0.0) or 0.0),"safety_net_score":float(row.get("safety_net_score", 0.0) or 0.0),"safety_metrics":_as_str(row.get("safety_metrics", ""))},
            design={"recommended_window_days":int(row.get("recommended_window_days", 1) or 1),"recommended_dose":_as_str(row.get("recommended_dose", "")),"min_trials_recommended":int(row.get("min_trials_recommended", 1) or 1),"trial_design_hint":_as_str(row.get("trial_design_hint", "")),"primary_metric":_as_str(row.get("primary_metric", ""))},
            action_name=action_name, action_type=_as_str(row.get("action_type", "")), expected_direction_num=int(float(row.get("expected_direction_on_target", 0) or 0)),
            expected_direction_label=_as_str(row.get("expected_direction_label", "")), downside_mechanism=_as_str(row.get("downside_action_reason", "")),
            dag_ann={"dag_risk_paths":_as_str(row.get("dag_risk_paths", ""))}, supporting=_as_str(row.get("supporting_features", "")), confound_hint=_as_str(row.get("confounder_hint", "")),
            adjusted_confounders=[x for x in _as_str(row.get("adjusted_confounders", "")).split("|") if x], adjusted_corr=float(row.get("adjusted_corr", 0.0) or 0.0), adjusted_delta=float(row.get("adjusted_delta_test", 0.0) or 0.0),
            attenuation_ratio=float(row.get("attenuation_after_adjustment", 0.0) or 0.0), confounding_risk_score=float(row.get("confounding_risk_score", 0.0) or 0.0), adjusted_support=int(row.get("adjusted_support_n", 0) or 0), causal_effect=float(row.get("discovery_effect_proxy", row.get("causal_effect", 0.0)) or 0.0), causal_effect_std=float(row.get("discovery_effect_proxy_std", row.get("causal_effect_std", 0.0)) or 0.0), causal_effect_ci_low=float(row.get("discovery_effect_proxy_ci_low", row.get("causal_effect_ci_low", 0.0)) or 0.0), causal_effect_ci_high=float(row.get("discovery_effect_proxy_ci_high", row.get("causal_effect_ci_high", 0.0)) or 0.0), effect_persistence_score=float(row.get("effect_persistence_score", 0.0) or 0.0), ci_signal_score=float(row.get("ci_signal_score", 0.0) or 0.0), ci_raw_strength=float(row.get("ci_raw_strength", 0.0) or 0.0), ci_adjusted_strength=float(row.get("ci_adjusted_strength", 0.0) or 0.0), parent_competition_score=float(row.get("parent_competition_score", 0.0) or 0.0), parent_competition_pass=int(row.get("parent_competition_pass", 0) or 0), causal_screen_score=float(row.get("causal_screen_score", 0.0) or 0.0), incremental_r2=float(row.get("incremental_r2", 0.0) or 0.0), conditional_beta=float(row.get("conditional_beta", 0.0) or 0.0), conditional_beta_std=float(row.get("conditional_beta_std", 0.0) or 0.0), conditional_t=float(row.get("conditional_t", 0.0) or 0.0), causal_screen_pass=int(row.get("causal_screen_pass", 0) or 0), residual_competition_score=float(row.get("residual_competition_score", 0.0) or 0.0), innovation_corr=float(row.get("innovation_corr", 0.0) or 0.0), innovation_beta_std=float(row.get("innovation_beta_std", 0.0) or 0.0), innovation_t=float(row.get("innovation_t", 0.0) or 0.0), innovation_pass=int(row.get("innovation_pass", 0) or 0), orientation_score=float(row.get("orientation_score", 0.0) or 0.0), orientation_dominance=float(row.get("orientation_dominance", 0.0) or 0.0), orientation_pass=int(row.get("orientation_pass", 0) or 0), mediator_hint=_as_str(row.get("mediator_hint", "")),
            forbidden_adjustment_hint=_as_str(row.get("forbidden_adjustment_hint", "")), risk_flags=[x for x in _as_str(row.get("risk_flags", "")).split("|") if x], exclusion_reasons=[],
            reason_codes=[x for x in _as_str(row.get("reason_codes", "")).split("|") if x], priority=float(row.get("priority_score", 0.0) or 0.0), consensus_score=float(row.get("temporal_consensus_score", 0.0) or 0.0), consensus_pass_rate=float(row.get("temporal_consensus_pass_rate", 0.0) or 0.0), consensus_sign_consistency=float(row.get("temporal_consensus_sign_consistency", 0.0) or 0.0), consensus_segments=int(row.get("temporal_consensus_segments", 0) or 0), consensus_pass=int(row.get("temporal_consensus_pass", 0) or 0), safety_precheck=_as_str(row.get("safety_precheck", ""))
        ))
        mediator = next((m for m in _as_str(row.get("mediator_hint", "")).split("|") if m), "")
        if not mediator:
            mediator = next((m for m in _as_str(row.get("supporting_features", "")).split("|") if m), "")
        context_feature = next((m for m in _as_str(row.get("confounder_hint", "")).split("|") if m), "")
        if not context_feature:
            context_feature = source
        path_id = f"PD-{_action_family(action_name, self.cfg) or 'action'}-{harm_label}"
        path_statement = f"{action_name} may activate {mediator or source} and increase risk of {harm_label}"
        return {
            "candidate_kind": "path_hypothesis",
            "path_id_candidate": path_id,
            "path_statement": path_statement,
            "harm_node_candidate": harm_node,
            "harm_label": harm_label,
            "harm_hypothesis": harm_rationale,
            "harm_hypothesis_origin": harm_origin,
            "mediator_candidate": mediator,
            "context_feature_candidate": context_feature,
            "discovery_focus": "path_hypothesis",
            "offline_role": "generate_path_candidates",
        }


    def _confidence_tier(self, row: pd.Series) -> str:
        plaus = _safe_float(row.get("causal_plausibility_score", np.nan), 0.0)
        orient = _safe_float(row.get("orientation_score", np.nan), 0.0)
        cons = _safe_float(row.get("temporal_consensus_score", np.nan), 0.0)
        if plaus >= 0.78 and orient >= 0.62 and cons >= 0.62:
            return "high"
        if plaus >= 0.62 and cons >= 0.50:
            return "medium"
        return "low"


    def _infer_candidate_stratum(self, row: dict) -> tuple[str, str, str]:
        parts: List[str] = []
        rationale: List[str] = []
        action_family = _as_str(row.get("action_family", ""))
        if action_family:
            parts.append(action_family)
            rationale.append("action_family")
        harm = _as_str(row.get("harm_node_candidate", ""))
        if self.op_graph is not None and harm:
            hint = self.op_graph.path_hint_for_harm(harm)
            for hinted in list(hint.get("candidate_stratum_hints", []) or []):
                if hinted:
                    parts.append(_as_str(hinted))
                    rationale.append("graph_hint")
        context = _as_str(row.get("candidate_context", ""))
        if context and context != row.get("source"):
            parts.append(context)
            rationale.append("context_feature")
        conf = _as_str(row.get("confounder_hint", ""))
        support = _as_str(row.get("supporting_features", ""))
        if any(k in conf.lower() for k in ("environment_risk", "context_load", "tool_retry", "policy_override")):
            parts.append("high_variability_context")
            rationale.append("confounder_variability")
        if any(k in support.lower() for k in ("memory_hit", "tool_call", "context_load")) and "agent_execution_state" not in parts:
            parts.append("agent_execution_state")
            rationale.append("supporting_feature")
        seen=set(); ded=[]
        for x in parts:
            if x and x not in seen:
                seen.add(x); ded.append(x)
        stratum='|'.join(ded[:5])
        confidence='high' if len(ded) >= 3 else 'medium' if len(ded) >= 2 else 'low' if len(ded) == 1 else 'none'
        return stratum, '|'.join(rationale[:5]), confidence


    def _alternative_explanations(self, row: dict) -> tuple[str, str]:
        alts: List[str] = []
        harm = _as_str(row.get("harm_node_candidate", ""))
        if self.op_graph is not None and harm:
            hint = self.op_graph.path_hint_for_harm(harm)
            for x in list(hint.get("alternative_explanations", []) or []):
                if x:
                    alts.append(_as_str(x))
        conf = [x for x in _as_str(row.get("confounder_hint", "")).split("|") if x]
        support = [x for x in _as_str(row.get("supporting_features", "")).split("|") if x]
        if conf:
            alts.append(f"confounding_via_{conf[0]}")
        if _safe_float(row.get("regime_shift_score", float("nan")), 0.0) >= self.cfg.regime_shift_review_threshold:
            alts.append("regime_shift_explanation")
        if _safe_float(row.get("leakage_score", float("nan")), 0.0) >= CAL.LEAKAGE_REVIEW_THRESHOLD:
            alts.append("possible_information_leakage")
        if support:
            alts.append(f"mediated_by_{support[0]}")
        if not alts:
            alts.append("noise_or_unobserved_context")
        alts = list(dict.fromkeys(alts[:5]))
        tier = "high" if len(alts) >= 3 else "medium" if len(alts) == 2 else "low"
        return '|'.join(alts), tier


    def _profile_outcome(self, y: pd.Series) -> Dict[str, str]:
        s = pd.to_numeric(y, errors="coerce").dropna()
        if s.empty:
            return {"kind": "continuous", "estimand": "effect_att"}
        uniq = sorted(pd.unique(s))
        if len(uniq) <= 2 and set(float(v) for v in uniq).issubset({0.0, 1.0}):
            return {"kind": "binary", "estimand": "risk_difference_att"}
        nonneg = bool((s >= 0).all())
        vals = s.to_numpy(dtype=float)
        int_like = bool(np.allclose(vals, np.round(vals), atol=1e-8))
        if nonneg and int_like and len(uniq) <= max(12, int(np.sqrt(len(s))) + 2):
            return {"kind": "count", "estimand": "count_effect_att"}
        name = (self.cfg.target_col or "").lower()
        if any(tok in name for tok in ("latency", "duration", "time_ms", "response_time", "delay")):
            return {"kind": "continuous_time", "estimand": "mean_difference_att"}
        return {"kind": "continuous", "estimand": "effect_att"}


    def _infer_source_role(self, source: str, action_type: str, dag_ann: Optional[Dict[str, object]] = None) -> str:
        family = _feature_family(source, self.cfg)
        dag_type = _as_str((dag_ann or {}).get("dag_node_type", "")).lower()
        if dag_type in {"action", "decision", "intervention"}:
            return "decision"
        if dag_type in {"guardrail", "approval", "policy"}:
            return "guardrail"
        blob = f"{source}|{action_type}|{family}".lower()
        if family in {"guardrail", "policy_guardrail", "approval"}:
            return "guardrail"
        if family in {"action", "decision", "tooling", "retry", "rollback", "policy_action"}:
            return "decision"
        if any(tok in blob for tok in ("guardrail", "approval", "override", "review")):
            return "guardrail"
        if any(tok in blob for tok in ("action", "tool", "retry", "rollback", "novel")):
            return "decision"
        return "context"


    def _infer_outcome_role(self, outcome_col: str) -> str:
        low = (outcome_col or "").lower()
        prof = dict(self._outcome_profile or {})
        if prof.get("kind") == "binary" and any(tok in low for tok in ("harm", "incident", "failure", "rollback", "unsafe")):
            return "harm"
        if any(tok in low for tok in ("harm", "incident", "failure", "rollback", "unsafe")):
            return "harm"
        return "outcome"


    def _infer_edge_family(self, source_role: str, outcome_role: str) -> str:
        if source_role in {"decision", "guardrail"} and outcome_role in {"harm", "outcome"}:
            return f"{source_role}_to_outcome"
        return "context_to_outcome"


    def _infer_validation_design(self, source_role: str, outcome_role: str, candidate_covariates: str = "") -> str:
        has_covs = bool(_as_str(candidate_covariates).strip())
        if source_role in {"decision", "guardrail"}:
            if outcome_role == "harm":
                return "matching+did" if has_covs else "interrupted_time_series"
            return "matching" if has_covs else "diff_in_diff_proxy"
        return "backdoor_adjustment" if has_covs else "time_adjusted_regression"


    def _infer_preferred_estimand(self, validation_design: str, outcome_col: str) -> str:
        low = (outcome_col or "").lower()
        prof = dict(self._outcome_profile or {})
        explicit = _as_str(prof.get("estimand", ""))
        if explicit:
            if explicit == "effect_att" and ("harm" in low or "incident" in low or "rollback" in low or validation_design == "matching+did"):
                return "risk_difference_att"
            return explicit
        if "harm" in low or "incident" in low or "rollback" in low or validation_design == "matching+did":
            return "risk_difference_att"
        return "effect_att"


