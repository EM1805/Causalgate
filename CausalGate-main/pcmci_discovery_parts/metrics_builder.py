from .engine_common import *
import numpy as np
import pandas as pd


class MetricsBuilderMixin:
    def _build_source_metrics(
        self,
        df: pd.DataFrame,
        source: str,
        candidates: Sequence[str],
        y: np.ndarray,
        discovery_ctx: DiscoveryContext,
    ) -> Optional[SourceMetrics]:
        cfg = self.cfg
        intervenible, name_is_leaklike, keep_for_guardrails, _ = self._validate_source_name(source)
        if (not intervenible) and (not keep_for_guardrails):
            return None

        stats = self._compute_source_statistics(df, source, y)
        if stats is None:
            return None
        lag = int(stats["lag"])
        corr = float(stats["corr"])
        delta = float(stats["delta"])
        stability = float(stats["stability"])
        stability_windows = int(stats["stability_windows"])
        lag_meta = stats["lag_meta"]
        regime = stats["regime"]
        relation_sign = float(stats["relation_sign"])

        dag_ann = self._resolve_dag_annotation(source)
        action_name, action_type, expected_direction_num, downside_mechanism, expected_direction_label = self._derive_action_metadata(source, relation_sign, dag_ann)
        if not action_name:
            return None

        testability_score, test_meta = self._testability_score(df, source, lag)
        base_scores = self._base_scores(corr, delta, stability, testability_score, lag, stability_windows, causal_screen_score=0.0)
        signal_score = float(base_scores["signal_score"])
        stability_score = float(base_scores["stability_score"])
        direction_score = float(base_scores["direction_score"])
        mechanism_score = float(base_scores["mechanism_score"])
        causal_plausibility = float(base_scores["causal_plausibility"])
        intervention_value = float(base_scores["intervention_value"])
        downside_action_score = _clip01(CAL.DOWNSIDE_INTERVENTION_WEIGHT * intervention_value + CAL.DOWNSIDE_TESTABILITY_WEIGHT * testability_score)
        validation_readiness = float(base_scores["validation_readiness"])

        hints = self._collect_hints(df, source, candidates, lag, dag_ann)
        adjustment = self._adjustment_summary(source, df, candidates, lag, corr, delta)
        ci_summary = self._conditional_signal_summary(source, df, candidates, lag, corr, delta)
        selected_controls = list(ci_summary.get("controls", [])) or list(adjustment.get("confounders", []))
        causal_screen = self._causal_screen_summary(source, df, selected_controls, lag)
        orientation = self._orientation_summary(source, df, selected_controls, lag)
        consensus = self._temporal_consensus_summary(source, df, selected_controls, lag)
        if ci_summary["controls"]:
            adjustment["confounders"] = list(dict.fromkeys(list(adjustment["confounders"]) + list(ci_summary["controls"])))[:6]
            adjustment["adjusted_corr"] = ci_summary["adjusted_corr"]
            adjustment["adjusted_delta"] = ci_summary["adjusted_delta"]
            adjustment["adjusted_support"] = max(int(adjustment.get("adjusted_support", 0) or 0), int(ci_summary["n_eff"]))
            raw_strength = max(abs(corr) + CAL.RAW_STRENGTH_DELTA_WEIGHT * abs(delta if np.isfinite(delta) else 0.0), 1e-6)
            attenuation = 1.0 - min(1.0, float(ci_summary["adjusted_strength"]) / raw_strength)
            adjustment["attenuation_ratio"] = float(_clip01(attenuation))
            adjustment["confounding_risk_score"] = float(_clip01(CAL.CONFOUNDING_RISK_ATTENUATION_WEIGHT * attenuation + (1.0 - CAL.CONFOUNDING_RISK_ATTENUATION_WEIGHT) * (1.0 - ci_summary["parent_competition_score"])))
        if adjustment["confounders"] and not hints["confound_hint"]:
            hints["confound_hint"] = "|".join(adjustment["confounders"])
        safety_scores = self._multioutcome_scores(df, source, lag, corr, delta, stability, lag_meta["leakage_score"])
        risk_flags, exclusion_reasons, reason_codes = self._classify_risks(
            source,
            corr,
            delta,
            stability,
            lag_meta,
            regime,
            test_meta,
            dag_ann,
            safety_scores,
            name_is_leaklike,
        )
        if hints["confound_hint"]:
            reason_codes.append("COMMON_CAUSE_RISK")
        if hints["mediator_hint"]:
            reason_codes.append("MEDIATOR_PATH_HINT")
        adj_corr = adjustment["adjusted_corr"]
        adj_delta = adjustment["adjusted_delta"]
        attenuation = adjustment["attenuation_ratio"]
        conf_risk = adjustment["confounding_risk_score"]
        adjusted_signal = 0.0
        if np.isfinite(adj_corr):
            adjusted_signal = CAL.SIGNAL_CORR_WEIGHT * _norm_abs(adj_corr, CAL.SIGNAL_CORR_SCALE) + CAL.SIGNAL_DELTA_WEIGHT * _norm_abs(adj_delta if np.isfinite(adj_delta) else 0.0, CAL.SIGNAL_DELTA_SCALE)
            causal_plausibility = CAL.ADJUSTMENT_BLEND_CAUSAL_PRIOR * causal_plausibility + CAL.ADJUSTMENT_BLEND_ADJUSTED_SIGNAL * adjusted_signal
            intervention_value = CAL.ADJUSTMENT_BLEND_INTERVENTION_PRIOR * intervention_value + CAL.ADJUSTMENT_BLEND_INTERVENTION_ADJUSTED * adjusted_signal
            if abs(adj_corr) < max(CAL.ADJUSTMENT_LOW_ABS_CORR, abs(corr) * CAL.ADJUSTMENT_LOW_RELATIVE_CORR):
                reason_codes.append("ATTENUATES_AFTER_ADJUSTMENT")
            elif abs(adj_corr) >= max(CAL.ADJUSTMENT_HIGH_ABS_CORR, abs(corr) * CAL.ADJUSTMENT_HIGH_RELATIVE_CORR):
                reason_codes.append("SURVIVES_ADJUSTMENT")
        if int(ci_summary["survives_conditioning"]) == 1:
            reason_codes.append("SURVIVES_CONDITIONAL_TEST")
        else:
            reason_codes.append("FAILS_CONDITIONAL_TEST")
            exclusion_reasons.append("FAILS_CONDITIONAL_TEST")
        if int(causal_screen.get("pass", 0)) == 1:
            reason_codes.append("AR_CONDITIONAL_SIGNAL")
        else:
            # Step 180: AR conditional is diagnostic, not a hard exclusion.
            reason_codes.append("AR_CONDITIONAL_DIAGNOSTIC_FAIL")
            risk_flags.append("ar_conditional_soft_fail")
        orientation_soft = bool(getattr(self.cfg, "orientation_as_soft_signal", True))
        if int(orientation.get("pass", 0)) == 1:
            reason_codes.append("ORIENTATION_DOMINANT")
        else:
            if not orientation_soft:
                exclusion_reasons.append("WEAK_EDGE_ORIENTATION")
            risk_flags.append("orientation_weak")
        if int(consensus.get("pass", 0)) == 1:
            reason_codes.append("TEMPORAL_CONSENSUS_PASS")
        else:
            exclusion_reasons.append("TEMPORAL_CONSENSUS_FAIL")
            risk_flags.append("temporal_consensus_fail")
        causal_plausibility = CAL.CAUSAL_BLEND_BASE * causal_plausibility + CAL.CAUSAL_BLEND_CI * ci_summary["ci_signal_score"] + CAL.CAUSAL_BLEND_PARENT * ci_summary["parent_competition_score"]
        causal_plausibility = 0.64 * causal_plausibility + 0.16 * float(causal_screen.get("screen_score", 0.0) or 0.0) + 0.04 * float(orientation.get("orientation_score", 0.0) or 0.0) + 0.10 * float(ci_summary.get("parent_competition_score", 0.0) or 0.0) + 0.06 * float(consensus.get("score", 0.0) or 0.0)
        causal_plausibility *= (1.0 - CAL.CAUSAL_CONF_RISK_PENALTY * conf_risk)
        downside_action_score *= (1.0 - CAL.DOWNSIDE_CONF_RISK_PENALTY * conf_risk)
        validation_readiness = CAL.READINESS_SUPPORT_BLEND_BASE * validation_readiness + CAL.READINESS_SUPPORT_BLEND_SUPPORT * _clip01(adjustment["adjusted_support"] / max(CAL.READINESS_SUPPORT_DENOM_MIN, float(cfg.min_obs)))
        validation_readiness = (1.0 - float(getattr(cfg, "consensus_weight", 0.12))) * validation_readiness + float(getattr(cfg, "consensus_weight", 0.12)) * float(consensus.get("score", 0.0) or 0.0)
        causal_plausibility, intervention_value, downside_action_score, validation_readiness = self._adjust_scores_for_regime(
            causal_plausibility,
            intervention_value,
            downside_action_score,
            validation_readiness,
            stability_windows,
            regime,
        )
        causal_plausibility, validation_readiness, reason_codes = self._apply_discovery_context_adjustment(
            source,
            action_name,
            "|".join(adjustment["confounders"]),
            hints["forbidden_adjustment_hint"],
            causal_plausibility,
            validation_readiness,
            discovery_ctx,
            reason_codes,
        )

        design = self._trial_design_hints(source, lag, test_meta, safety_scores)
        structural_risk_score = self._structural_risk_score(
            leakage_score=lag_meta["leakage_score"],
            dag_review_flag=int(dag_ann.get("dag_review_flag", 0)),
            dag_known=int(dag_ann.get("dag_known", 0)),
            regime_shift_score=regime.get("regime_shift_score", np.nan),
            risk_flags=risk_flags,
            exclusion_reasons=exclusion_reasons,
        )
        effect_strength = _clip01(abs(adjustment["causal_effect_std"])) if np.isfinite(adjustment["causal_effect_std"]) else 0.0
        effect_persistence = _clip01(adjustment["effect_persistence_score"]) if np.isfinite(adjustment["effect_persistence_score"]) else 0.0
        adjusted_persistence = _clip01(CAL.PERSISTENCE_ATTENUATION_WEIGHT * (1.0 - adjustment["attenuation_ratio"]) + CAL.PERSISTENCE_EFFECT_WEIGHT * effect_persistence)
        # Top-level Discovery priority now uses the explicit ProposalConfig
        # weights (w_causal/w_value/w_ready/w_safety).  The older calibration
        # constants remain as small diagnostic bonuses, but they no longer hide
        # or override the top-level product semantics.
        w_causal = max(0.0, float(getattr(cfg, "w_causal", 0.34)))
        w_value = max(0.0, float(getattr(cfg, "w_value", 0.26)))
        w_ready = max(0.0, float(getattr(cfg, "w_ready", 0.22)))
        w_safety = max(0.0, float(getattr(cfg, "w_safety", 0.18)))
        w_total = w_causal + w_value + w_ready + w_safety
        if w_total <= 0.0:
            w_causal, w_value, w_ready, w_safety, w_total = 0.34, 0.26, 0.22, 0.18, 1.0
        w_causal, w_value, w_ready, w_safety = (
            w_causal / w_total,
            w_value / w_total,
            w_ready / w_total,
            w_safety / w_total,
        )
        value_axis = _clip01(0.55 * downside_action_score + 0.45 * float(intervention_value or 0.0))
        readiness_axis = _clip01(0.70 * testability_score + 0.30 * adjusted_persistence)
        safety_axis = _clip01(1.0 - structural_risk_score)
        top_level_priority = _clip01(
            w_causal * causal_plausibility
            + w_value * value_axis
            + w_ready * readiness_axis
            + w_safety * safety_axis
        )
        diagnostic_bonus = _clip01(
            0.04 * effect_strength
            + 0.04 * ci_summary["parent_competition_score"]
            + 0.02 * float(orientation.get("orientation_score", 0.0) or 0.0)
            + 0.03 * float(consensus.get("score", 0.0) or 0.0)
        )
        priority = _clip01(top_level_priority + diagnostic_bonus)
        safety_precheck = self._safety_precheck(exclusion_reasons, risk_flags, safety_scores)

        return SourceMetrics(
            source=source,
            lag=lag,
            corr=corr,
            delta=delta,
            stability=stability,
            stability_windows=stability_windows,
            relation_sign=relation_sign,
            lag_meta=lag_meta,
            regime=regime,
            testability_score=float(testability_score),
            test_meta=test_meta,
            causal_plausibility=float(causal_plausibility),
            intervention_value=float(intervention_value),
            downside_action_score=float(downside_action_score),
            validation_readiness=float(validation_readiness),
            structural_risk_score=float(structural_risk_score),
            safety_scores=safety_scores,
            design=design,
            action_name=action_name,
            action_type=action_type,
            expected_direction_num=expected_direction_num,
            expected_direction_label=expected_direction_label,
            downside_mechanism=downside_mechanism,
            dag_ann=dag_ann,
            supporting=hints["supporting"],
            confound_hint=hints["confound_hint"],
            adjusted_confounders=adjustment["confounders"],
            adjusted_corr=float(adjustment["adjusted_corr"]),
            adjusted_delta=float(adjustment["adjusted_delta"]),
            attenuation_ratio=float(adjustment["attenuation_ratio"]),
            confounding_risk_score=float(adjustment["confounding_risk_score"]),
            adjusted_support=int(adjustment["adjusted_support"]),
            causal_effect=float(adjustment["causal_effect"]),
            causal_effect_std=float(adjustment["causal_effect_std"]),
            causal_effect_ci_low=float(adjustment["causal_effect_ci_low"]),
            causal_effect_ci_high=float(adjustment["causal_effect_ci_high"]),
            effect_persistence_score=float(adjustment["effect_persistence_score"]),
            ci_signal_score=float(ci_summary["ci_signal_score"]),
            ci_raw_strength=float(ci_summary["raw_strength"]),
            ci_adjusted_strength=float(ci_summary["adjusted_strength"]),
            parent_competition_score=float(ci_summary["parent_competition_score"]),
            parent_competition_pass=int(ci_summary.get("parent_competition_pass", 0) or 0),
            causal_screen_score=float(causal_screen.get("screen_score", 0.0) or 0.0),
            incremental_r2=float(causal_screen.get("incremental_r2", np.nan)),
            conditional_beta=float(causal_screen.get("conditional_beta", np.nan)),
            conditional_beta_std=float(causal_screen.get("conditional_beta_std", np.nan)),
            conditional_t=float(causal_screen.get("conditional_t", np.nan)),
            causal_screen_pass=int(causal_screen.get("pass", 0) or 0),
            residual_competition_score=float(ci_summary.get("innovation_score", 0.0) or 0.0),
            innovation_corr=float(ci_summary.get("innovation_corr", np.nan)),
            innovation_beta_std=float(ci_summary.get("innovation_beta_std", np.nan)),
            innovation_t=float(ci_summary.get("innovation_t", np.nan)),
            innovation_pass=int(ci_summary.get("innovation_pass", 0) or 0),
            orientation_score=float(orientation.get("orientation_score", 0.0) or 0.0),
            orientation_dominance=float(orientation.get("dominance", np.nan)),
            orientation_pass=int(orientation.get("pass", 0) or 0),
            consensus_score=float(consensus.get("score", np.nan)),
            consensus_pass_rate=float(consensus.get("pass_rate", np.nan)),
            consensus_sign_consistency=float(consensus.get("sign_consistency", np.nan)),
            consensus_segments=int(consensus.get("segments", 0) or 0),
            consensus_pass=int(consensus.get("pass", 0) or 0),
            mediator_hint=hints["mediator_hint"],
            forbidden_adjustment_hint=hints["forbidden_adjustment_hint"],
            risk_flags=risk_flags,
            exclusion_reasons=exclusion_reasons,
            reason_codes=reason_codes,
            priority=float(priority),
            safety_precheck=safety_precheck,
        )
