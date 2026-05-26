from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
import warnings
from typing import Any, Dict, Tuple


def _parse_bool(value, default: bool = False) -> bool:
    """Parse booleans from JSON/YAML/env-style values without bool("false") bugs.

    Accepted truthy strings: true, 1, yes, y, on
    Accepted falsy strings: false, 0, no, n, off, none, null, empty string

    Ambiguous values fall back to `default` so config mistakes do not silently
    enable conservative/safety-sensitive flags.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"true", "1", "yes", "y", "on"}:
            return True
        if token in {"false", "0", "no", "n", "off", "none", "null", ""}:
            return False
    return default


@dataclass
class ProposalConfig:
    out_dir: str = "out"
    data_csv: str = "data.csv"
    outcome_col: str = "harm_event"
    target_col: str = "harm_event"  # legacy alias for outcome_col; edge rows still emit target
    date_col: str = "date"

    max_lag: int = 7
    min_obs: int = 40
    min_unique: int = 5
    max_nan_frac: float = 0.40
    top_k: int = 25
    discovery_mode: str = "conservative"  # conservative | balanced | exploratory
    discovery_mode_applied: bool = False
    applied_discovery_mode: str = ""

    stability_window: int = 45
    stability_stride: int = 14
    min_stability_windows: int = 3

    # proposal thresholds
    min_abs_corr: float = 0.12
    min_abs_delta_z: float = 0.15
    priority_threshold: float = 0.55
    block_leakage_hard: bool = True
    hard_block_name_patterns: Tuple[str, ...] = (
        "leak", "target", "label", "outcome", "future", "next", "post"
    )

    # hard filtering thresholds
    keep_min_priority: float = 0.54
    keep_min_causal_plausibility: float = 0.40
    keep_min_stability: float = 0.45
    keep_min_testability: float = 0.55
    keep_min_benefit: float = 0.20
    keep_max_harm: float = 0.60
    keep_max_uncertainty: float = 0.55
    no_signal_max_priority: float = 0.52
    no_signal_max_corr: float = 0.12
    no_signal_max_delta: float = 0.15

    testability_min_coverage: float = 0.55
    candidate_name_blocklist: Tuple[str, ...] = (
        "id", "uuid", "index", "timestamp", "ts", "hash"
    )
    sensitive_name_patterns: Tuple[str, ...] = (
        "suicide", "self_harm", "sex", "pregnan", "diagnos", "disease",
        "relig", "ethnic", "race", "politic", "violence", "abuse"
    )
    mediator_name_patterns: Tuple[str, ...] = (
        "latency", "retry", "queue", "memory", "tool", "approval",
        "guardrail", "rollback", "recovery", "blast_radius", "override"
    )
    actionable_high_patterns: Tuple[str, ...] = (
        "tool", "retry", "approval", "guardrail", "rollback", "override",
        "memory", "context", "latency", "action", "policy", "blast_radius"
    )
    harm_name_patterns: Tuple[str, ...] = (
        "harm", "incident", "failure", "rollback", "unsafe", "latency",
        "recovery", "blast_radius", "negative_control_outcome"
    )

    # Optional external family mapping.
    # Use this to override the built-in string heuristics in `_feature_family`
    # and `_action_family` when moving Discovery beyond the current
    # health/wellbeing-style naming conventions.
    family_map_path: str = "candidate_family_map.yaml"

    # stronger temporal conditional screen
    discovery_target_ar_lags: int = 2
    causal_min_incremental_r2: float = 0.008
    causal_min_beta_abs: float = 0.03
    orientation_min_score: float = 0.55
    orientation_as_soft_signal: bool = True
    parent_competition_min_score: float = 0.52

    # lightweight conditional-independence / skeleton pruning
    ci_prune_min_score: float = 0.50
    ci_prune_min_partial_corr: float = 0.045
    ci_prune_min_t_abs: float = 1.25
    ci_prune_max_conditioning_parents: int = 3
    # Step 184 / PCMCI cleanup B: CI prune is retained only as a
    # lightweight pre-MCI diagnostic; it must not act as an autonomous gate.
    ci_prune_as_soft_score: bool = True

    # Full PCMCI-style MCI final gate
    mci_min_score: float = 0.52
    mci_min_partial_corr: float = 0.050
    mci_min_t_abs: float = 1.30
    mci_min_delta_r2: float = 0.006
    mci_min_n_eff: int = 24
    mci_min_robustness: float = 0.45
    # Explicit source-parent controls for PCMCI-style MCI.
    # These approximate parents(X_{t-lag}) as Z_{t-lag-k} controls instead of
    # relying only on autoregressive X lags. Kept small for local-first speed.
    mci_source_parent_enable: bool = True
    mci_source_parent_max_lag: int = 2
    mci_source_parent_max_candidates: int = 3
    mci_source_parent_min_score: float = 0.18
    mci_max_target_parents: int = 4
    mci_max_source_parents: int = 2
    # Explicit PCMCI-style conditioning caps: parents(Y) and parents(X).
    mci_max_conds_py: int = 4
    mci_max_conds_px: int = 3
    # When true, MCI is the final Discovery gate, not a soft diagnostic.
    mci_as_final_gate: bool = True
    # Keep false for PCMCI purity: no peer fallback when PC1 finds no parents(Y).
    mci_allow_fallback_target_parents: bool = False
    mci_weight: float = 0.17
    mci_use_bh_fdr: bool = True
    mci_bh_alpha: float = 0.15
    mci_require_q_value: bool = True
    mci_max_q_value: float = 0.15
    # Q-values between mci_max_q_value and this bound are treated as
    # diagnostic support/fail labels, not as hard Discovery vetoes.
    mci_diagnostic_q_value: float = 0.20

    # temporal consensus / stability selection
    consensus_n_splits: int = 3
    consensus_min_segment_n: int = 36
    consensus_min_pass_rate: float = 0.60
    consensus_min_sign_consistency: float = 0.66
    consensus_weight: float = 0.12

    # explicit PC1-style parent selection layer
    pc1_enable: bool = True
    pc1_max_parents: int = 4
    pc1_min_priority: float = 0.48
    pc1_keep_history: bool = True
    pc1_as_main_selector: bool = False
    # PCMCI-style PC1 parent selection. pc1_alpha is intentionally a
    # selection regularizer, not a public causal-confidence threshold.
    pc1_alpha: float = 0.20
    pc1_max_conds_dim: int = 2
    # Step 105: conservative PC1 hardening.
    # These gates make PC1 less likely to keep weak, unstable, or duplicate-lag
    # parents before the MCI stage. They are intentionally small/local-first and
    # remain configurable from pcb.json under level25.
    pc1_min_effect_abs: float = 0.030
    pc1_stability_enable: bool = True
    pc1_stability_splits: int = 3
    pc1_stability_min_segment_n: int = 24
    pc1_stability_min_pass_rate: float = 0.55
    pc1_stability_min_sign_consistency: float = 0.60
    pc1_stability_min_score: float = 0.18
    pc1_best_lag_per_source: bool = True
    pc1_lag_top_k_per_source: int = 1

    # STEP106: audit-only diagnostics for PCMCI-style discovery.
    # These do not prune by themselves; they make PC1/MCI quality visible.
    pcmci_diagnostics_enable: bool = True
    pcmci_drift_warning_threshold: float = 0.35
    pcmci_stationarity_warning_threshold: float = 0.45
    pcmci_conditioning_min_controls_for_full: int = 2

    # step-2 output separation
    output_separate_layers: bool = True
    output_discovery_dirname: str = "discovery"
    output_validation_dirname: str = "validation"
    output_ranking_dirname: str = "ranking"

    # evidence-weighted ranking over discovery components
    selection_blend_priority: float = 0.50
    selection_blend_evidence: float = 0.50
    keep_min_selection_score: float = 0.48
    keep_min_evidence_score: float = 0.43
    track_high_selection_score: float = 0.72
    track_medium_selection_score: float = 0.58
    # Granger evidence removed in Step 74. This alias is kept only for
    # backward-compatible external configs and is not consumed by ranking.
    ev_weight_granger: float = 0.0
    ev_weight_stability: float = 0.06
    ev_weight_causal_screen: float = 0.10
    ev_weight_parent_competition: float = 0.12
    ev_weight_innovation: float = 0.10
    ev_weight_orientation: float = 0.03
    ev_weight_mci: float = 0.16
    ev_weight_temporal_consensus: float = 0.09
    ev_weight_ci: float = 0.03
    ev_weight_structural: float = 0.09
    ev_weight_pc1: float = 0.06
    # score weights
    # These weights intentionally sum to 1.0 and reflect the current product goal:
    # prioritize causal plausibility first, then user/value relevance, then how
    # validation-ready the idea is, while still reserving a meaningful but smaller
    # share for safety gating. In a higher-risk deployment, start by increasing
    # `w_safety`; in a pure exploration workflow, start by increasing `w_value`
    # or `w_ready`.
    w_causal: float = 0.34
    w_value: float = 0.26
    w_ready: float = 0.22
    w_safety: float = 0.18

    # sub-score weights
    w_signal: float = 0.40
    w_stability: float = 0.25
    w_direction: float = 0.20
    w_mechanism: float = 0.15

    # Offline prior graph input was removed from the public contract in 0.2.22.
    # Kept as an internal empty field so old in-memory callers do not crash.
    dag_path: str = ""

    # regime awareness
    regime_recent_frac: float = 0.33
    regime_min_recent_n: int = 24
    regime_shift_penalty: float = 0.75
    regime_shift_review_threshold: float = 0.55
    regime_alignment_bonus: float = 1.05

    # safety blend
    uncertainty_penalty_weight: float = 0.45
    harm_penalty_weight: float = 0.55


    def _legacy_alias_map(self) -> Dict[str, str]:
        """Return old config names and the effective parameter that replaces them."""
        return {
            "ev_weight_granger": "removed_granger_component",
            "target_col": "outcome_col",
        }

    def _effective_score_weights(self) -> Dict[str, float]:
        """Evidence score weights used by ranking after mode application.

        These weights are normalized by their runtime total before scoring. They
        intentionally do not need to sum to 1.0; adding a component changes the
        denominator, so this view exposes both raw values and the raw sum.
        """
        names = [
            "ev_weight_stability", "ev_weight_causal_screen",
            "ev_weight_parent_competition", "ev_weight_innovation",
            "ev_weight_orientation",
            "ev_weight_mci", "ev_weight_temporal_consensus",
            "ev_weight_ci", "ev_weight_structural", "ev_weight_pc1",
        ]
        weights: Dict[str, float] = {}
        for name in names:
            try:
                weights[name] = float(getattr(self, name))
            except (TypeError, ValueError):
                weights[name] = 0.0
        return weights

    def to_effective_dict(self) -> Dict[str, Any]:
        """Return a readable view of the effective Discovery configuration.

        `ProposalConfig` remains backward compatible and mutable, but this view
        is the canonical debugging/export surface: it shows values after
        `apply_discovery_mode()` has been applied, hides legacy aliases from the
        primary active-parameter section, and records which old names still map
        to newer effective parameters.
        """
        self.ensure_mode_applied(warn=False)
        raw = asdict(self)
        legacy_aliases = self._legacy_alias_map()
        meta_fields = {"discovery_mode_applied", "applied_discovery_mode"}
        active_parameters = {k: v for k, v in raw.items() if k not in legacy_aliases and k not in meta_fields}
        score_weights = self._effective_score_weights()
        score_weight_total = sum(float(v) for v in score_weights.values())
        normalized_score_weights = {
            k: (float(v) / score_weight_total if score_weight_total > 0 else 0.0)
            for k, v in score_weights.items()
        }
        return {
            "schema_version": "1.0",
            "discovery_mode": self.discovery_mode,
            "mode_application": {
                "applied": self.discovery_mode_applied,
                "applied_discovery_mode": self.applied_discovery_mode,
                "note": "apply_discovery_mode() mutates this ProposalConfig in place; ensure_mode_applied() is the compatibility guard for direct constructors.",
            },
            "active_parameters": active_parameters,
            "legacy_aliases": legacy_aliases,
            "legacy_values": {k: raw.get(k) for k in legacy_aliases if k in raw},
            "score_weights": {
                "raw": score_weights,
                "raw_sum": score_weight_total,
                "normalized": normalized_score_weights,
                "note": "Raw evidence weights are normalized by runtime total; they are not required to sum to 1.0.",
            },
            "top_level_weights": {
                "w_causal": self.w_causal,
                "w_value": self.w_value,
                "w_ready": self.w_ready,
                "w_safety": self.w_safety,
                "sum": self.w_causal + self.w_value + self.w_ready + self.w_safety,
            },
        }

    def effective_view(self) -> Dict[str, Any]:
        """Alias for `to_effective_dict()` used by callers/tests."""
        return self.to_effective_dict()

    def write_effective_config(self, path: str = None) -> str:
        """Write the effective Discovery config JSON and return its path."""
        out_path = path or os.path.join(self.out_dir, "discovery_config_effective.json")
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(self.to_effective_dict(), f, ensure_ascii=False, indent=2, sort_keys=True)
        return out_path


    def ensure_mode_applied(self, warn: bool = True) -> "ProposalConfig":
        """Ensure the discovery preset has been applied before this config is used.

        Direct construction such as `ProposalConfig(discovery_mode="balanced")`
        does not automatically run the preset mutator. This guard keeps the
        public API backward compatible while making that side effect explicit.
        """
        current_mode = str(getattr(self, "discovery_mode", "conservative") or "conservative").lower().strip()
        already_applied = bool(getattr(self, "discovery_mode_applied", False))
        applied_mode = str(getattr(self, "applied_discovery_mode", "") or "").lower().strip()
        if already_applied and applied_mode == current_mode:
            return self
        if warn:
            warnings.warn(
                "ProposalConfig discovery_mode preset was not applied yet; applying it now in place. "
                "Prefer ProposalConfig.from_dict() or ProposalConfig.load() for production construction.",
                RuntimeWarning,
                stacklevel=2,
            )
        return self.apply_discovery_mode()


    def apply_discovery_mode(self) -> "ProposalConfig":
        """Apply the discovery strictness preset by mutating this instance in place.

        Side effect: this method rewrites thresholds on `self` and marks
        `discovery_mode_applied=True`. It is intentionally idempotent for the
        current preset because it only relaxes/tightens values with min/max
        guards. Prefer `ProposalConfig.from_dict()` or `ProposalConfig.load()`
        for normal construction; direct constructors can call
        `ensure_mode_applied()` before use. Use `to_effective_dict()` to inspect
        the final values that a run will use.
        """
        mode = str(getattr(self, "discovery_mode", "conservative") or "conservative").lower().strip()
        self.discovery_mode = mode
        if mode == "balanced":
            self.top_k = max(int(self.top_k), 40)
            self.min_abs_corr = min(float(self.min_abs_corr), 0.08)
            self.min_abs_delta_z = min(float(self.min_abs_delta_z), 0.10)
            self.keep_min_priority = min(float(self.keep_min_priority), 0.44)
            self.keep_min_causal_plausibility = min(float(self.keep_min_causal_plausibility), 0.30)
            self.keep_min_stability = min(float(self.keep_min_stability), 0.30)
            self.keep_min_testability = min(float(self.keep_min_testability), 0.40)
            self.keep_max_uncertainty = max(float(self.keep_max_uncertainty), 0.70)
            self.keep_min_selection_score = min(float(self.keep_min_selection_score), 0.38)
            self.keep_min_evidence_score = min(float(self.keep_min_evidence_score), 0.34)
            self.causal_min_incremental_r2 = min(float(self.causal_min_incremental_r2), 0.004)
            self.causal_min_beta_abs = min(float(self.causal_min_beta_abs), 0.018)
            self.ci_prune_min_score = min(float(self.ci_prune_min_score), 0.42)
            self.mci_min_score = min(float(self.mci_min_score), 0.42)
            self.mci_max_q_value = max(float(self.mci_max_q_value), 0.20)
            self.mci_bh_alpha = max(float(self.mci_bh_alpha), 0.20)
            self.pc1_min_priority = min(float(self.pc1_min_priority), 0.40)
            self.pc1_alpha = max(float(self.pc1_alpha), 0.25)
        elif mode == "exploratory":
            self.top_k = max(int(self.top_k), 75)
            self.min_abs_corr = min(float(self.min_abs_corr), 0.05)
            self.min_abs_delta_z = min(float(self.min_abs_delta_z), 0.07)
            self.priority_threshold = min(float(self.priority_threshold), 0.42)
            self.keep_min_priority = min(float(self.keep_min_priority), 0.34)
            self.keep_min_causal_plausibility = min(float(self.keep_min_causal_plausibility), 0.22)
            self.keep_min_stability = min(float(self.keep_min_stability), 0.18)
            self.keep_min_testability = min(float(self.keep_min_testability), 0.30)
            self.keep_min_benefit = min(float(self.keep_min_benefit), 0.08)
            self.keep_max_harm = max(float(self.keep_max_harm), 0.78)
            self.keep_max_uncertainty = max(float(self.keep_max_uncertainty), 0.85)
            self.keep_min_selection_score = min(float(self.keep_min_selection_score), 0.28)
            self.keep_min_evidence_score = min(float(self.keep_min_evidence_score), 0.24)
            self.causal_min_incremental_r2 = min(float(self.causal_min_incremental_r2), 0.002)
            self.causal_min_beta_abs = min(float(self.causal_min_beta_abs), 0.010)
            self.orientation_min_score = min(float(self.orientation_min_score), 0.42)
            self.parent_competition_min_score = min(float(self.parent_competition_min_score), 0.34)
            self.ci_prune_min_score = min(float(self.ci_prune_min_score), 0.30)
            self.mci_min_score = min(float(self.mci_min_score), 0.30)
            self.mci_require_q_value = False
            self.mci_max_q_value = max(float(self.mci_max_q_value), 0.35)
            self.mci_bh_alpha = max(float(self.mci_bh_alpha), 0.35)
            self.consensus_min_pass_rate = min(float(self.consensus_min_pass_rate), 0.34)
            self.pc1_min_priority = min(float(self.pc1_min_priority), 0.30)
            self.pc1_alpha = max(float(self.pc1_alpha), 0.35)
        self.discovery_mode_applied = True
        self.applied_discovery_mode = mode
        return self

    @classmethod
    def from_dict(cls, d: dict) -> "ProposalConfig":
        cfg = cls()
        if not isinstance(d, dict):
            return cfg.apply_discovery_mode()
        cfg.out_dir = str(d.get("out_dir", cfg.out_dir))
        cfg.data_csv = str(d.get("data_csv", cfg.data_csv))
        cfg.outcome_col = str(d.get("outcome_col", d.get("target_col", d.get("target", cfg.outcome_col))))
        cfg.target_col = cfg.outcome_col  # keep legacy callers aligned
        cfg.date_col = str(d.get("date_col", cfg.date_col))
        lv = d.get("level25", d.get("causal", {})) if isinstance(d, dict) else {}
        removed_prior_keys = {"offline_prior_path", "dag_path"}
        for k, v in dict(lv or {}).items():
            if k in removed_prior_keys:
                continue
            if hasattr(cfg, k):
                cur = getattr(cfg, k)
                if isinstance(cur, bool):
                    setattr(cfg, k, _parse_bool(v, default=cur))
                elif isinstance(cur, int) and not isinstance(cur, bool):
                    setattr(cfg, k, int(v))
                elif isinstance(cur, float):
                    setattr(cfg, k, float(v))
                elif isinstance(cur, tuple):
                    if isinstance(v, (list, tuple)):
                        setattr(cfg, k, tuple(str(x) for x in v))
                    else:
                        setattr(cfg, k, (str(v),))
                else:
                    setattr(cfg, k, str(v))
        return cfg.apply_discovery_mode()

    @classmethod
    def load(cls, path: str = "pcb.json") -> "ProposalConfig":
        try:
            from config import load_config  # type: ignore
            return cls.from_dict(load_config(path)).apply_discovery_mode()
        except (ImportError, OSError, ValueError, TypeError):
            return cls().apply_discovery_mode()
