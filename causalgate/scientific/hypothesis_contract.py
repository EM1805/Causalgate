from __future__ import annotations

"""Scientific hypothesis contract for CausalGate.

Canonical boundary object for LLM/research-agent scientific hypotheses. The
contract keeps claims at candidate level, normalizes compact DAG formats, splits
negative-control variables from prose tests, and exposes an SCM-ID-shaped query.
Mathematical conjectures are handled as proof/counterexample candidates rather
than empirical causal packages.
"""

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .claim_levels import normalize_claim_level


def _legacy_claim_level(level_key: str) -> str:
    return {
        "blocked": "blocked",
        "speculative_idea": "observation_only",
        "candidate_hypothesis": "hypothesis_only",
        "testable_hypothesis": "testable_candidate",
        "statistically_supported": "supported_candidate",
        "causally_identified": "identified_candidate",
        "experimentally_validated": "experimentally_validated",
        "independently_replicated": "validated_external",
        "observation_only": "observation_only",
        "hypothesis_only": "hypothesis_only",
        "testable_candidate": "testable_candidate",
        "supported_candidate": "supported_candidate",
        "identified_candidate": "identified_candidate",
        "validated_external": "validated_external",
        "conjecture_candidate": "hypothesis_only",
        "proof_or_counterexample_candidate": "hypothesis_only",
    }.get(str(level_key or ""), "hypothesis_only")


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _clean_lower(value: Any, default: str = "") -> str:
    text = _clean_str(value, default).lower()
    return text if text else default


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, Mapping)):
        return list(value)
    return [value]


def _as_str_list(value: Any) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in _as_list(value):
        text = _clean_str(item)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _dedupe_str_list(values: Iterable[Any]) -> List[str]:
    return _as_str_list(list(values))


def _first_text(*values: Any) -> str:
    for value in values:
        text = _clean_str(value)
        if text:
            return text
    return ""


def _looks_like_variable_name(text: str) -> bool:
    text = _clean_str(text)
    if not text or len(text) > 80:
        return False
    if any(ch.isspace() for ch in text):
        return False
    if any(ch in text for ch in (".", ",", ";", ":", "?", "!", "(", ")", "[", "]", "{", "}")):
        return False
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\-./]*", text))


def _split_negative_control_items(value: Any) -> Tuple[List[str], List[str]]:
    variables: List[str] = []
    tests: List[str] = []
    for item in _as_list(value):
        if isinstance(item, Mapping):
            variable = _first_text(item.get("variable"), item.get("node"), item.get("node_id"), item.get("outcome"), item.get("exposure"), item.get("name"), item.get("id"))
            description = _first_text(item.get("test"), item.get("description"), item.get("rationale"), item.get("assumption"), item.get("expected_result"))
            if variable:
                (variables if _looks_like_variable_name(variable) else tests).append(variable)
            if description:
                tests.append(description)
            continue
        text = _clean_str(item)
        if text:
            (variables if _looks_like_variable_name(text) else tests).append(text)
    return _dedupe_str_list(variables), _dedupe_str_list(tests)


def _normalize_node(node: Any) -> Dict[str, Any]:
    if isinstance(node, Mapping):
        out = dict(node)
        node_id = _first_text(out.get("id"), out.get("node_id"), out.get("name"), out.get("variable"))
        if node_id:
            out["id"] = node_id
            out.setdefault("node_id", node_id)
            out.setdefault("observed", True)
        return out
    node_id = _clean_str(node)
    return {"id": node_id, "node_id": node_id, "observed": True} if node_id else {}


def _edge_from_pair(pair: Any, edge_kind: str = "directed") -> Dict[str, Any]:
    parts = _as_list(pair)
    if len(parts) >= 2:
        return {"source": _clean_str(parts[0]), "target": _clean_str(parts[1]), "edge_kind": edge_kind}
    return {}


def _normalize_edge(edge: Any) -> Dict[str, Any]:
    if isinstance(edge, Mapping):
        out = dict(edge)
        source = _first_text(out.get("source"), out.get("from"), out.get("src"))
        target = _first_text(out.get("target"), out.get("to"), out.get("dst"))
        if source:
            out["source"] = source
        if target:
            out["target"] = target
        out.setdefault("edge_kind", _first_text(out.get("edge_kind"), out.get("edge_type"), "directed"))
        return out
    return _edge_from_pair(edge, "directed")


def normalize_dag(dag: Any, variables: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    raw = _as_dict(dag)
    variables = _as_dict(variables)
    nodes = [_normalize_node(n) for n in _as_list(raw.get("nodes"))]
    edges = [_normalize_edge(e) for e in _as_list(raw.get("edges"))]
    edges.extend(_edge_from_pair(e, "directed") for e in _as_list(raw.get("directed_edges")))
    edges.extend(_edge_from_pair(e, "bidirected") for e in _as_list(raw.get("bidirected_edges")))
    node_ids: List[str] = []
    for node in nodes:
        node_id = _first_text(node.get("node_id"), node.get("id"))
        if node_id and node_id not in node_ids:
            node_ids.append(node_id)
    variable_candidates: List[Any] = []
    for key in ("treatment", "outcome", "treatments", "outcomes", "mediators", "confounders", "controls", "negative_controls", "negative_control_variables", "negative_control_outcomes", "negative_control_exposures"):
        variable_candidates.extend(_as_list(variables.get(key)))
    for edge in edges:
        variable_candidates.extend([edge.get("source"), edge.get("target")])
    for item in variable_candidates:
        node_id = _clean_str(item)
        if node_id and node_id not in node_ids:
            node_ids.append(node_id)
            nodes.append({"id": node_id, "node_id": node_id, "observed": True})
    clean_edges = []
    seen_edges = set()
    for edge in edges:
        source = _clean_str(edge.get("source"))
        target = _clean_str(edge.get("target"))
        kind = _clean_str(edge.get("edge_kind"), "directed")
        key = (source, target, kind)
        if source and target and key not in seen_edges:
            seen_edges.add(key)
            clean_edges.append({**edge, "source": source, "target": target, "edge_kind": kind})
    return {**raw, "nodes": [n for n in nodes if _first_text(n.get("id"), n.get("node_id"))], "edges": clean_edges}


@dataclass
class ScientificHypothesisPackage:
    hypothesis_id: str = ""
    run_id: str = ""
    step: int = 0
    title: str = ""
    claim: str = ""
    claim_level: str = "hypothesis_only"
    claim_level_index: int = 2
    claim_level_key: str = "candidate_hypothesis"
    claim_level_label: str = "candidate hypothesis"
    domain: str = "unknown"
    hypothesis_kind: str = ""
    domain_diagnostic: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)
    treatment: str = ""
    outcome: str = ""
    treatments: List[str] = field(default_factory=list)
    outcomes: List[str] = field(default_factory=list)
    mediators: List[str] = field(default_factory=list)
    confounders: List[str] = field(default_factory=list)
    controls: List[str] = field(default_factory=list)
    candidate_equation: str = ""
    dag: Dict[str, Any] = field(default_factory=dict)
    assumptions: List[str] = field(default_factory=list)
    mechanism_plausible: str = ""
    identification_strategy: str = ""
    adjustment_set: List[str] = field(default_factory=list)
    observed_confounder_measurements: Dict[str, Any] = field(default_factory=dict)
    estimation_plan: str = ""
    counterfactual_query: str = ""
    falsification_tests: List[str] = field(default_factory=list)
    measurable_predictions: List[str] = field(default_factory=list)
    negative_controls: List[str] = field(default_factory=list)
    negative_control_variables: List[str] = field(default_factory=list)
    negative_control_tests: List[str] = field(default_factory=list)
    placebo_tests: List[str] = field(default_factory=list)
    sensitivity_checks: List[str] = field(default_factory=list)
    data_requirements: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    external_evidence_quality: Dict[str, Any] = field(default_factory=dict)
    simulation_plan: str = ""
    test_plan: str = ""
    conclusion_strength: str = "hypothesis_only"
    source: str = "llm_or_research_agent"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Optional[Mapping[str, Any]]) -> "ScientificHypothesisPackage":
        data = _as_dict(payload)
        if isinstance(data.get("hypothesis"), Mapping):
            wrapped = dict(data.get("hypothesis") or {})
            for k, v in data.items():
                if k != "hypothesis" and k not in wrapped:
                    wrapped[k] = v
            data = wrapped
        variables = _as_dict(data.get("variables"))
        treatment = _first_text(data.get("treatment"), variables.get("treatment"), data.get("cause"), data.get("x"))
        outcome = _first_text(data.get("outcome"), variables.get("outcome"), data.get("effect"), data.get("y"))
        treatments = _as_str_list(data.get("treatments") or variables.get("treatments") or ([treatment] if treatment else []))
        outcomes = _as_str_list(data.get("outcomes") or variables.get("outcomes") or ([outcome] if outcome else []))
        if not treatment and treatments:
            treatment = treatments[0]
        if not outcome and outcomes:
            outcome = outcomes[0]
        mediators = _as_str_list(data.get("mediators") or variables.get("mediators"))
        confounders = _as_str_list(data.get("confounders") or variables.get("confounders"))
        controls = _as_str_list(data.get("controls") or variables.get("controls") or data.get("adjustment_set"))
        nc_vars: List[str] = []
        nc_tests: List[str] = []
        for source in (data.get("negative_control_variables"), data.get("negative_control_outcomes"), data.get("negative_control_exposures"), variables.get("negative_control_variables"), variables.get("negative_control_outcomes"), variables.get("negative_control_exposures"), data.get("negative_controls"), variables.get("negative_controls")):
            split_vars, split_tests = _split_negative_control_items(source)
            nc_vars.extend(split_vars)
            nc_tests.extend(split_tests)
        explicit_nc_tests = _as_str_list(data.get("negative_control_tests") or data.get("negative_control_test_descriptions") or variables.get("negative_control_tests"))
        negative_control_variables = _dedupe_str_list(nc_vars)
        negative_control_tests = _dedupe_str_list([*nc_tests, *explicit_nc_tests])
        negative_controls = list(negative_control_variables)
        merged_variables = {**variables, "treatment": treatment, "outcome": outcome, "treatments": treatments, "outcomes": outcomes, "mediators": mediators, "confounders": confounders, "controls": controls, "negative_controls": negative_controls, "negative_control_variables": negative_control_variables, "negative_control_tests": negative_control_tests}
        dag = normalize_dag(data.get("dag") or data.get("scm_graph") or data.get("graph"), merged_variables)
        requested_claim_level = normalize_claim_level(data.get("claim_level") or data.get("requested_claim_level") or data.get("conclusion_strength") or data.get("scientific_claim_level"))
        claim_level = _legacy_claim_level(requested_claim_level.key)

        def _as_int(value: Any) -> int:
            try:
                return int(value)
            except Exception:
                return 0

        return cls(hypothesis_id=_first_text(data.get("hypothesis_id"), data.get("id"), data.get("candidate_id")), run_id=_clean_str(data.get("run_id")), step=_as_int(data.get("step")), title=_clean_str(data.get("title")), claim=_first_text(data.get("claim"), data.get("hypothesis_claim"), data.get("statement")), claim_level=claim_level, claim_level_index=requested_claim_level.index, claim_level_key=requested_claim_level.key, claim_level_label=requested_claim_level.label, domain=_clean_lower(data.get("domain"), "unknown"), hypothesis_kind=_clean_str(data.get("hypothesis_kind") or data.get("kind")), domain_diagnostic=_as_dict(data.get("domain_diagnostic")), variables=merged_variables, treatment=treatment, outcome=outcome, treatments=treatments, outcomes=outcomes, mediators=mediators, confounders=confounders, controls=controls, candidate_equation=_first_text(data.get("candidate_equation"), data.get("equation"), data.get("formula")), dag=dag, assumptions=_as_str_list(data.get("assumptions")), mechanism_plausible=_clean_str(data.get("mechanism_plausible") or data.get("mechanism")), identification_strategy=_clean_str(data.get("identification_strategy") or data.get("strategy_hint")), adjustment_set=_as_str_list(data.get("adjustment_set") or controls), observed_confounder_measurements=_as_dict(data.get("observed_confounder_measurements") or data.get("confounder_measurements")), estimation_plan=_clean_str(data.get("estimation_plan") or data.get("analysis_plan")), counterfactual_query=_clean_str(data.get("counterfactual_query") or data.get("causal_query")), falsification_tests=_as_str_list(data.get("falsification_tests") or data.get("falsification_plan")), measurable_predictions=_as_str_list(data.get("measurable_predictions") or data.get("falsifiable_predictions") or data.get("observable_predictions") or data.get("predictions")), negative_controls=negative_controls, negative_control_variables=negative_control_variables, negative_control_tests=negative_control_tests, placebo_tests=_as_str_list(data.get("placebo_tests") or data.get("temporal_placebo_tests") or data.get("placebos")), sensitivity_checks=_as_str_list(data.get("sensitivity_checks") or data.get("sensitivity_tests") or data.get("hidden_confounding_checks")), data_requirements=_as_str_list(data.get("data_requirements") or data.get("required_data")), evidence_refs=_as_str_list(data.get("evidence_refs") or data.get("references") or data.get("literature_refs")), external_evidence_quality=_as_dict(data.get("external_evidence_quality")), simulation_plan=_clean_str(data.get("simulation_plan")), test_plan=_clean_str(data.get("test_plan")), conclusion_strength=_legacy_claim_level(normalize_claim_level(data.get("conclusion_strength") or claim_level).key), source=_clean_str(data.get("source"), "llm_or_research_agent"), metadata=_as_dict(data.get("metadata")))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_identification_query(self) -> Dict[str, Any]:
        return {"treatment": self.treatment, "outcome": self.outcome, "treatments": list(self.treatments or ([self.treatment] if self.treatment else [])), "outcomes": list(self.outcomes or ([self.outcome] if self.outcome else [])), "adjustment_set": list(self.adjustment_set), "mediators": list(self.mediators), "confounders": list(self.confounders), "negative_control_variables": list(self.negative_control_variables or self.negative_controls), "scm_graph": dict(self.dag), "query_id": self.hypothesis_id, "claim_level": self.claim_level_key, "claim_level_index": self.claim_level_index, "source": "causalgate.scientific.hypothesis_contract"}

    def _is_math(self) -> bool:
        return self.domain == "mathematical" or self.hypothesis_kind == "mathematical_conjecture" or self.claim.lower().startswith("candidate mathematical conjecture")

    def missing_core_items(self) -> List[str]:
        missing: List[str] = []
        if not self.claim:
            missing.append("claim")
        if self._is_math():
            if not self.assumptions:
                missing.append("definitions_or_axioms")
            if not self.falsification_tests:
                missing.append("counterexample_search")
            if not self.data_requirements:
                missing.append("formal_statement_and_boundary_cases")
            return missing
        if not (self.treatment or self.treatments):
            missing.append("treatment_or_cause")
        if not (self.outcome or self.outcomes):
            missing.append("outcome_or_effect")
        if not self.dag.get("nodes") or not self.dag.get("edges"):
            missing.append("dag_with_nodes_and_edges")
        if not self.assumptions:
            missing.append("assumptions")
        if not self.falsification_tests:
            missing.append("falsification_tests")
        if not self.data_requirements:
            missing.append("data_requirements")
        return missing


def normalize_scientific_hypothesis(payload: Optional[Mapping[str, Any]]) -> ScientificHypothesisPackage:
    return ScientificHypothesisPackage.from_dict(payload)


__all__ = ["ScientificHypothesisPackage", "normalize_scientific_hypothesis", "normalize_dag"]
