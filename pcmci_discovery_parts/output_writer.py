
from runtime_env import configure_scientific_runtime
configure_scientific_runtime()

from .engine_common import *
from contracts.discovery_bridge import (
    write_bridge_from_insights,
    write_identification_assets,
    write_scm_assets,
)
import numpy as np
import pandas as pd


MAIN_DISCOVERY_SCORE_COLUMNS = [
    "priority_score",
    "discovery_evidence_score",
    "selection_score",
    "hypothesis_signal_score",
    "safety_risk_score",
]

GATE_AUDIT_COLUMNS = [
    "proposal_id",
    "source",
    "target",
    "lag",
    "priority_score",
    "discovery_evidence_score",
    "selection_score",
    "hypothesis_signal_score",
    "hypothesis_signal_grade",
    "safety_risk_score",
    "safety_risk_grade",
    "signal_safety_cell",
    "signal_safety_matrix_track",
    "signal_safety_blocking",
    "discovery_track",
    "keep_flag",
    "mci_status",
    "mci_t_abs",
    "mci_n_eff",
    "confounder_status",
    "ar_conditional_status",
    "final_decision",
    "drop_reason",
    "reason_codes",
    "risk_flags",
]

DISCOVERY_SCORING_COLUMNS = [
    "proposal_id",
    "source",
    "target",
    "lag",
    *MAIN_DISCOVERY_SCORE_COLUMNS,
    "hypothesis_signal_grade",
    "safety_risk_grade",
    "signal_safety_matrix_track",
    "signal_safety_blocking",
    "discovery_track",
    "keep_flag",
]

PC1_PARENT_CANDIDATE_COLUMNS = [
    "proposal_id",
    "target_col",
    "target",
    "source",
    "lag",
    "pc1_parent_spec",
    "pc1_is_selected_parent",
    "pc1_parent_rank",
    "pc1_parent_iteration",
    "pc1_parent_support_status",
    "pc1_parent_set_all",
    "pc1_selected_parents",
    "pc1_controls",
    "pc1_subset_size",
    "pc1_score",
    "pc1_partial_corr",
    "pc1_t",
    "pc1_p_value",
    "pc1_pval_max",
    "pc1_val_min",
    "pc1_iterations",
    "pc1_alpha",
    "pc1_max_conds_dim",
    "pc1_effect_abs",
    "pc1_stability_pass_rate",
    "pc1_stability_sign_consistency",
    "pc1_stability_segments",
    "pc1_gate_pass",
    "pc1_gate_reason",
    "priority_score",
    "discovery_evidence_score",
    "selection_score",
    "discovery_track",
    "keep_flag",
]

PCMCI_SCM_BRIDGE_COLUMNS = [
    "insight_id",
    "proposal_id",
    "source",
    "target",
    "lag",
    "edge_type",
    "parent_set",
    "pc1_parent_spec",
    "pc1_is_selected_parent",
    "pc1_parent_rank",
    "pc1_parent_iteration",
    "pc1_parent_support_status",
    "pc1_p_value",
    "pc1_pval_max",
    "pc1_val_min",
    "pc1_iterations",
    "conditioning_set_used",
    "conditioning_set_size",
    "conditioning_quality",
    "mci_status",
    "mci_val",
    "mci_partial_corr",
    "mci_t_abs",
    "mci_p_value",
    "mci_pvalue",
    "mci_q_value",
    "mci_n_eff",
    "mci_conditioning_set_y",
    "mci_conditioning_set_x",
    "mci_parents_y_count",
    "mci_parents_x_count",
    "mci_final_gate",
    "mci_gate_reason",
    "pc1_parent_support",
    "confounder_status",
    "ar_conditional_status",
    "signal_safety_matrix_track",
    "signal_safety_blocking",
    "scm_role_hint",
    "identification_priority",
    "discovery_track",
    "keep_flag",
    "drop_reason",
    "risk_flags",
]

# Public ranked insight contract.  Step 3 keeps insights_level2.csv as a
# minimal human/audit summary.  Rich handoff payloads remain in
# discovery_estimation_bridge.csv and discovery/pcmci_scm_bridge.csv.
PUBLIC_INSIGHT_COLUMNS = [
    "insight_id",
    "proposal_id",
    "source",
    "target",
    "lag",
    "pc1_status",
    "pc1_parent_spec",
    "pc1_p_value",
    "pc1_pval_max",
    "pc1_val_min",
    "mci_status",
    "mci_pvalue",
    "mci_q_value",
    "mci_val",
    "support_n",
    "discovery_strength",
    "discovery_track",
    "gate_status",
    "reason",
    "causal_interpretation_level",
]



class OutputWriterMixin:

    def _audit_status_from_row(self, row: pd.Series, kind: str) -> str:
        """Return compact gate status labels for audit outputs.

        The audit intentionally keeps only the main Discovery scores and clear
        pass/diagnostic/fail labels so downstream users do not need to inspect
        dozens of legacy score columns.
        """
        reason_blob = "|".join(str(row.get(c, "") or "") for c in [
            "reason_codes", "risk_flags", "exclusion_reasons", "drop_reason",
            "hypothesis_signal_reason_codes", "safety_risk_reason_codes",
        ]).upper()
        if kind == "mci":
            n_eff = pd.to_numeric(pd.Series([row.get("mci_n_eff", np.nan)]), errors="coerce").iloc[0]
            score = pd.to_numeric(pd.Series([row.get("mci_score", np.nan)]), errors="coerce").iloc[0]
            q_val = pd.to_numeric(pd.Series([row.get("mci_q_value", np.nan)]), errors="coerce").iloc[0]
            passed = row.get("mci_pass", np.nan)
            try:
                if np.isfinite(float(passed)) and int(float(passed)) == 1:
                    return "pass"
            except (TypeError, ValueError):
                pass
            if np.isfinite(n_eff) and float(n_eff) > 0:
                if "MCI_Q_DIAGNOSTIC_SUPPORT" in reason_blob:
                    return "diagnostic_support"
                if np.isfinite(q_val):
                    return "diagnostic_fail"
                if np.isfinite(score):
                    return "diagnostic_fail"
                return "diagnostic"
            return "not_evaluated"
        if kind == "confounder":
            if "CONFOUNDER" in reason_blob:
                return "diagnostic_risk"
            risk = pd.to_numeric(pd.Series([row.get("confounding_risk_score", np.nan)]), errors="coerce").iloc[0]
            if np.isfinite(risk) and float(risk) > 0.35:
                return "diagnostic_risk"
            return "clear"
        if kind == "ar":
            if "AR_CONDITIONAL" in reason_blob or "FAILS_AR_CONDITIONAL_SCREEN" in reason_blob:
                return "diagnostic_fail"
            passed = row.get("causal_screen_pass", np.nan)
            try:
                if np.isfinite(float(passed)):
                    return "pass" if int(float(passed)) == 1 else "diagnostic_fail"
            except (TypeError, ValueError):
                pass
            return "not_evaluated"
        return "unknown"

    def _with_existing_columns(self, frame: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
        existing = [c for c in columns if c in frame.columns]
        if len(frame) == 0:
            return pd.DataFrame(columns=columns)
        out = frame.copy()
        for c in columns:
            if c not in out.columns:
                out[c] = ""
        return out[columns].copy()

    def _pc1_parent_sets_frame(self, proposals: pd.DataFrame) -> pd.DataFrame:
        """Return one row per target with the selected PC1 parent set.

        This audit artifact must never block a pipeline run. Missing PC1
        diagnostic columns are converted to stable empty/default values.
        """
        columns = [
            "target_col", "target", "pc1_selected_parents", "pc1_parent_set_all",
            "pc1_controls", "pc1_parent_count", "pc1_candidate_count",
            "pc1_selected_count", "pc1_gate_pass_count", "pc1_best_score",
            "pc1_pval_max", "pc1_val_min", "pc1_iterations",
        ]
        if proposals is None or len(proposals) == 0:
            return pd.DataFrame(columns=columns)
        src = proposals.copy()
        if "target" not in src.columns:
            src["target"] = ""
        if "target_col" not in src.columns:
            src["target_col"] = src["target"]
        for col in ["pc1_selected_parents", "pc1_parent_set_all", "pc1_controls"]:
            if col not in src.columns:
                src[col] = ""
        if "pc1_score" not in src.columns:
            src["pc1_score"] = 0.0
        if "pc1_is_selected_parent" not in src.columns:
            if "pc1_parent_support_status" in src.columns:
                src["pc1_is_selected_parent"] = src["pc1_parent_support_status"].astype(str).str.lower().isin({"selected", "pass", "passed", "true", "1"})
            else:
                src["pc1_is_selected_parent"] = False
        if "pc1_gate_pass" not in src.columns:
            src["pc1_gate_pass"] = src["pc1_is_selected_parent"]

        def _join_unique(values) -> str:
            out = []
            for value in values:
                for part in str(value or "").replace(",", "|").split("|"):
                    part = part.strip()
                    if part and part.lower() not in {"nan", "none", "null"} and part not in out:
                        out.append(part)
            return "|".join(out)

        rows = []
        for (target_col, target), group in src.groupby(["target_col", "target"], dropna=False, sort=False):
            parent_set = _join_unique(group.get("pc1_parent_set_all", []))
            rows.append({
                "target_col": target_col,
                "target": target,
                "pc1_selected_parents": _join_unique(group.get("pc1_selected_parents", [])),
                "pc1_parent_set_all": parent_set,
                "pc1_controls": _join_unique(group.get("pc1_controls", [])),
                "pc1_parent_count": len([p for p in parent_set.split("|") if p]),
                "pc1_candidate_count": int(len(group)),
                "pc1_selected_count": int(group["pc1_is_selected_parent"].astype(str).str.lower().isin({"true", "1", "1.0", "selected", "pass", "passed"}).sum()),
                "pc1_gate_pass_count": int(group["pc1_gate_pass"].astype(str).str.lower().isin({"true", "1", "1.0", "pass", "passed"}).sum()),
                "pc1_best_score": float(pd.to_numeric(group["pc1_score"], errors="coerce").fillna(0.0).max()) if len(group) else 0.0,
                "pc1_pval_max": float(pd.to_numeric(group["pc1_pval_max"], errors="coerce").max()) if "pc1_pval_max" in group and len(group) else np.nan,
                "pc1_val_min": float(pd.to_numeric(group["pc1_val_min"], errors="coerce").min()) if "pc1_val_min" in group and len(group) else np.nan,
                "pc1_iterations": int(pd.to_numeric(group["pc1_iterations"], errors="coerce").fillna(0).max()) if "pc1_iterations" in group and len(group) else 0,
            })
        return pd.DataFrame(rows, columns=columns)

    def _pc1_parent_candidates_frame(self, proposals: pd.DataFrame) -> pd.DataFrame:
        """Return the stable per-candidate PC1 parent audit artifact."""
        return self._with_existing_columns(proposals, PC1_PARENT_CANDIDATE_COLUMNS)

    def _build_gate_audit_frame(self, proposals: pd.DataFrame) -> pd.DataFrame:
        audit = self._with_existing_columns(proposals, GATE_AUDIT_COLUMNS).copy()
        if len(audit) == 0:
            return audit
        src = proposals.reset_index(drop=True)
        for kind, col in [
            ("mci", "mci_status"),
            ("confounder", "confounder_status"),
            ("ar", "ar_conditional_status"),
        ]:
            audit[col] = src.apply(lambda r: self._audit_status_from_row(r, kind), axis=1)
        audit["final_decision"] = audit.apply(
            lambda r: "kept" if str(r.get("keep_flag", "0")).strip() in {"1", "1.0", "true", "True"}
            or str(r.get("discovery_track", "")).strip().lower() not in {"", "dropped"}
            else "dropped",
            axis=1,
        )
        return audit[GATE_AUDIT_COLUMNS].copy()

    def _build_discovery_scoring_frame(self, proposals: pd.DataFrame) -> pd.DataFrame:
        return self._with_existing_columns(proposals, DISCOVERY_SCORING_COLUMNS)

    def _build_pcmci_scm_bridge_frame(self, proposals: pd.DataFrame) -> pd.DataFrame:
        """Compact structural handoff from PCMCI Discovery to SCM/estimation.

        PCMCI still provides candidate hypotheses, not causal proof. This file
        records the parent/conditioning sets and diagnostic statuses that SCM
        and estimation should inspect downstream.
        """
        bridge = self._with_existing_columns(proposals, PCMCI_SCM_BRIDGE_COLUMNS).copy()
        if len(bridge) == 0:
            return bridge
        src = proposals.reset_index(drop=True)
        bridge["edge_type"] = "temporal_candidate"
        if "pc1_parent_set_all" in src.columns:
            bridge["parent_set"] = src["pc1_parent_set_all"].fillna("").astype(str)
        elif "pc1_selected_parents" in src.columns:
            bridge["parent_set"] = src["pc1_selected_parents"].fillna("").astype(str)
        elif "pc1_parent_set" in src.columns:
            bridge["parent_set"] = src["pc1_parent_set"].fillna("").astype(str)
        else:
            bridge["parent_set"] = ""
        for _col in ["pc1_parent_spec", "pc1_is_selected_parent", "pc1_parent_rank", "pc1_parent_iteration", "pc1_parent_support_status", "pc1_p_value", "pc1_pval_max", "pc1_val_min", "pc1_iterations"]:
            if _col in src.columns:
                bridge[_col] = src[_col]

        if "mci_conditioning_set_used" in src.columns:
            bridge["conditioning_set_used"] = src["mci_conditioning_set_used"].fillna("").astype(str)
        else:
            controls = src["mci_controls"].fillna("").astype(str) if "mci_controls" in src.columns else pd.Series([""] * len(src))
            source_parents = src["mci_source_parents"].fillna("").astype(str) if "mci_source_parents" in src.columns else pd.Series([""] * len(src))
            bridge["conditioning_set_used"] = ["|".join([p for p in (a + "|" + b).split("|") if p]) for a, b in zip(controls, source_parents)]
        if "mci_conditioning_set_size" in src.columns:
            bridge["conditioning_set_size"] = src["mci_conditioning_set_size"]
        else:
            bridge["conditioning_set_size"] = bridge["conditioning_set_used"].apply(lambda v: len([p for p in str(v).split("|") if p]))
        if "mci_conditioning_quality" in src.columns:
            bridge["conditioning_quality"] = src["mci_conditioning_quality"].fillna("").astype(str)
        for _col in ["mci_val", "mci_pvalue", "mci_conditioning_set_y", "mci_conditioning_set_x", "mci_parents_y_count", "mci_parents_x_count", "mci_final_gate", "mci_gate_reason"]:
            if _col in src.columns:
                bridge[_col] = src[_col]

        bridge["mci_status"] = src.apply(lambda r: self._audit_status_from_row(r, "mci"), axis=1)
        bridge["confounder_status"] = src.apply(lambda r: self._audit_status_from_row(r, "confounder"), axis=1)
        bridge["ar_conditional_status"] = src.apply(lambda r: self._audit_status_from_row(r, "ar"), axis=1)
        if "pc1_parent_support_status" in src.columns:
            bridge["pc1_parent_support"] = src["pc1_parent_support_status"].fillna("not_evaluated").astype(str)
        elif "pc1_pass" in src.columns:
            bridge["pc1_parent_support"] = src["pc1_pass"].apply(lambda v: "selected" if str(v).strip() in {"1", "1.0", "True", "true"} else "diagnostic")
        else:
            bridge["pc1_parent_support"] = bridge["parent_set"].apply(lambda v: "selected" if str(v).strip() else "fallback_or_empty")

        def _role_hint(r):
            track = str(r.get("discovery_track", "")).strip().lower()
            mci_status = str(r.get("mci_status", "")).strip().lower()
            risk = str(r.get("risk_flags", "")).upper()
            if any(tok in risk for tok in ["LEAKAGE_BLOCK", "COLLIDER_PATTERN_PRUNE", "SENSITIVE_FEATURE", "BLOCKLISTED"]):
                return "do_not_use_hard_blocked"
            if track and track != "dropped" and mci_status in {"pass", "diagnostic_support"}:
                return "scm_temporal_parent_candidate"
            if track and track != "dropped":
                return "scm_diagnostic_temporal_candidate"
            return "discovery_rejected_diagnostic"

        bridge["scm_role_hint"] = bridge.apply(_role_hint, axis=1)
        if "selection_score" in src.columns:
            bridge["identification_priority"] = pd.to_numeric(src["selection_score"], errors="coerce")
        elif "priority_score" in src.columns:
            bridge["identification_priority"] = pd.to_numeric(src["priority_score"], errors="coerce")
        return bridge[PCMCI_SCM_BRIDGE_COLUMNS].copy()


    def _build_public_insights_frame(self, kept: pd.DataFrame) -> pd.DataFrame:
        """Return the Step-3 minimal public ranked-insights artifact.

        ``insights_level2.csv`` should not be a bridge, SCM payload, or effect
        estimate table.  It is now only a compact view of the candidate temporal
        link and the PC1/MCI gate status.  Detailed conditioning sets, SCM role
        hints, adjustment candidates, validation payloads, and Discovery-only
        effect proxies remain in dedicated artifacts.
        """
        public = self._with_existing_columns(kept, PUBLIC_INSIGHT_COLUMNS).copy()
        if len(public) == 0:
            return public

        src = kept.reset_index(drop=True).copy()

        def _truthy(value) -> bool:
            return str(value).strip().lower() in {"1", "1.0", "true", "yes", "y", "on", "pass", "passed", "selected"}

        def _first_nonempty(row: pd.Series, names: List[str], default: str = "") -> str:
            for name in names:
                if name in row.index:
                    value = row.get(name, "")
                    if pd.notna(value) and str(value).strip() != "":
                        return str(value)
            return default

        def _pc1_status(row: pd.Series) -> str:
            status = _first_nonempty(row, ["pc1_parent_support_status", "pc1_parent_support", "pc1_status"])
            if status:
                return status
            if _truthy(row.get("pc1_gate_pass", "")) or _truthy(row.get("pc1_is_selected_parent", "")) or _truthy(row.get("pc1_pass", "")):
                return "selected_parent"
            if _first_nonempty(row, ["pc1_parent_spec", "pc1_selected_parents", "pc1_parent_set_all"]):
                return "candidate_parent"
            return "not_evaluated"

        def _support_n(row: pd.Series):
            for name in ["mci_n_eff", "adjusted_support_n", "support_n", "stability_windows"]:
                if name in row.index:
                    value = pd.to_numeric(pd.Series([row.get(name, np.nan)]), errors="coerce").iloc[0]
                    if np.isfinite(value):
                        return int(value)
            return np.nan

        def _discovery_strength(row: pd.Series):
            for name in ["selection_score", "priority_score", "discovery_evidence_score", "strength"]:
                if name in row.index:
                    value = pd.to_numeric(pd.Series([row.get(name, np.nan)]), errors="coerce").iloc[0]
                    if np.isfinite(value):
                        return float(value)
            return np.nan

        def _gate_status(row: pd.Series) -> str:
            if str(row.get("drop_reason", "") or "").strip():
                return "dropped"
            if _truthy(row.get("keep_flag", "")):
                return "kept"
            if _truthy(row.get("mci_final_gate", "")):
                return "kept_by_mci"
            track = str(row.get("discovery_track", "") or "").strip().lower()
            if track and track != "dropped":
                return "kept"
            return "unknown"

        def _reason(row: pd.Series) -> str:
            return _first_nonempty(row, ["drop_reason", "mci_gate_reason", "reason_codes", "risk_flags"], "")

        public["pc1_status"] = src.apply(_pc1_status, axis=1)
        public["mci_status"] = src.apply(lambda r: self._audit_status_from_row(r, "mci"), axis=1)
        public["support_n"] = src.apply(_support_n, axis=1)
        public["discovery_strength"] = src.apply(_discovery_strength, axis=1)
        public["gate_status"] = src.apply(_gate_status, axis=1)
        public["reason"] = src.apply(_reason, axis=1)

        # Keep a single, stable public schema with no effect-estimate aliases or
        # heavy handoff columns.
        public = public.loc[:, ~public.columns.duplicated()].copy()
        return public[PUBLIC_INSIGHT_COLUMNS].copy()

    def _write_jsonl_records(self, frame: pd.DataFrame, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for _, r in frame.iterrows():
                f.write(json.dumps({k: (None if pd.isna(v) else v) for k, v in r.to_dict().items()}, ensure_ascii=False) + "\n")


    def _discovery_warning_summary(self) -> Dict[str, object]:
        """Return a stable warning summary for Discovery manifests.

        When no non-fatal warnings were emitted we write warnings_count=0 and
        warnings_file=None explicitly, so a missing discovery_warnings.jsonl is
        interpreted as clean execution rather than a missing artifact.
        """
        cfg = self.cfg
        warning_path = os.path.join(cfg.out_dir, "discovery_warnings.jsonl")
        if not os.path.exists(warning_path):
            return {"warnings_count": 0, "warnings_file": None}
        count = 0
        try:
            with open(warning_path, "r", encoding="utf-8") as f:
                count = sum(1 for line in f if line.strip())
        except OSError:
            count = -1
        return {"warnings_count": int(count), "warnings_file": warning_path}


    def _write_discovery_run_manifest(self, paths: Dict[str, str], proposals: pd.DataFrame, kept: pd.DataFrame) -> str:
        cfg = self.cfg
        manifest_path = os.path.join(cfg.out_dir, "discovery_run_manifest.json")
        summary = self._discovery_warning_summary()
        payload = {
            "layer": "discovery",
            "manifest_version": 2,
            "out_dir": cfg.out_dir,
            "counts": {"proposal_rows": int(len(proposals)), "kept_rows": int(len(kept))},
            **summary,
            "files": paths,
        }
        os.makedirs(cfg.out_dir, exist_ok=True)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return manifest_path


    def _layer_dirs(self) -> Dict[str, str]:
        cfg = self.cfg
        return {
            "discovery": os.path.join(cfg.out_dir, getattr(cfg, "output_discovery_dirname", "discovery")),
            "validation": os.path.join(cfg.out_dir, getattr(cfg, "output_validation_dirname", "validation")),
            "ranking": os.path.join(cfg.out_dir, getattr(cfg, "output_ranking_dirname", "ranking")),
        }


    def _write_layered_outputs(self, proposals: pd.DataFrame, candidate_views: Dict[str, pd.DataFrame], discovery_ctx: DiscoveryContext, base_paths: Dict[str, str]) -> Dict[str, str]:
        cfg = self.cfg
        kept = candidate_views["insights"]
        public_insights = self._build_public_insights_frame(kept)
        bridge_source = proposals.copy()
        if "proposal_id" in bridge_source.columns and "proposal_id" in kept.columns and "insight_id" in kept.columns:
            id_map = kept[["proposal_id", "insight_id"]].dropna().drop_duplicates(subset=["proposal_id"], keep="first")
            bridge_source = bridge_source.drop(columns=["insight_id"], errors="ignore").merge(id_map, on="proposal_id", how="left")
        layer_dirs = self._layer_dirs()
        for path in layer_dirs.values():
            os.makedirs(path, exist_ok=True)

        discovery_paths = {
            "edges": os.path.join(layer_dirs["discovery"], "edges.csv"),
            "hypotheses_raw": os.path.join(layer_dirs["discovery"], "hypotheses_layer1_raw.csv"),
            "pc1_parent_sets": os.path.join(layer_dirs["discovery"], "pc1_parent_sets.csv"),
            "pc1_parent_candidates": os.path.join(layer_dirs["discovery"], "pc1_parent_candidates.csv"),
            "pcmci_links": os.path.join(layer_dirs["discovery"], "pcmci_links.csv"),
            "gate_audit": os.path.join(layer_dirs["discovery"], "gate_audit.csv"),
            "discovery_scoring": os.path.join(layer_dirs["discovery"], "discovery_scoring.csv"),
            "pcmci_scm_bridge": os.path.join(layer_dirs["discovery"], "pcmci_scm_bridge.csv"),
            "manifest": os.path.join(layer_dirs["discovery"], "discovery_manifest.json"),
        }
        proposals.to_csv(discovery_paths["edges"], index=False)
        proposals.to_csv(discovery_paths["hypotheses_raw"], index=False)
        self._pc1_parent_sets_frame(proposals).to_csv(discovery_paths["pc1_parent_sets"], index=False)
        self._pc1_parent_candidates_frame(proposals).to_csv(discovery_paths["pc1_parent_candidates"], index=False)
        self._build_gate_audit_frame(proposals).to_csv(discovery_paths["gate_audit"], index=False)
        self._build_discovery_scoring_frame(proposals).to_csv(discovery_paths["discovery_scoring"], index=False)
        self._build_pcmci_scm_bridge_frame(bridge_source).to_csv(discovery_paths["pcmci_scm_bridge"], index=False)
        link_cols = [c for c in [
            "proposal_id", "source", "target", "lag", "pc1_parent_set", "pc1_pass",
            "mci_score", "mci_val", "mci_partial_corr", "mci_t_abs", "mci_delta_r2", "mci_n_eff",
            "mci_robustness", "mci_p_value", "mci_pvalue", "mci_q_value",
            "mci_conditioning_set_y", "mci_conditioning_set_x", "mci_parents_y_count", "mci_parents_x_count",
            "mci_conditioning_set_used", "mci_conditioning_set_size", "mci_conditioning_quality",
            "mci_final_gate", "mci_gate_reason",
            "priority_score", "discovery_evidence_score", "selection_score",
            "hypothesis_signal_score", "hypothesis_signal_grade",
            "safety_risk_score", "safety_risk_grade",
            "signal_safety_cell", "signal_safety_matrix_track", "signal_safety_blocking",
            "discovery_track", "keep_flag", "risk_flags", "drop_reason"
        ] if c in proposals.columns]
        proposals[link_cols].copy().to_csv(discovery_paths["pcmci_links"], index=False)

        validation_paths = {
            "path_candidates_csv": os.path.join(layer_dirs["validation"], "path_candidates_level2.csv"),
            "path_candidates_jsonl": os.path.join(layer_dirs["validation"], "path_candidates_level2.jsonl"),
            "mediators_csv": os.path.join(layer_dirs["validation"], "mediator_candidates_level2.csv"),
            "context_csv": os.path.join(layer_dirs["validation"], "context_feature_candidates_level2.csv"),
            "harms_csv": os.path.join(layer_dirs["validation"], "harm_hypotheses_level2.csv"),
            "strata_csv": os.path.join(layer_dirs["validation"], "candidate_strata_level2.csv"),
            "alternatives_csv": os.path.join(layer_dirs["validation"], "alternative_explanations_level2.csv"),
            "validation_plan_csv": os.path.join(layer_dirs["validation"], "validation_plan_level2.csv"),
            "manifest": os.path.join(layer_dirs["validation"], "validation_manifest.json"),
        }
        candidate_views["path_candidates"].to_csv(validation_paths["path_candidates_csv"], index=False)
        self._write_jsonl_records(candidate_views["path_candidates"], validation_paths["path_candidates_jsonl"])
        candidate_views["mediator_candidates"].to_csv(validation_paths["mediators_csv"], index=False)
        candidate_views["context_features"].to_csv(validation_paths["context_csv"], index=False)
        candidate_views["harm_hypotheses"].to_csv(validation_paths["harms_csv"], index=False)
        candidate_views["strata_candidates"].to_csv(validation_paths["strata_csv"], index=False)
        candidate_views["alternative_explanations"].to_csv(validation_paths["alternatives_csv"], index=False)
        candidate_views["validation_plan"].to_csv(validation_paths["validation_plan_csv"], index=False)

        ranking_paths = {
            "insights_csv": os.path.join(layer_dirs["ranking"], "insights_level2.csv"),
            "insights_jsonl": os.path.join(layer_dirs["ranking"], "insights_level2.jsonl"),
            "manifest": os.path.join(layer_dirs["ranking"], "ranking_manifest.json"),
        }
        public_insights.to_csv(ranking_paths["insights_csv"], index=False)
        self._write_jsonl_records(public_insights, ranking_paths["insights_jsonl"])
        for track in ["high_confidence", "exploratory", "weak_structured"]:
            subset = public_insights[public_insights["discovery_track"] == track].copy() if "discovery_track" in public_insights.columns else public_insights.iloc[0:0].copy()
            subset.to_csv(os.path.join(layer_dirs["ranking"], f"insights_level2_{track}.csv"), index=False)

        warning_summary = self._discovery_warning_summary()
        with open(discovery_paths["manifest"], "w", encoding="utf-8") as f:
            json.dump({
                "layer": "discovery",
                "selector": "pc1",
                "confirmation": "mci",
                "files": discovery_paths,
                "counts": {"proposal_rows": int(len(proposals)), "kept_rows": int(len(kept))},
                **warning_summary,
            }, f, ensure_ascii=False, indent=2)
        with open(validation_paths["manifest"], "w", encoding="utf-8") as f:
            json.dump({
                "layer": "validation",
                "files": validation_paths,
                "counts": {k: int(len(v)) for k, v in candidate_views.items() if hasattr(v, "__len__")},
            }, f, ensure_ascii=False, indent=2)
        with open(ranking_paths["manifest"], "w", encoding="utf-8") as f:
            json.dump({
                "layer": "ranking",
                "files": ranking_paths,
                "track_counts": kept["discovery_track"].value_counts().to_dict() if len(kept) > 0 and "discovery_track" in kept.columns else {},
            }, f, ensure_ascii=False, indent=2)

        combined_manifest = os.path.join(cfg.out_dir, "discovery_layer_manifest.json")
        with open(combined_manifest, "w", encoding="utf-8") as f:
            json.dump({
                "separated_layers": True,
                "discovery_dir": layer_dirs["discovery"],
                "validation_dir": layer_dirs["validation"],
                "ranking_dir": layer_dirs["ranking"],
                "legacy_compatibility_files": base_paths,
                **warning_summary,
                "layer_files": {
                    "discovery": discovery_paths,
                    "validation": validation_paths,
                    "ranking": ranking_paths,
                },
            }, f, ensure_ascii=False, indent=2)
        out = {}
        out.update({f"layer_discovery_{k}": v for k, v in discovery_paths.items()})
        out.update({f"layer_validation_{k}": v for k, v in validation_paths.items()})
        out.update({f"layer_ranking_{k}": v for k, v in ranking_paths.items()})
        out["layer_manifest"] = combined_manifest
        return out


    def _emit_nonfatal_warning(self, stage: str, exc: Exception, paths: Optional[Dict[str, str]] = None) -> None:
        """Record non-fatal artifact generation failures instead of hiding them.

        Discovery should continue when optional SCM / identification assets fail,
        but the failure must remain visible in stderr and in out/discovery_warnings.jsonl.
        """
        cfg = self.cfg
        message = f"[causalgate][warning] {stage} failed: {type(exc).__name__}: {exc}"
        print(message, file=sys.stderr)
        warning_path = os.path.join(cfg.out_dir, "discovery_warnings.jsonl")
        try:
            os.makedirs(cfg.out_dir, exist_ok=True)
            with open(warning_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "stage": stage,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }, ensure_ascii=False) + "\n")
            if paths is not None:
                paths["warnings_jsonl"] = warning_path
        except OSError as warning_error:
            print(f"[causalgate][warning] failed to write warning log {warning_path}: {type(warning_error).__name__}: {warning_error}", file=sys.stderr)


    def _write_outputs(self, proposals: pd.DataFrame, candidate_views: Dict[str, pd.DataFrame], discovery_ctx: DiscoveryContext) -> Dict[str, str]:
        cfg = self.cfg
        kept = candidate_views["insights"]
        public_insights = self._build_public_insights_frame(kept)
        bridge_source = proposals.copy()
        # Attach insight_id to structural bridge rows so SCM/contract metadata
        # merges with the ranked insight and estimation handoff instead of
        # becoming a detached source->target audit row.
        if "proposal_id" in bridge_source.columns and "proposal_id" in kept.columns and "insight_id" in kept.columns:
            id_map = kept[["proposal_id", "insight_id"]].dropna().drop_duplicates(subset=["proposal_id"], keep="first")
            bridge_source = bridge_source.drop(columns=["insight_id"], errors="ignore").merge(id_map, on="proposal_id", how="left")
        paths = {
            "edges": os.path.join(cfg.out_dir, "edges.csv"),
            "hypotheses_raw": os.path.join(cfg.out_dir, "hypotheses_layer1_raw.csv"),
            "pc1_parent_sets": os.path.join(cfg.out_dir, "pc1_parent_sets.csv"),
            "pc1_parent_candidates_csv": os.path.join(cfg.out_dir, "pc1_parent_candidates.csv"),
            "gate_audit_csv": os.path.join(cfg.out_dir, "gate_audit.csv"),
            "discovery_scoring_csv": os.path.join(cfg.out_dir, "discovery_scoring.csv"),
            "pcmci_scm_bridge_csv": os.path.join(cfg.out_dir, "pcmci_scm_bridge.csv"),
            "insights_csv": os.path.join(cfg.out_dir, "insights_level2.csv"),
            "insights_jsonl": os.path.join(cfg.out_dir, "insights_level2.jsonl"),
            "path_candidates_csv": os.path.join(cfg.out_dir, "path_candidates_level2.csv"),
            "path_candidates_jsonl": os.path.join(cfg.out_dir, "path_candidates_level2.jsonl"),
            "mediators_csv": os.path.join(cfg.out_dir, "mediator_candidates_level2.csv"),
            "context_csv": os.path.join(cfg.out_dir, "context_feature_candidates_level2.csv"),
            "harms_csv": os.path.join(cfg.out_dir, "harm_hypotheses_level2.csv"),
            "strata_csv": os.path.join(cfg.out_dir, "candidate_strata_level2.csv"),
            "alternatives_csv": os.path.join(cfg.out_dir, "alternative_explanations_level2.csv"),
            "validation_plan_csv": os.path.join(cfg.out_dir, "validation_plan_level2.csv"),
            "discovery_bridge_csv": os.path.join(cfg.out_dir, "discovery_estimation_bridge.csv"),
            "discovery_bridge_manifest": os.path.join(cfg.out_dir, "discovery_estimation_manifest.json"),
            "effective_config_json": os.path.join(cfg.out_dir, "discovery_config_effective.json"),
        }
        try:
            paths["effective_config_json"] = cfg.write_effective_config(paths["effective_config_json"])
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            self._emit_nonfatal_warning("effective_discovery_config", exc, paths)
        proposals.to_csv(paths["edges"], index=False)
        proposals.to_csv(paths["hypotheses_raw"], index=False)
        self._pc1_parent_sets_frame(proposals).to_csv(paths["pc1_parent_sets"], index=False)
        self._pc1_parent_candidates_frame(proposals).to_csv(paths["pc1_parent_candidates_csv"], index=False)
        self._build_gate_audit_frame(proposals).to_csv(paths["gate_audit_csv"], index=False)
        self._build_discovery_scoring_frame(proposals).to_csv(paths["discovery_scoring_csv"], index=False)
        self._build_pcmci_scm_bridge_frame(bridge_source).to_csv(paths["pcmci_scm_bridge_csv"], index=False)
        public_insights.to_csv(paths["insights_csv"], index=False)
        candidate_views["path_candidates"].to_csv(paths["path_candidates_csv"], index=False)
        candidate_views["mediator_candidates"].to_csv(paths["mediators_csv"], index=False)
        candidate_views["context_features"].to_csv(paths["context_csv"], index=False)
        candidate_views["harm_hypotheses"].to_csv(paths["harms_csv"], index=False)
        candidate_views["strata_candidates"].to_csv(paths["strata_csv"], index=False)
        candidate_views["alternative_explanations"].to_csv(paths["alternatives_csv"], index=False)
        candidate_views["validation_plan"].to_csv(paths["validation_plan_csv"], index=False)
        for track in ["high_confidence", "exploratory", "weak_structured"]:
            subset = public_insights[public_insights["discovery_track"] == track].copy() if "discovery_track" in public_insights.columns else public_insights.iloc[0:0].copy()
            subset.to_csv(os.path.join(cfg.out_dir, f"insights_level2_{track}.csv"), index=False)
            pc = candidate_views["path_candidates"]
            if len(pc) > 0 and "discovery_track" in pc.columns:
                pc[pc["discovery_track"] == track].copy().to_csv(os.path.join(cfg.out_dir, f"path_candidates_level2_{track}.csv"), index=False)
            hh = candidate_views["harm_hypotheses"]
            if len(hh) > 0 and "discovery_track" in hh.columns:
                hh[hh["discovery_track"] == track].copy().to_csv(os.path.join(cfg.out_dir, f"harm_hypotheses_level2_{track}.csv"), index=False)
            sc = candidate_views["strata_candidates"]
            if len(sc) > 0 and "discovery_track" in sc.columns:
                sc[sc["discovery_track"] == track].copy().to_csv(os.path.join(cfg.out_dir, f"candidate_strata_level2_{track}.csv"), index=False)
            av = candidate_views["alternative_explanations"]
            if len(av) > 0 and "discovery_track" in av.columns:
                av[av["discovery_track"] == track].copy().to_csv(os.path.join(cfg.out_dir, f"alternative_explanations_level2_{track}.csv"), index=False)
            vp = candidate_views["validation_plan"]
            if len(vp) > 0 and "discovery_track" in vp.columns:
                vp[vp["discovery_track"] == track].copy().to_csv(os.path.join(cfg.out_dir, f"validation_plan_level2_{track}.csv"), index=False)
        self._write_jsonl_records(public_insights, paths["insights_jsonl"])
        self._write_jsonl_records(candidate_views["path_candidates"], paths["path_candidates_jsonl"])
        bridge_frame = None
        try:
            bridge_csv, bridge_manifest, bridge_frame = write_bridge_from_insights(kept, cfg.out_dir, source_insights_path=paths.get("insights_csv", ""))
            paths["discovery_bridge_csv"] = bridge_csv
            paths["discovery_bridge_manifest"] = bridge_manifest
        except (OSError, ValueError, TypeError, RuntimeError, KeyError, ImportError) as exc:
            bridge_frame = None
            self._emit_nonfatal_warning("discovery_bridge_assets", exc, paths)
        try:
            scm_paths = write_scm_assets(proposals, kept, out_dir=cfg.out_dir, bridge=bridge_frame, dag_path=getattr(cfg, "dag_path", None))
            paths.update({f"scm_{k}": v for k, v in scm_paths.items()})
            try:
                id_paths = write_identification_assets(
                    out_dir=cfg.out_dir,
                    scm_graph_path=scm_paths.get("scm_graph_json"),
                    bridge=bridge_frame,
                    bridge_csv_path=paths.get("discovery_bridge_csv"),
                    insights=kept,
                )
                paths.update({f"ident_{k}": v for k, v in id_paths.items()})
            except (OSError, ValueError, TypeError, RuntimeError, KeyError, ImportError) as exc:
                self._emit_nonfatal_warning("identification_assets", exc, paths)
        except (OSError, ValueError, TypeError, RuntimeError, KeyError, ImportError) as exc:
            self._emit_nonfatal_warning("scm_assets", exc, paths)
        if getattr(cfg, "output_separate_layers", True):
            paths.update(self._write_layered_outputs(proposals, candidate_views, discovery_ctx, paths.copy()))
        try:
            paths["discovery_run_manifest"] = self._write_discovery_run_manifest(paths.copy(), proposals, kept)
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            self._emit_nonfatal_warning("discovery_run_manifest", exc, paths)
        return paths


    def _print_summary(self, data_path: str, proposals: pd.DataFrame, candidate_views: Dict[str, pd.DataFrame], paths: Dict[str, str]) -> None:
        print("\n=== CAUSALGATE DISCOVERY — downside rewrite ===")
        print("Data:", data_path)
        print("Saved edges:", paths["edges"])
        kept = candidate_views["insights"]
        print("Saved insights:", paths["insights_csv"])
        print("Saved PC1 parent sets:", paths["pc1_parent_sets"])
        if "pc1_parent_candidates_csv" in paths:
            print("Saved PC1 parent candidates:", paths["pc1_parent_candidates_csv"])
        if "gate_audit_csv" in paths:
            print("Saved gate audit:", paths["gate_audit_csv"])
        if "discovery_scoring_csv" in paths:
            print("Saved Discovery scoring:", paths["discovery_scoring_csv"])
        if "pcmci_scm_bridge_csv" in paths:
            print("Saved PCMCI→SCM bridge:", paths["pcmci_scm_bridge_csv"])
        print("Saved path candidates:", paths["path_candidates_csv"])
        print("Saved harm hypotheses:", paths["harms_csv"])
        print("Saved candidate strata:", paths["strata_csv"])
        print("Saved alternative explanations:", paths["alternatives_csv"])
        print("Saved validation plans:", paths["validation_plan_csv"])
        if "effective_config_json" in paths:
            print("Saved effective Discovery config:", paths["effective_config_json"])
        if "scm_scm_graph_json" in paths:
            print("Saved SCM graph:", paths["scm_scm_graph_json"])
        if "scm_node_roles_csv" in paths:
            print("Saved node roles:", paths["scm_node_roles_csv"])
        if "ident_identified_effects_csv" in paths:
            print("Saved identified effects:", paths["ident_identified_effects_csv"])
        if "layer_manifest" in paths:
            print("Saved layered manifest:", paths["layer_manifest"])
            print("Discovery layer dir:", self._layer_dirs()["discovery"])
            print("Validation layer dir:", self._layer_dirs()["validation"])
            print("Ranking layer dir:", self._layer_dirs()["ranking"])
        print("Proposal rows:", len(proposals))
        print("Kept rows:", len(kept))
        if len(kept) > 0 and "discovery_track" in kept.columns:
            counts = kept["discovery_track"].value_counts().to_dict()
            print("Track counts:", counts)
        if len(candidate_views["path_candidates"]) > 0:
            cols = [c for c in [
                "insight_id", "path_id_candidate", "action_name", "harm_label", "mediator_candidate",
                "priority_score", "causal_plausibility_score", "validation_readiness_score", "structural_risk_score"
            ] if c in candidate_views["path_candidates"].columns]
            print(candidate_views["path_candidates"][cols].head(10).to_string(index=False))


