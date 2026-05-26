"""Hypothesis generation and proposal finalization for Level 2.5 discovery.

This mixin keeps ProposalEngine focused on orchestration. It owns the logic
that turns scored source metrics into proposal rows, applies the staged
pruning/finalization passes, and assigns final discovery tracks.
"""


from runtime_env import configure_scientific_runtime
configure_scientific_runtime()

from .engine_common import *
import numpy as np
import pandas as pd
from contracts.discovery_track_rules import apply_drop_reasons, hard_drop_mask
from contracts.signal_safety_matrix import classify_signal_safety_decision


class HypothesisGeneratorMixin:
    def _layer1_generate_hypotheses(self, df: pd.DataFrame, candidates: Sequence[str], y: np.ndarray, discovery_ctx: DiscoveryContext) -> pd.DataFrame:
        rows: List[dict] = []
        for source in candidates:
            if source.strip().lower() == "negative_control_outcome":
                continue
            metrics = self._build_source_metrics(df, source, candidates, y, discovery_ctx)
            if metrics is None:
                continue
            base_row = self._build_row(metrics)
            rows.extend(self._expand_hypothesis_variants(base_row))
        return pd.DataFrame(rows)

    def _compute_track(self, row: pd.Series) -> str:
        """Classify one proposal using the explicit signal × safety matrix.

        The matrix decides the maximum permitted route. Numeric thresholds can
        still downgrade a candidate, but they cannot upgrade a blocked or
        diagnostic-only matrix cell into a stronger track.
        """

        exclusion = _as_str(row.get("exclusion_reasons", ""))
        mode = _as_str(getattr(self.cfg, "discovery_mode", "conservative")).lower() or "conservative"
        decision = classify_signal_safety_decision(
            row.get("hypothesis_signal_grade", "block"),
            row.get("safety_risk_grade", "good"),
            mode=mode,
        )
        matrix_track = _as_str(row.get("signal_safety_matrix_track", decision.get("signal_safety_matrix_track", "dropped"))) or "dropped"
        matrix_policy = _as_str(row.get("signal_safety_policy", decision.get("signal_safety_policy", "blocked")))
        safety_blocking = int(_safe_float(row.get("safety_blocking", 0), 0))

        if safety_blocking == 1 or int(decision.get("signal_safety_blocking", 0)) == 1 or matrix_track == "dropped":
            return "dropped"
        # Step 178: avoid a second hard-blocking system that bypasses the
        # explicit hypothesis_signal_grade × safety_risk_grade matrix.  Only
        # true structural safety traps remain automatic drops; ordinary failed
        # diagnostics are expressed through scores, grades, and reasons.
        if any(flag in exclusion for flag in ("LEAKAGE_BLOCK", "COLLIDER_PATTERN_PRUNE", "SENSITIVE_FEATURE", "BLOCKLISTED")):
            return "dropped"
        if bool(getattr(self.cfg, "mci_as_final_gate", True)) and int(_safe_float(row.get("mci_evaluated", 0), 0)) == 1:
            if int(_safe_float(row.get("mci_pass", 0), 0)) != 1:
                return "dropped"
            if bool(getattr(self.cfg, "mci_require_q_value", True)):
                max_q = float(getattr(self.cfg, "mci_max_q_value", getattr(self.cfg, "mci_bh_alpha", 0.15)))
                qv = _safe_float(row.get("mci_q_value", np.nan), np.nan)
                if (not np.isfinite(qv)) or qv > max_q:
                    return "dropped"

        priority = _safe_float(row.get("priority_score", np.nan), 0.0)
        selection = _safe_float(row.get("selection_score", np.nan), priority)
        evidence = _safe_float(row.get("discovery_evidence_score", np.nan), 0.0)
        plaus = _safe_float(row.get("causal_plausibility_score", np.nan), 0.0)
        downside = _safe_float(row.get("downside_action_score", np.nan), 0.0)
        structural = _safe_float(row.get("structural_risk_score", np.nan), 1.0)
        conf_risk = _safe_float(row.get("confounding_risk_score", np.nan), 0.0)
        ci = _safe_float(row.get("ci_signal_score", np.nan), 0.0)
        # Placebo is no longer a Discovery track gate. Estimation owns
        # falsification and writes the authoritative estimation falsification status.
        parent = _safe_float(row.get("parent_competition_score", np.nan), 0.0)

        high_ok = (
            selection >= max(getattr(self.cfg, "track_high_selection_score", 0.72), CAL.TRACK_HIGH_PRIORITY_FLOOR)
            and evidence >= 0.68
            and plaus >= CAL.TRACK_HIGH_PLAUSIBILITY
            and downside >= CAL.TRACK_HIGH_DOWNSIDE
            and structural <= CAL.TRACK_HIGH_STRUCTURAL_MAX
            and conf_risk <= CAL.TRACK_HIGH_CONF_RISK_MAX
            and ci >= CAL.TRACK_HIGH_CI
            and parent >= CAL.TRACK_HIGH_PARENT
        )
        medium_ok = (
            selection >= max(getattr(self.cfg, "track_medium_selection_score", 0.58), CAL.TRACK_EXPLORATORY_PLAUSIBILITY)
            and evidence >= 0.50
            and downside >= CAL.TRACK_EXPLORATORY_DOWNSIDE
            and structural <= CAL.TRACK_EXPLORATORY_STRUCTURAL_MAX
        )
        weak_ok = (
            evidence >= 0.42
            and plaus >= CAL.TRACK_WEAK_PLAUSIBILITY
            and (downside >= CAL.TRACK_WEAK_DOWNSIDE or _as_str(row.get("mediator_hint", "")) or _as_str(row.get("confounder_hint", "")))
        )

        if matrix_track == "high_confidence" and high_ok:
            return "high_confidence"
        if matrix_track in ("high_confidence", "exploratory") and medium_ok:
            return "exploratory"
        if matrix_track in ("high_confidence", "exploratory", "weak_structured") and weak_ok:
            return "weak_structured"
        if matrix_policy in ("diagnostic_only", "observe_more") and matrix_track == "weak_structured":
            # Keep low-risk diagnostic cells visible only when they have at least
            # minimal signal; otherwise they remain dropped.
            if evidence >= 0.30 or plaus >= CAL.TRACK_WEAK_PLAUSIBILITY:
                return "weak_structured"
        return "dropped"

    def _deduplicate_proposals(self, proposals: pd.DataFrame) -> pd.DataFrame:
        if len(proposals) == 0:
            return proposals

        ranked = proposals.sort_values(
            ["selection_score", "discovery_evidence_score", "priority_score", "testability_score"],
            ascending=[False, False, False, False],
            na_position="last",
        ).reset_index(drop=True)

        exact = ranked.drop_duplicates().copy()

        semantic_keys = [
            "source",
            "target_col",
            "lag",
            "hypothesis_variant",
            "candidate_context",
            "discovery_focus",
            "action_name",
            "expected_direction",
        ]
        subset = [c for c in semantic_keys if c in exact.columns]
        if subset:
            exact = exact.drop_duplicates(subset=subset, keep="first").copy()

        return exact.reset_index(drop=True)


    def _finalize_proposals(self, proposals: pd.DataFrame, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        cfg = self.cfg
        if len(proposals) == 0:
            empty = self._empty_outputs()
            return empty, empty.copy()

        proposals = self._refresh_evidence_and_selection(proposals)
        proposals = self._deduplicate_proposals(proposals)
        proposals["proposal_id"] = [f"H2-{i+1:05d}" for i in range(len(proposals))]
        proposals["keep_flag"] = self._compute_keep_mask(proposals).astype(int)
        proposals["discovery_track"] = proposals.apply(self._compute_track, axis=1)
        proposals = self._apply_conditional_independence_pruning(proposals, df)
        proposals["keep_flag"] = self._compute_keep_mask(proposals).astype(int)
        proposals["discovery_track"] = proposals.apply(self._compute_track, axis=1)
        proposals = self._apply_pc1_pruning(proposals, df)
        proposals["keep_flag"] = self._compute_keep_mask(proposals).astype(int)
        proposals["discovery_track"] = proposals.apply(self._compute_track, axis=1)
        proposals = self._apply_mci_test(proposals, df)
        proposals = self._apply_mci_multiple_testing(proposals)
        proposals["keep_flag"] = self._compute_keep_mask(proposals).astype(int)
        proposals["discovery_track"] = proposals.apply(self._compute_track, axis=1)
        proposals = self._refresh_evidence_and_selection(proposals)
        proposals["keep_flag"] = self._compute_keep_mask(proposals).astype(int)
        proposals["discovery_track"] = proposals.apply(self._compute_track, axis=1)
        hard_dropped = hard_drop_mask(proposals, cfg)
        exploratory_reclass = (proposals["discovery_track"] == "dropped") & (proposals["keep_flag"] == 1) & (~hard_dropped)
        proposals.loc[exploratory_reclass, "discovery_track"] = "exploratory"
        weak_reclass = (proposals["discovery_track"] == "dropped") & (pd.to_numeric(proposals["causal_plausibility_score"], errors="coerce").fillna(0.0) >= CAL.TRACK_WEAK_PLAUSIBILITY) & (~hard_dropped)
        proposals.loc[weak_reclass, "discovery_track"] = "weak_structured"
        proposals = apply_drop_reasons(proposals, cfg)
        if str(getattr(cfg, "discovery_mode", "conservative")).lower() == "exploratory":
            soft_drop = (proposals["discovery_track"] == "dropped") & (~hard_dropped)
            score_ok = pd.to_numeric(proposals.get("selection_score", 0.0), errors="coerce").fillna(0.0) >= float(getattr(cfg, "keep_min_selection_score", 0.28))
            evidence_ok = pd.to_numeric(proposals.get("discovery_evidence_score", 0.0), errors="coerce").fillna(0.0) >= float(getattr(cfg, "keep_min_evidence_score", 0.24))
            plaus_ok = pd.to_numeric(proposals.get("causal_plausibility_score", 0.0), errors="coerce").fillna(0.0) >= 0.18
            proposals.loc[soft_drop & (score_ok | evidence_ok | plaus_ok), "discovery_track"] = "exploratory"
            proposals.loc[soft_drop & ~(score_ok | evidence_ok | plaus_ok), "discovery_track"] = "weak_structured"

        # Step 178: keep_flag should reflect the final routing decision after
        # matrix/diagnostic reclassification.  Earlier keep_mask values remain
        # useful internally, but exporting kept rows with keep_flag=0 is
        # confusing for downstream consumers.
        proposals["keep_flag"] = (proposals["discovery_track"] != "dropped").astype(int)
        proposals["strength"] = proposals["selection_score"].astype(float)
        proposals["strength_semantics"] = "legacy_alias_for_selection_score"
        proposals["selection_score_semantics"] = "priority_score_blended_with_component_discovery_evidence"
        proposals = self._deduplicate_proposals(proposals)
        proposals["proposal_id"] = [f"H2-{i+1:05d}" for i in range(len(proposals))]

        kept = proposals[proposals["discovery_track"] != "dropped"].copy().reset_index(drop=True)
        if cfg.top_k > 0:
            kept = kept.head(int(cfg.top_k * 3)).copy()
        kept["insight_id"] = [f"I2-{i+1:05d}" for i in range(len(kept))]
        return proposals, kept

