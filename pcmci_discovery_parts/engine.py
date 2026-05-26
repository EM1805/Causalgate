
from runtime_env import configure_scientific_runtime
configure_scientific_runtime()

from .engine_common import *
import numpy as np
import pandas as pd
from .evidence import EvidenceScorerMixin
from .pruner import PcmciPrunerMixin
from .views import CandidateViewMixin
from .output_writer import OutputWriterMixin
from .hypotheses import HypothesisGeneratorMixin
from .metrics_builder import MetricsBuilderMixin
from .row_builder import RowBuilderMixin


class ProposalEngine(EvidenceScorerMixin, PcmciPrunerMixin, CandidateViewMixin, OutputWriterMixin, HypothesisGeneratorMixin, MetricsBuilderMixin, RowBuilderMixin):
    def __init__(self, cfg: ProposalConfig):
        self.cfg = cfg
        self.dag = None
        self.op_graph = None
        # Offline prior graph input was removed from the canonical public contract.
        # This guarded branch is only for private in-memory experiments that set
        # cfg.dag_path explicitly; CLI/config/pcb.json no longer expose it.
        raw_dag_path = str(getattr(cfg, "dag_path", "") or "").strip()
        if raw_dag_path and OfflinePriorGraph is not None:
            dag_path = os.path.join(cfg.out_dir, raw_dag_path) if not os.path.isabs(raw_dag_path) else raw_dag_path
            if not os.path.exists(dag_path):
                alt = raw_dag_path
                dag_path = alt if os.path.exists(alt) else dag_path
            if os.path.exists(dag_path):
                try:
                    self.dag = OfflinePriorGraph.load(dag_path)
                except (OSError, ValueError, TypeError, RuntimeError, KeyError):
                    self.dag = None
        # Operational/runtime graph authority intentionally stays outside PCMCI Discovery.
        # Discovery may emit causal candidates; runtime/veto layers decide activation and policy effects.
        self._outcome_profile: Dict[str, str] = {"kind": "continuous", "estimand": "effect_att"}

    def _load_df(self, data_csv_path: Optional[str]) -> Tuple[pd.DataFrame, str]:
        cfg = self.cfg
        candidates = [
            data_csv_path,
            cfg.data_csv,
            os.path.join(cfg.out_dir, "data_clean.csv"),
            os.path.join(cfg.out_dir, "demo_data.csv"),
        ]
        path = next((p for p in candidates if p and os.path.exists(p)), None)
        if not path:
            raise FileNotFoundError("No input data found for Level 2.5")
        df = pd.read_csv(path)
        if cfg.date_col in df.columns:
            try:
                dt = pd.to_datetime(df[cfg.date_col], errors="coerce")
                if dt.notna().mean() > 0.2:
                    df[cfg.date_col] = dt
            except (TypeError, ValueError):
                pass
        return df, path

    def _candidate_columns(self, df: pd.DataFrame) -> List[str]:
        cfg = self.cfg
        cols: List[str] = []
        for c in df.columns:
            if c in (cfg.target_col, cfg.date_col):
                continue
            s = pd.to_numeric(df[c], errors="coerce")
            nan_frac = 1.0 - float(s.notna().mean())
            if nan_frac > cfg.max_nan_frac:
                continue
            if s.nunique(dropna=True) < cfg.min_unique:
                continue
            if float(np.nanstd(s.to_numpy(dtype=float))) < 1e-8:
                continue
            cols.append(c)
        return cols

    def _supporting_features(self, source: str, all_candidates: Sequence[str]) -> str:
        low = source.lower()
        toks = [t for t in re.split(r"[_\W]+", low) if t]
        out: List[str] = []
        for c in all_candidates:
            if c == source:
                continue
            cl = c.lower()
            if any(tok in cl for tok in toks[:2] if tok and len(tok) >= 3):
                out.append(c)
            if len(out) >= 5:
                break
        return "|".join(out)

    def _rank_confounders(self, source: str, df: pd.DataFrame, candidates: Sequence[str], lag: int) -> List[dict]:
        y = pd.to_numeric(df[self.cfg.target_col], errors="coerce").to_numpy(dtype=float)
        x = pd.to_numeric(df[source], errors="coerce").to_numpy(dtype=float)
        ranked: List[dict] = []
        for c in candidates:
            if c == source:
                continue
            z = pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float)
            if len(z) <= lag + 8:
                continue
            zx = _corr(z[:-lag], x[lag:])
            zy = _corr(z[:-lag], y[lag:])
            if not (np.isfinite(zx) and np.isfinite(zy)):
                continue
            if abs(zx) < CAL.CONFOUNDER_MIN_ABS_CORR or abs(zy) < CAL.CONFOUNDER_MIN_ABS_CORR:
                continue
            temporal_bonus = CAL.CONFOUNDER_TEMPORAL_NAME_BONUS if ("prev" in c.lower() or "baseline" in c.lower()) else 0.0
            score = abs(zx) * abs(zy) + temporal_bonus
            ranked.append({"name": c, "score": float(score), "zx": float(zx), "zy": float(zy)})
        ranked.sort(key=lambda r: r["score"], reverse=True)
        return ranked

    def _confounder_hint(self, source: str, df: pd.DataFrame, candidates: Sequence[str], lag: int) -> str:
        ranked = self._rank_confounders(source, df, candidates, lag)
        return "|".join(r["name"] for r in ranked[:CAL.MAX_CONFOUNDER_HINTS])

    def _adjustment_summary(self, source: str, df: pd.DataFrame, candidates: Sequence[str], lag: int, corr: float, delta: float) -> dict:
        x = pd.to_numeric(df[source], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(df[self.cfg.target_col], errors="coerce").to_numpy(dtype=float)
        ranked = self._rank_confounders(source, df, candidates, lag)
        selected = [r["name"] for r in ranked[: min(CAL.MAX_SELECTED_CONFOUNDERS, len(ranked))]]
        controls = [pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float) for c in selected]
        metrics = _adjusted_effect_metrics(x, y, controls, lag)
        raw_strength = max(abs(corr) + CAL.RAW_STRENGTH_DELTA_WEIGHT * abs(delta if np.isfinite(delta) else 0.0), 1e-6)
        adj_strength = 0.0
        if np.isfinite(metrics.get("adjusted_corr", np.nan)):
            adj_strength += abs(float(metrics["adjusted_corr"]))
        if np.isfinite(metrics.get("adjusted_delta", np.nan)):
            adj_strength += CAL.RAW_STRENGTH_DELTA_WEIGHT * abs(float(metrics["adjusted_delta"]))
        attenuation = 1.0 - min(1.0, adj_strength / raw_strength)
        if len(selected) == 0:
            confounding_risk = CAL.CONFOUNDING_RISK_NO_CONTROLS
        else:
            confounding_risk = _clip01(CAL.CONFOUNDING_RISK_ATTENUATION_WEIGHT * attenuation + CAL.CONFOUNDING_RISK_ZX_WEIGHT * np.nanmean([abs(r["zx"]) for r in ranked[:len(selected)]]) + CAL.CONFOUNDING_RISK_ZY_WEIGHT * np.nanmean([abs(r["zy"]) for r in ranked[:len(selected)]]))
        return {
            "confounders": selected,
            "adjusted_corr": float(metrics.get("adjusted_corr", np.nan)),
            "adjusted_delta": float(metrics.get("adjusted_delta", np.nan)),
            "attenuation_ratio": float(_clip01(attenuation)),
            "confounding_risk_score": float(confounding_risk),
            "adjusted_support": int(metrics.get("n_eff", 0) or 0),
            "discovery_effect_proxy": float(metrics.get("causal_effect", np.nan)),
            "discovery_effect_proxy_std": float(metrics.get("causal_effect_std", np.nan)),
            "discovery_effect_proxy_ci_low": float(metrics.get("causal_effect_ci_low", np.nan)),
            "discovery_effect_proxy_ci_high": float(metrics.get("causal_effect_ci_high", np.nan)),
            # Legacy internal names retained until the SourceMetrics dataclass is renamed.
            "causal_effect": float(metrics.get("causal_effect", np.nan)),
            "causal_effect_std": float(metrics.get("causal_effect_std", np.nan)),
            "causal_effect_ci_low": float(metrics.get("causal_effect_ci_low", np.nan)),
            "causal_effect_ci_high": float(metrics.get("causal_effect_ci_high", np.nan)),
            "effect_persistence_score": float(metrics.get("effect_persistence_score", np.nan)),
        }

    def _mediator_hint(self, source: str, candidates: Sequence[str]) -> str:
        low = source.lower()
        out: List[str] = []
        for c in candidates:
            if c == source:
                continue
            cl = c.lower()
            if any(p in cl for p in self.cfg.mediator_name_patterns) and not any(t in cl for t in low.split("_")):
                out.append(c)
            if len(out) >= 4:
                break
        return "|".join(out)

    def _forbidden_adjustment_hint(self, source: str, mediator_hint: str) -> str:
        out: List[str] = []
        if source.endswith("_prev"):
            out.append(source)
        if mediator_hint:
            out.extend([m for m in mediator_hint.split("|") if m])
        return "|".join(dict.fromkeys(out[:5]))

    def _validate_source_name(self, source: str) -> Tuple[bool, bool, bool, set[str]]:
        intervenible, intervene_reasons = _is_intervenible(source, self.cfg)
        blocked_name_reasons = set(intervene_reasons)
        name_is_leaklike = "LEAKAGE_NAME_PATTERN" in blocked_name_reasons
        name_is_non_actionable_only = blocked_name_reasons.issubset(
            {"NON_ACTIONABLE_NAME", "IS_TARGET", "IS_DATE", "EMPTY_NAME", "LAGGED_PROXY"}
        )
        keep_for_guardrails = (not intervenible) and name_is_leaklike and (not name_is_non_actionable_only)
        return intervenible, name_is_leaklike, keep_for_guardrails, blocked_name_reasons

    def _compute_source_statistics(self, df: pd.DataFrame, source: str, y: np.ndarray) -> Optional[dict]:
        cfg = self.cfg
        x = pd.to_numeric(df[source], errors="coerce").to_numpy(dtype=float)
        both = np.isfinite(x) & np.isfinite(y)
        if int(np.sum(both)) < max(cfg.min_obs, cfg.max_lag + 10):
            return None
        best = _best_lag_metrics(x, y, cfg.max_lag)
        lag = int(best["lag"]) if np.isfinite(best["lag"]) else None
        corr = float(best["corr"]) if np.isfinite(best["corr"]) else np.nan
        delta = float(best["delta_test"]) if np.isfinite(best["delta_test"]) else np.nan
        if lag is None or not np.isfinite(corr):
            return None
        stability, n_win, _ = _rolling_stability(x, y, lag, cfg.stability_window, cfg.stability_stride)
        lag_meta = _future_leakage_score(x, y, lag)
        regime = _regime_awareness_metrics(x, y, lag, cfg.regime_recent_frac, cfg.regime_min_recent_n)
        relation_sign = math.copysign(1.0, corr) if np.isfinite(corr) and corr != 0 else 0.0
        return {
            "x": x,
            "lag": lag,
            "corr": corr,
            "delta": delta,
            "stability": stability,
            "stability_windows": n_win,
            "lag_meta": lag_meta,
            "regime": regime,
            "relation_sign": relation_sign,
        }

    def _conditional_signal_summary(self, source: str, df: pd.DataFrame, candidates: Sequence[str], lag: int, corr: float, delta: float) -> dict:
        ranked = self._rank_confounders(source, df, candidates, lag)
        top_rivals: List[str] = []
        source_low = source.lower()
        for item in ranked:
            name = item["name"]
            low = name.lower()
            if low == source_low:
                continue
            if low.startswith(source_low) or source_low.startswith(low):
                continue
            top_rivals.append(name)
            if len(top_rivals) >= 3:
                break
        selected = [r["name"] for r in ranked[: min(4, len(ranked))]]
        if top_rivals:
            selected = list(dict.fromkeys(selected + top_rivals))
        x = pd.to_numeric(df[source], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(df[self.cfg.target_col], errors="coerce").to_numpy(dtype=float)
        controls = [pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float) for c in selected]
        metrics = _adjusted_effect_metrics(x, y, controls, lag)
        raw_strength = max(abs(corr) + CAL.RAW_STRENGTH_DELTA_WEIGHT * abs(delta if np.isfinite(delta) else 0.0), 1e-6)
        adjusted_strength = 0.0
        adj_corr = float(metrics.get("adjusted_corr", np.nan))
        adj_delta = float(metrics.get("adjusted_delta", np.nan))
        if np.isfinite(adj_corr):
            adjusted_strength += abs(adj_corr)
        if np.isfinite(adj_delta):
            adjusted_strength += CAL.RAW_STRENGTH_DELTA_WEIGHT * abs(adj_delta)
        innovation = _residual_competition_signal(
            x,
            y,
            controls,
            lag,
            ar_lags=max(1, int(getattr(self.cfg, "discovery_target_ar_lags", 2))),
        )
        innovation_score = float(innovation.get("screen_score", 0.0) or 0.0)
        innovation_corr = float(innovation.get("innovation_corr", np.nan))
        innovation_beta_std = float(innovation.get("innovation_beta_std", np.nan))
        innovation_t = float(innovation.get("innovation_t", np.nan))
        parent_score = _clip01(0.55 * _clip01(adjusted_strength / raw_strength) + 0.45 * innovation_score)
        ci_signal = max(adjusted_strength, 0.0)
        survives = bool((np.isfinite(adj_corr) and abs(adj_corr) >= max(CAL.CI_MIN_SURVIVAL_ABS_CORR, abs(corr) * CAL.CI_RELATIVE_SURVIVAL_FRACTION)) or (np.isfinite(adj_delta) and abs(adj_delta) >= max(CAL.CI_MIN_SURVIVAL_ABS_DELTA, abs(delta) * CAL.CI_RELATIVE_SURVIVAL_FRACTION if np.isfinite(delta) else CAL.CI_MIN_SURVIVAL_ABS_DELTA)))
        survives = survives and int(innovation.get("pass", 0) or 0) == 1
        parent_pass = int(parent_score >= float(getattr(self.cfg, "parent_competition_min_score", 0.52)) and survives)
        return {
            "controls": selected,
            "top_rivals": top_rivals,
            "adjusted_corr": adj_corr,
            "adjusted_delta": adj_delta,
            "n_eff": int(metrics.get("n_eff", 0) or 0),
            "raw_strength": float(raw_strength),
            "adjusted_strength": float(adjusted_strength),
            "ci_signal_score": float(_clip01((0.70 * ci_signal + 0.30 * innovation_score * max(raw_strength, CAL.CI_SIGNAL_DENOM_MIN)) / max(CAL.CI_SIGNAL_DENOM_MIN, raw_strength))),
            "parent_competition_score": float(parent_score),
            "parent_competition_pass": int(parent_pass),
            "innovation_score": innovation_score,
            "innovation_corr": innovation_corr,
            "innovation_beta_std": innovation_beta_std,
            "innovation_t": innovation_t,
            "innovation_pass": int(innovation.get("pass", 0) or 0),
            "survives_conditioning": int(survives),
        }


    def _orientation_summary(self, source: str, df: pd.DataFrame, selected_controls: Sequence[str], lag: int) -> dict:
        x = pd.to_numeric(df[source], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(df[self.cfg.target_col], errors="coerce").to_numpy(dtype=float)
        controls = [pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float) for c in selected_controls if c in df.columns and c != source]
        summary = _edge_orientation_signal(x, y, controls, lag, ar_lags=max(1, int(getattr(self.cfg, "discovery_target_ar_lags", 2))))
        score = float(summary.get("orientation_score", 0.0) or 0.0)
        passed = int(summary.get("pass", 0) or 0) == 1 and score >= float(getattr(self.cfg, "orientation_min_score", 0.55))
        summary["pass"] = int(passed)
        return summary

    def _temporal_consensus_summary(self, source: str, df: pd.DataFrame, selected_controls: Sequence[str], lag: int) -> dict:
        x = pd.to_numeric(df[source], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(df[self.cfg.target_col], errors="coerce").to_numpy(dtype=float)
        control_names = [c for c in selected_controls if c in df.columns and c != source]
        controls = [pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float) for c in control_names]
        n = len(y)
        n_splits = max(2, int(getattr(self.cfg, "consensus_n_splits", 3)))
        min_seg_n = max(lag + 12, int(getattr(self.cfg, "consensus_min_segment_n", 36)))
        if n < max(min_seg_n * 2, lag + 20):
            return {"score": np.nan, "pass_rate": np.nan, "sign_consistency": np.nan, "segments": 0, "pass": 0}
        edges = np.linspace(0, n, n_splits + 1, dtype=int)
        segment_scores = []
        pass_flags = []
        sign_votes = []
        for start, end in zip(edges[:-1], edges[1:]):
            if end - start < min_seg_n:
                continue
            xs = x[start:end]
            ys = y[start:end]
            ctrls = [z[start:end] for z in controls]
            summary = _temporal_conditional_signal(xs, ys, ctrls, lag, ar_lags=max(1, int(getattr(self.cfg, "discovery_target_ar_lags", 2))))
            score = float(summary.get("screen_score", 0.0) or 0.0)
            beta = float(summary.get("conditional_beta", np.nan))
            tstat = float(summary.get("conditional_t", np.nan))
            passed = int(summary.get("pass", 0) or 0) == 1
            segment_scores.append(score)
            pass_flags.append(1 if passed else 0)
            if np.isfinite(beta) and abs(tstat) >= 1.0 and beta != 0:
                sign_votes.append(1 if beta > 0 else -1)
        if not segment_scores:
            return {"score": np.nan, "pass_rate": np.nan, "sign_consistency": np.nan, "segments": 0, "pass": 0}
        pass_rate = float(np.mean(pass_flags)) if pass_flags else np.nan
        if sign_votes:
            major = 1 if sum(sign_votes) >= 0 else -1
            sign_consistency = float(np.mean([1.0 if s == major else 0.0 for s in sign_votes]))
        else:
            sign_consistency = np.nan
        med_score = float(np.nanmedian(segment_scores))
        score = float(_clip01(0.60 * med_score + 0.25 * (pass_rate if np.isfinite(pass_rate) else 0.0) + 0.15 * (sign_consistency if np.isfinite(sign_consistency) else 0.5)))
        passed = (
            (pass_rate if np.isfinite(pass_rate) else 0.0) >= float(getattr(self.cfg, "consensus_min_pass_rate", 0.60))
            and (sign_consistency if np.isfinite(sign_consistency) else 0.5) >= float(getattr(self.cfg, "consensus_min_sign_consistency", 0.66))
        )
        return {
            "score": score,
            "pass_rate": pass_rate,
            "sign_consistency": sign_consistency,
            "segments": int(len(segment_scores)),
            "pass": int(passed),
        }


    def _resolve_dag_annotation(self, source: str) -> Dict[str, object]:
        if self.dag is None:
            return {
                "dag_known": 0,
                "dag_node_type": "unknown",
                "dag_intervenable": 0,
                "dag_action_name": "",
                "dag_expected_direction": "",
                "dag_risk_paths": "",
                "dag_review_flag": 0,
            }
        return self.dag.l25_annotation(source)

    def _causal_screen_summary(self, source: str, df: pd.DataFrame, selected_controls: Sequence[str], lag: int) -> dict:
        x = pd.to_numeric(df[source], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(df[self.cfg.target_col], errors="coerce").to_numpy(dtype=float)
        controls = [pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float) for c in selected_controls if c in df.columns and c != source]
        summary = _temporal_conditional_signal(x, y, controls, lag, ar_lags=max(1, int(getattr(self.cfg, "discovery_target_ar_lags", 2))))
        incr = float(summary.get("incremental_r2", np.nan))
        beta_std = float(summary.get("conditional_beta_std", np.nan))
        passed = int(summary.get("pass", 0)) == 1
        if np.isfinite(incr):
            passed = passed and incr >= float(getattr(self.cfg, "causal_min_incremental_r2", 0.008))
        if np.isfinite(beta_std):
            passed = passed and abs(beta_std) >= float(getattr(self.cfg, "causal_min_beta_abs", 0.03))
        summary["pass"] = int(passed)
        return summary



    def _expand_hypothesis_variants(self, base_row: dict) -> List[dict]:
        rows: List[dict] = []
        base = dict(base_row)
        base["hypothesis_layer"] = "generation"
        base["hypothesis_variant"] = "base"
        base["candidate_context"] = ""
        base["candidate_stratum"], base["candidate_stratum_rationale"], base["candidate_stratum_confidence"] = self._infer_candidate_stratum(base)
        base_graph_fields = self._graph_link_fields(_as_str(base.get("harm_node_candidate", "")))
        base.update(base_graph_fields)
        base.update(self._local_causal_dag_fields(
            source=_as_str(base.get("source", "")),
            target=_as_str(base.get("target_col", self.cfg.target_col)),
            mediator_hint=_as_str(base.get("mediator_hint", "")),
            confounder_hint=_as_str(base.get("confounder_hint", "")),
            graph_fields=base_graph_fields,
        ))
        base["alternative_explanations"], base["alternative_explanations_tier"] = self._alternative_explanations(base)
        rows.append(base)

        confounds = [x for x in _as_str(base.get("confounder_hint", "")).split("|") if x]
        supports = [x for x in _as_str(base.get("supporting_features", "")).split("|") if x]
        contexts: List[str] = []
        for c in confounds[:2]:
            if c and c != base.get("source"):
                contexts.append(c)
        for c in supports[:1]:
            if c and c != base.get("source") and c not in contexts:
                contexts.append(c)
        if _safe_float(base.get("regime_shift_score", float("nan")), 0.0) >= self.cfg.regime_shift_review_threshold:
            contexts.append("regime_shift_context")
        seen = set()
        for ctx in contexts:
            if ctx in seen:
                continue
            seen.add(ctx)
            row = dict(base)
            row["hypothesis_variant"] = "contextualized"
            row["candidate_context"] = ctx
            row["path_statement"] = f"{base.get('action_name','action')} may increase risk in context '{ctx}' via {base.get('mediator_hint','') or base.get('source','signal')}"
            row["validation_readiness_score"] = max(CAL.CONTEXT_READINESS_FLOOR, _safe_float(row.get("validation_readiness_score", 0.0), 0.0) - CAL.CONTEXT_READINESS_DELTA)
            row["priority_score"] = min(CAL.CONTEXT_PRIORITY_CAP, _safe_float(row.get("priority_score", 0.0), 0.0) + CAL.CONTEXT_PRIORITY_BONUS)
            row["discovery_focus"] = "path_hypothesis_contextualized"
            row["candidate_stratum"], row["candidate_stratum_rationale"], row["candidate_stratum_confidence"] = self._infer_candidate_stratum(row)
            row_graph_fields = self._graph_link_fields(_as_str(row.get("harm_node_candidate", "")))
            row.update(row_graph_fields)
            row.update(self._local_causal_dag_fields(
                source=_as_str(row.get("source", "")),
                target=_as_str(row.get("target_col", self.cfg.target_col)),
                mediator_hint=_as_str(row.get("mediator_hint", "")),
                confounder_hint=_as_str(row.get("confounder_hint", "")),
                graph_fields=row_graph_fields,
            ))
            row["alternative_explanations"], row["alternative_explanations_tier"] = self._alternative_explanations(row)
            rows.append(row)
        return rows

    def run(self, data_csv_path: Optional[str] = None) -> pd.DataFrame:
        cfg = self.cfg
        _ensure_out(cfg.out_dir)
        df, data_path = self._load_df(data_csv_path)
        if cfg.target_col not in df.columns:
            raise ValueError(f"Target column '{cfg.target_col}' not found")
        self._outcome_profile = self._profile_outcome(df[cfg.target_col])
        y = pd.to_numeric(df[cfg.target_col], errors="coerce").to_numpy(dtype=float)
        candidates = self._candidate_columns(df)
        if len(candidates) == 0:
            empty = self._empty_outputs()
            empty_views = self._build_candidate_views(empty.copy())
            paths = self._write_outputs(empty, empty_views, DiscoveryContext())
            self._print_summary(data_path, empty, empty_views, paths)
            return empty_views["insights"]

        discovery_ctx = DiscoveryContext()
        proposals = self._layer1_generate_hypotheses(df, candidates, y, discovery_ctx)
        proposals, kept = self._finalize_proposals(proposals, df)
        candidate_views = self._build_candidate_views(kept)
        paths = self._write_outputs(proposals, candidate_views, discovery_ctx)
        self._print_summary(data_path, proposals, candidate_views, paths)
        return candidate_views["insights"]


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pcmci_core.py",
        description="PCB Level 2.5 — PCMCI-style discovery core",
    )
    p.add_argument("--data", default=None, help="Optional path to data csv")
    p.add_argument("--target", default=None, help="Optional override for target column")
    p.add_argument("--max-lag", default=None, type=int, help="Optional max lag override")
    p.add_argument("--out-dir", default=None, help="Optional output directory override")
    p.add_argument("--config", default="pcb.json", help="Optional config path override")
    p.add_argument("--discovery-mode", choices=["conservative", "balanced", "exploratory"], default=None,
                   help="Discovery-only strictness preset. Does not relax runtime veto/policy gates.")
    return p


def main(data_csv_path: Optional[str] = None, target_col: Optional[str] = None, max_lag: Optional[int] = None, out_dir: Optional[str] = None, config_path: str = "pcb.json", discovery_mode: Optional[str] = None):
    cfg = ProposalConfig.load(config_path)
    if discovery_mode:
        cfg.discovery_mode = str(discovery_mode)
        cfg.apply_discovery_mode()
    if target_col:
        cfg.target_col = str(target_col)
    if max_lag is not None:
        cfg.max_lag = int(max_lag)
    if out_dir:
        cfg.out_dir = str(out_dir)
    engine = ProposalEngine(cfg)
    return engine.run(data_csv_path=data_csv_path)


def cli(argv: Optional[Sequence[str]] = None) -> int:
    args = build_argparser().parse_args(sys.argv[1:] if argv is None else argv)
    main(data_csv_path=args.data, target_col=args.target, max_lag=args.max_lag, out_dir=args.out_dir, config_path=args.config, discovery_mode=args.discovery_mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
