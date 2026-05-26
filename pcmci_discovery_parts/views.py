
from runtime_env import configure_scientific_runtime
configure_scientific_runtime()

from .engine_common import *
import numpy as np
import pandas as pd


class CandidateViewMixin:
    _EMPTY_VIEW_SCHEMAS = {
        "path_candidates": ["insight_id", "discovery_track", "hypothesis_variant", "candidate_context", "path_id_candidate", "action_name", "action_type", "source", "mediator_candidate", "context_feature_candidate", "harm_node_candidate", "harm_label", "path_statement", "harm_hypothesis", "candidate_stratum", "candidate_stratum_rationale", "candidate_stratum_confidence", "local_causal_graph", "candidate_adjustment_set", "forbidden_variables", "identification_status", "local_dag_assumptions", "local_dag_json", "graph_contrast_key", "graph_treated_value", "graph_control_value", "graph_preferred_stratum_keys", "graph_adjustment_hint", "graph_forbidden_adjustment_hint", "alternative_explanations", "alternative_explanations_tier", "priority_score", "discovery_evidence_score", "selection_score", "hypothesis_signal_score", "safety_risk_score", "hypothesis_signal_grade", "safety_risk_grade", "risk_flags", "reason_codes", "trial_design_hint"],
        "mediator_candidates": ["insight_id", "discovery_track", "source", "action_name", "mediator_candidate", "harm_node_candidate", "priority_score", "selection_score"],
        "context_features": ["insight_id", "discovery_track", "action_name", "context_feature_candidate", "harm_node_candidate", "priority_score", "selection_score"],
        "harm_hypotheses": ["insight_id", "discovery_track", "hypothesis_variant", "candidate_context", "action_name", "source", "harm_node_candidate", "harm_label", "harm_hypothesis", "harm_hypothesis_origin", "candidate_stratum", "identification_status", "priority_score", "selection_score", "hypothesis_signal_score", "safety_risk_score"],
        "strata_candidates": ["insight_id", "discovery_track", "hypothesis_variant", "action_name", "source", "candidate_stratum", "candidate_stratum_rationale", "candidate_stratum_confidence", "candidate_adjustment_set", "forbidden_variables", "identification_status", "priority_score", "selection_score", "hypothesis_signal_score", "safety_risk_score"],
        "alternative_explanations": ["insight_id", "discovery_track", "hypothesis_variant", "action_name", "source", "harm_label", "alternative_explanations", "alternative_explanations_tier", "confounder_hint", "priority_score", "selection_score"],
        "validation_plan": ["insight_id", "discovery_track", "hypothesis_variant", "action_name", "source", "source_role", "edge_family", "validation_design", "treatment_col", "treatment_role", "outcome_col", "outcome_role", "preferred_estimand", "candidate_covariates", "post_treatment_columns", "path_id_candidate", "harm_node_candidate", "candidate_stratum", "candidate_stratum_confidence", "local_causal_graph", "identification_status", "local_dag_assumptions", "recommended_validation", "validation_priority_tier", "suggested_adjustment_set", "adjustment_set_confidence", "forbidden_adjustment_set", "forbidden_adjustment_confidence", "priority_score", "discovery_evidence_score", "selection_score", "hypothesis_signal_score", "safety_risk_score", "validation_plan_rationale"],
    }

    def _empty_view(self, name: str) -> pd.DataFrame:
        return pd.DataFrame(columns=list(self._EMPTY_VIEW_SCHEMAS.get(name, [])))

    def _build_candidate_views(self, kept: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        if len(kept) == 0:
            return {
                "path_candidates": self._empty_view("path_candidates"),
                "mediator_candidates": self._empty_view("mediator_candidates"),
                "context_features": self._empty_view("context_features"),
                "harm_hypotheses": self._empty_view("harm_hypotheses"),
                "strata_candidates": self._empty_view("strata_candidates"),
                "alternative_explanations": self._empty_view("alternative_explanations"),
                "validation_plan": self._empty_view("validation_plan"),
                "insights": kept.copy(),
            }
        enriched = kept.copy()
        payloads = [self._derive_path_payload(r) for _, r in enriched.iterrows()]
        payload_df = pd.DataFrame(payloads)
        # Overlay derived path fields instead of concatenating them.  Some fields
        # (for example discovery_focus/path_statement) may already exist on the
        # Discovery row; assigning keeps the CSV schema unique and makes the
        # path payload the authoritative validation-layer view.
        enriched = enriched.reset_index(drop=True)
        payload_df = payload_df.reset_index(drop=True)
        for col in payload_df.columns:
            enriched[col] = payload_df[col]
        enriched["recommendation"] = enriched["path_id_candidate"]
        enriched["proposal_stage"] = "path_candidate_generation"
        enriched["discovery_track"] = enriched.get("discovery_track", "high_confidence")
        enriched["causal_interpretation_level"] = "path_hypothesis_only"
        enriched["veto_candidate"] = 0
        enriched["human_statement"] = enriched.apply(lambda r: f"Path candidate '{r['path_id_candidate']}' suggests action '{r['action_name']}' may contribute to {r['harm_label']} via '{r['mediator_candidate'] or r['source']}'. Validate via path evidence/counterfactual layers before any veto.", axis=1)

        path_cols = [c for c in ["insight_id","discovery_track","hypothesis_variant","candidate_context","path_id_candidate","action_name","action_type","source","mediator_candidate","context_feature_candidate","harm_node_candidate","harm_label","path_statement","harm_hypothesis","candidate_stratum","candidate_stratum_rationale","candidate_stratum_confidence","local_causal_graph","candidate_adjustment_set","forbidden_variables","identification_status","local_dag_assumptions","local_dag_json","graph_contrast_key","graph_treated_value","graph_control_value","graph_preferred_stratum_keys","graph_adjustment_hint","graph_forbidden_adjustment_hint","alternative_explanations","alternative_explanations_tier","priority_score","discovery_evidence_score","selection_score","hypothesis_signal_score","safety_risk_score","hypothesis_signal_grade","safety_risk_grade","risk_flags","reason_codes","trial_design_hint"] if c in enriched.columns]
        path_candidates = enriched[path_cols].copy()

        mediator_rows = []
        for _, r in enriched.iterrows():
            meds = [m for m in _as_str(r.get("mediator_hint", "")).split("|") if m]
            if not meds and _as_str(r.get("mediator_candidate", "")):
                meds = [_as_str(r.get("mediator_candidate", ""))]
            for m in meds[:5]:
                mediator_rows.append({
                    "insight_id": r.get("insight_id", ""),
                    "discovery_track": r.get("discovery_track", ""),
                    "source": r.get("source", ""),
                    "action_name": r.get("action_name", ""),
                    "mediator_candidate": m,
                    "harm_node_candidate": r.get("harm_node_candidate", ""),
                    "priority_score": r.get("priority_score", np.nan),
                    "selection_score": r.get("selection_score", np.nan),
                })
        mediator_candidates = pd.DataFrame(mediator_rows)

        context_rows = []
        for _, r in enriched.iterrows():
            ctxs = [m for m in _as_str(r.get("confounder_hint", "")).split("|") if m]
            if not ctxs and _as_str(r.get("context_feature_candidate", "")):
                ctxs = [_as_str(r.get("context_feature_candidate", ""))]
            for c in ctxs[:5]:
                context_rows.append({
                    "insight_id": r.get("insight_id", ""),
                    "discovery_track": r.get("discovery_track", ""),
                    "action_name": r.get("action_name", ""),
                    "context_feature_candidate": c,
                    "harm_node_candidate": r.get("harm_node_candidate", ""),
                    "priority_score": r.get("priority_score", np.nan),
                    "selection_score": r.get("selection_score", np.nan),
                })
        context_features = pd.DataFrame(context_rows)

        harm_hypotheses = enriched[[c for c in ["insight_id","discovery_track","hypothesis_variant","candidate_context","action_name","source","harm_node_candidate","harm_label","harm_hypothesis","harm_hypothesis_origin","candidate_stratum","identification_status","priority_score","selection_score","hypothesis_signal_score","safety_risk_score"] if c in enriched.columns]].copy()
        strata_candidates = enriched[[c for c in ["insight_id","discovery_track","hypothesis_variant","action_name","source","candidate_stratum","candidate_stratum_rationale","candidate_stratum_confidence","candidate_adjustment_set","forbidden_variables","identification_status","priority_score","selection_score","hypothesis_signal_score","safety_risk_score"] if c in enriched.columns]].copy()
        alternative_views = enriched[[c for c in ["insight_id","discovery_track","hypothesis_variant","action_name","source","harm_label","alternative_explanations","alternative_explanations_tier","confounder_hint","priority_score","selection_score","hypothesis_signal_score","safety_risk_score"] if c in enriched.columns]].copy()
        validation_plan = self._build_validation_plan(enriched)
        return {"path_candidates": path_candidates, "mediator_candidates": mediator_candidates, "context_features": context_features, "harm_hypotheses": harm_hypotheses, "strata_candidates": strata_candidates, "alternative_explanations": alternative_views, "validation_plan": validation_plan, "insights": enriched}


    def _graph_link_fields(self, harm_node: str) -> dict:
        if self.op_graph is None or not harm_node:
            return {
                "graph_contrast_key": "",
                "graph_treated_value": "",
                "graph_control_value": "",
                "graph_preferred_stratum_keys": "",
                "graph_adjustment_hint": "",
                "graph_forbidden_adjustment_hint": "",
            }
        hint = self.op_graph.path_hint_for_harm(harm_node)
        return {
            "graph_contrast_key": _as_str(hint.get("contrast_key", "")),
            "graph_treated_value": json.dumps(hint.get("treated_value")) if hint.get("treated_value", "") != "" else "",
            "graph_control_value": json.dumps(hint.get("control_value")) if hint.get("control_value", "") != "" else "",
            "graph_preferred_stratum_keys": "|".join([_as_str(x) for x in (hint.get("preferred_stratum_keys", []) or []) if _as_str(x)]),
            "graph_adjustment_hint": "|".join([_as_str(x) for x in (hint.get("adjust_for", []) or []) if _as_str(x)]),
            "graph_forbidden_adjustment_hint": "|".join([_as_str(x) for x in (hint.get("avoid", []) or []) if _as_str(x)]),
        }


    def _local_causal_dag_fields(self, source: str, target: str, mediator_hint: str, confounder_hint: str, graph_fields: dict) -> dict:
        dag_bits: List[str] = []
        seen_edges = set()

        def add_edge(left: str, right: str) -> None:
            left = _as_str(left)
            right = _as_str(right)
            if not left or not right:
                return
            edge = f"{left}->{right}"
            if edge not in seen_edges:
                seen_edges.add(edge)
                dag_bits.append(edge)

        source_resolved = _as_str(source)
        target_resolved = _as_str(target)
        mediator = next((x for x in _as_str(mediator_hint).split('|') if x), '')
        confounders = [x for x in _as_str(confounder_hint).split('|') if x][:3]
        graph_adj = [x for x in _as_str(graph_fields.get('graph_adjustment_hint', '')).split('|') if x]
        graph_forbidden = [x for x in _as_str(graph_fields.get('graph_forbidden_adjustment_hint', '')).split('|') if x]

        l32 = self.dag.l32_annotation(source_resolved, target_resolved) if self.dag is not None else {}
        dag_adj = [x for x in _as_str(l32.get('dag_adjustment_set', '')).split('|') if x]
        dag_forbidden = [x for x in _as_str(l32.get('dag_forbidden_adjustments', '')).split('|') if x]
        adjustment = list(dict.fromkeys([x for x in dag_adj + graph_adj + confounders if x and x not in {source_resolved, target_resolved, mediator}]))
        forbidden = list(dict.fromkeys([x for x in dag_forbidden + graph_forbidden + ([mediator] if mediator else []) if x]))

        for c in confounders:
            add_edge(c, source_resolved)
            add_edge(c, target_resolved)
        if mediator:
            add_edge(source_resolved, mediator)
            add_edge(mediator, target_resolved)
        else:
            add_edge(source_resolved, target_resolved)

        direct_conf = _as_str(l32.get('dag_direct_edge_confidence', 'unknown'))
        path_conf = _as_str(l32.get('dag_path_confidence', 'unknown'))
        adj_conf = _as_str(l32.get('dag_adjustment_confidence', 'unknown'))
        action_known = int(l32.get('dag_action_known', 0) or 0) == 1
        target_known = int(l32.get('dag_target_known', 0) or 0) == 1
        has_adjustment = len(adjustment) > 0
        if action_known and target_known and has_adjustment and path_conf in {'medium', 'high'}:
            identification_status = 'identified'
        elif (action_known or target_known) and (has_adjustment or confounders or mediator or path_conf in {'low', 'medium', 'high'}):
            identification_status = 'partially_identified'
        else:
            identification_status = 'not_identified'

        assumptions: List[str] = []
        if action_known and target_known:
            assumptions.append('dag_mapping_available')
        if has_adjustment:
            assumptions.append('backdoor_adjustment_candidate_available')
        if mediator:
            assumptions.append('mediator_excluded_from_adjustment')
        if path_conf in {'medium', 'high'}:
            assumptions.append('dag_path_support')

        return {
            'local_causal_graph': '; '.join(dag_bits),
            'local_dag_json': json.dumps({
                'treatment': source_resolved,
                'outcome': target_resolved,
                'confounders': confounders,
                'mediators': [mediator] if mediator else [],
                'adjustment_set': adjustment,
                'forbidden_adjustment_set': forbidden,
                'direct_edge_confidence': direct_conf,
                'path_confidence': path_conf,
                'adjustment_confidence': adj_conf,
            }, ensure_ascii=False),
            'candidate_adjustment_set': '|'.join(adjustment),
            'suggested_adjustment_set': '|'.join(adjustment),
            'adjustment_set_confidence': adj_conf,
            'forbidden_variables': '|'.join(forbidden),
            'forbidden_adjustment_set': '|'.join(forbidden),
            'forbidden_adjustment_confidence': 'high' if mediator or dag_forbidden else 'medium' if graph_forbidden else 'low',
            'identification_status': identification_status,
            'local_dag_assumptions': '|'.join(assumptions),
            'local_dag_treatment': source_resolved,
            'local_dag_outcome': target_resolved,
            'local_dag_mediator': mediator,
            'local_dag_confounders': '|'.join(confounders),
            'local_dag_edge_confidence': direct_conf or path_conf or 'unknown',
        }


    def _build_validation_plan(self, enriched: pd.DataFrame) -> pd.DataFrame:
        if len(enriched) == 0:
            return pd.DataFrame()
        rows = []
        for _, r in enriched.iterrows():
            track = _as_str(r.get("discovery_track", ""))
            stratum = _as_str(r.get("candidate_stratum", ""))
            stratum_conf = _as_str(r.get("candidate_stratum_confidence", "low"))
            priority = _safe_float(r.get("priority_score", np.nan), 0.0)
            evidence = _safe_float(r.get("discovery_evidence_score", np.nan), 0.0)
            selection = _safe_float(r.get("selection_score", np.nan), 0.0)
            signal = _safe_float(r.get("hypothesis_signal_score", np.nan), 0.0)
            safety_risk = _safe_float(r.get("safety_risk_score", np.nan), 1.0)
            if stratum and stratum_conf in {"medium", "high"} and selection >= 0.45:
                recommended = "within_stratum_matched_did"
            elif stratum:
                recommended = "within_stratum_screen_then_counterfactual"
            else:
                recommended = "global_screen_then_counterfactual"
            if track == "high_confidence" and signal >= 0.55:
                tier = "priority_validation"
            elif track == "exploratory":
                tier = "exploratory_validation"
            else:
                tier = "research_backlog"
            rationale_bits = []
            if stratum:
                rationale_bits.append(f"test within candidate stratum {stratum}")
            if _as_str(r.get("graph_preferred_stratum_keys", "")):
                rationale_bits.append(f"use graph stratum keys {_as_str(r.get('graph_preferred_stratum_keys', ''))}")
            if _as_str(r.get("suggested_adjustment_set", "")) or _as_str(r.get("graph_adjustment_hint", "")):
                rationale_bits.append("apply suggested adjustment set")
            if _as_str(r.get("forbidden_adjustment_set", "")):
                rationale_bits.append("avoid forbidden adjustment variables")
            if safety_risk >= 0.68:
                rationale_bits.append("safety risk is elevated so validate cautiously")
            rows.append({
                "insight_id": _as_str(r.get("insight_id", "")),
                "discovery_track": track,
                "hypothesis_variant": _as_str(r.get("hypothesis_variant", "")),
                "action_name": _as_str(r.get("action_name", "")),
                "source": _as_str(r.get("source", "")),
                "source_role": _as_str(r.get("source_role", "")),
                "edge_family": _as_str(r.get("edge_family", "")),
                "validation_design": _as_str(r.get("validation_design", "")),
                "treatment_col": _as_str(r.get("treatment_col", r.get("source", ""))),
                "treatment_role": _as_str(r.get("treatment_role", r.get("source_role", ""))),
                "outcome_col": _as_str(r.get("outcome_col", r.get("target_col", r.get("target", "")))),
                "outcome_role": _as_str(r.get("outcome_role", "outcome")),
                "preferred_estimand": _as_str(r.get("preferred_estimand", r.get("validation_design", ""))),
                "candidate_covariates": _as_str(r.get("candidate_covariates", "")) or _as_str(r.get("suggested_adjustment_set", "")) or _as_str(r.get("graph_adjustment_hint", "")),
                "post_treatment_columns": _as_str(r.get("post_treatment_columns", "")) or _as_str(r.get("forbidden_adjustment_set", "")) or _as_str(r.get("graph_forbidden_adjustment_hint", "")),
                "path_id_candidate": _as_str(r.get("path_id_candidate", "")),
                "harm_node_candidate": _as_str(r.get("harm_node_candidate", "")),
                "candidate_stratum": stratum,
                "candidate_stratum_confidence": stratum_conf,
                "local_causal_graph": _as_str(r.get("local_causal_graph", "")),
                "identification_status": _as_str(r.get("identification_status", "not_identified")),
                "local_dag_assumptions": _as_str(r.get("local_dag_assumptions", "")),
                "recommended_validation": recommended,
                "validation_priority_tier": tier,
                "suggested_adjustment_set": _as_str(r.get("suggested_adjustment_set", "")) or _as_str(r.get("graph_adjustment_hint", "")),
                "adjustment_set_confidence": _as_str(r.get("adjustment_set_confidence", "")),
                "forbidden_adjustment_set": _as_str(r.get("forbidden_adjustment_set", "")) or _as_str(r.get("graph_forbidden_adjustment_hint", "")),
                "forbidden_adjustment_confidence": _as_str(r.get("forbidden_adjustment_confidence", "")),
                "priority_score": priority,
                "discovery_evidence_score": evidence,
                "selection_score": selection,
                "hypothesis_signal_score": signal,
                "safety_risk_score": safety_risk,
                "validation_plan_rationale": "; ".join(rationale_bits),
            })
        return pd.DataFrame(rows)


