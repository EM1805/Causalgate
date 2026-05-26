from __future__ import annotations

"""Deterministic hypothesis repair agent for CausalGate.

This module applies small, auditable patches from CausalGate verdicts.  It is not a
creative science generator: it reads ``missing_items`` / ``reason_codes`` and
fills only the structural fields needed for the next veto pass while preserving
claim strength.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping
from uuid import uuid4

from .hypothesis_contract import normalize_scientific_hypothesis


REPAIRABLE_ITEMS = {
    "measurable_prediction",
    "adjustment_set",
    "observed_confounder_measurements",
    "identification_strategy",
    "test_plan_or_simulation_plan",
    "negative_control_outcome_or_exposure",
    "placebo_or_temporal_leakage_test",
}


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
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
    if isinstance(value, Iterable) and not isinstance(value, (Mapping, bytes, bytearray)):
        return list(value)
    return [value]


def _str_list(value: Any) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in _as_list(value):
        text = _clean_str(item)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _append_unique(values: Any, additions: Iterable[str]) -> List[str]:
    out = _str_list(values)
    seen = set(out)
    for item in additions:
        text = _clean_str(item)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _edge_pairs(dag: Mapping[str, Any]) -> List[tuple[str, str]]:
    pairs: List[tuple[str, str]] = []
    for edge in _as_list(dag.get("edges")):
        if isinstance(edge, Mapping):
            src = _clean_str(edge.get("source") or edge.get("from") or edge.get("src"))
            dst = _clean_str(edge.get("target") or edge.get("to") or edge.get("dst"))
        else:
            parts = _as_list(edge)
            src = _clean_str(parts[0]) if len(parts) >= 1 else ""
            dst = _clean_str(parts[1]) if len(parts) >= 2 else ""
        if src and dst:
            pairs.append((src, dst))
    for edge in _as_list(dag.get("directed_edges")):
        parts = _as_list(edge)
        if len(parts) >= 2:
            src, dst = _clean_str(parts[0]), _clean_str(parts[1])
            if src and dst:
                pairs.append((src, dst))
    return pairs


def _infer_confounders(hypothesis: Mapping[str, Any]) -> List[str]:
    hyp = normalize_scientific_hypothesis(hypothesis)
    if hyp.confounders:
        return list(hyp.confounders)
    treatment_nodes = set(hyp.treatments or ([hyp.treatment] if hyp.treatment else []))
    outcome_nodes = set(hyp.outcomes or ([hyp.outcome] if hyp.outcome else []))
    into_treatment = {src for src, dst in _edge_pairs(hyp.dag) if dst in treatment_nodes}
    into_outcome = {src for src, dst in _edge_pairs(hyp.dag) if dst in outcome_nodes}
    return sorted((into_treatment & into_outcome) - treatment_nodes - outcome_nodes)


def _measurement_for(name: str) -> str:
    compact = name.replace("_", " ").replace("-", " ").lower()
    if "age" in compact:
        return "Measured at baseline as age in years."
    if "socio" in compact or "income" in compact or "education" in compact:
        return "Measured at baseline using income, education, occupation, or neighborhood deprivation indicators."
    if "prior" in compact or "baseline" in compact or "pre" in compact:
        return "Measured before treatment using baseline outcome score or pre-intervention records."
    if "mental" in compact or "health" in compact:
        return "Measured at baseline using diagnosis history or a validated screening scale."
    return f"Measured at or before baseline with a documented variable for {name}."


def _infer_identification_strategy(hypothesis: Mapping[str, Any]) -> str:
    hyp = normalize_scientific_hypothesis(hypothesis)
    domain = _clean_str(hyp.domain).lower()
    kind = _clean_str(hypothesis.get("hypothesis_kind") or hypothesis.get("kind")).lower()
    if "math" in domain or "math" in kind or hyp.candidate_equation:
        return "Mathematical proof/counterexample protocol; no empirical causal identification claim is made."
    confounders = _infer_confounders(hypothesis)
    if confounders:
        return "Back-door adjustment using observed confounders: " + ", ".join(confounders) + "."
    if any("random" in text.lower() for text in hyp.assumptions + hyp.data_requirements + [hyp.test_plan]):
        return "Randomized assignment / experimental identification, subject to protocol fidelity and attrition checks."
    return "Prospective observational comparison with pre-specified adjustment; no stronger causal identification is claimed."


def _prediction(hypothesis: Mapping[str, Any]) -> str:
    hyp = normalize_scientific_hypothesis(hypothesis)
    x = hyp.treatment or "the treatment/exposure"
    y = hyp.outcome or "the outcome"
    return (
        f"Over the stated follow-up window, a measurable increase in {x} is predicted to be associated with "
        f"a directional change in {y} compared with the specified control/comparison group, after applying "
        "the stated adjustment set."
    )


def _test_plan(hypothesis: Mapping[str, Any]) -> str:
    hyp = normalize_scientific_hypothesis(hypothesis)
    if "math" in hyp.domain.lower() or hyp.candidate_equation:
        return "Use proof review, counterexample search, and independent computational verification; do not treat numerical checks as proof."
    return (
        "Run the pre-specified empirical design, estimate the adjusted association/effect, report uncertainty, "
        "and execute falsification, negative-control, placebo/leakage, and sensitivity checks before any claim upgrade."
    )


@dataclass
class HypothesisRepairResult:
    hypothesis_id: str = ""
    repaired_hypothesis: Dict[str, Any] = field(default_factory=dict)
    revision_patch: Dict[str, Any] = field(default_factory=dict)
    missing_items_addressed: List[str] = field(default_factory=list)
    missing_items_unhandled: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HypothesisRepairAgent:
    """Apply conservative, field-level repairs requested by CausalGate verdicts."""

    def repair(self, payload: Mapping[str, Any]) -> HypothesisRepairResult:
        data = _as_dict(payload)
        hypothesis = _as_dict(data.get("hypothesis")) or data
        verdict = _as_dict(data.get("verdict"))
        missing_items = _str_list(verdict.get("missing_items") or data.get("missing_items"))
        reason_codes = _str_list(verdict.get("reason_codes") or data.get("reason_codes"))

        repaired = normalize_scientific_hypothesis(hypothesis).to_dict()
        # Preserve extra fields that the canonical dataclass does not own yet.
        for key, value in hypothesis.items():
            repaired.setdefault(key, value)

        added: Dict[str, Any] = {}
        modified: Dict[str, Any] = {}
        addressed: List[str] = []

        confounders = _infer_confounders(repaired)
        if confounders and not repaired.get("confounders"):
            repaired["confounders"] = confounders
            repaired.setdefault("variables", {})["confounders"] = confounders
            added["confounders"] = confounders

        if "measurable_prediction" in missing_items and not _str_list(repaired.get("measurable_predictions")):
            repaired["measurable_predictions"] = [_prediction(repaired)]
            added["measurable_predictions"] = repaired["measurable_predictions"]
            addressed.append("measurable_prediction")

        if "adjustment_set" in missing_items and confounders and not _str_list(repaired.get("adjustment_set")):
            repaired["adjustment_set"] = confounders
            repaired.setdefault("variables", {})["controls"] = confounders
            repaired["controls"] = confounders
            added["adjustment_set"] = confounders
            addressed.append("adjustment_set")

        if "observed_confounder_measurements" in missing_items and confounders:
            existing = _as_dict(repaired.get("observed_confounder_measurements"))
            measurements = {**existing, **{z: existing.get(z) or _measurement_for(z) for z in confounders}}
            repaired["observed_confounder_measurements"] = measurements
            data_requirements = _str_list(repaired.get("data_requirements"))
            for z in confounders:
                req = f"{z}: {_measurement_for(z)}"
                if req not in data_requirements:
                    data_requirements.append(req)
            repaired["data_requirements"] = data_requirements
            added["observed_confounder_measurements"] = measurements
            modified["data_requirements"] = data_requirements
            addressed.append("observed_confounder_measurements")

        if ("identification_strategy" in missing_items or "EFFECT_NOT_IDENTIFIED_OR_ID_UNAVAILABLE" in reason_codes) and not _clean_str(repaired.get("identification_strategy")):
            repaired["identification_strategy"] = _infer_identification_strategy(repaired)
            added["identification_strategy"] = repaired["identification_strategy"]
            addressed.append("identification_strategy")

        if "test_plan_or_simulation_plan" in missing_items and not _clean_str(repaired.get("test_plan")):
            repaired["test_plan"] = _test_plan(repaired)
            added["test_plan"] = repaired["test_plan"]
            addressed.append("test_plan_or_simulation_plan")

        if "negative_control_outcome_or_exposure" in missing_items:
            repaired["negative_control_tests"] = _append_unique(repaired.get("negative_control_tests"), [
                "A pre-specified negative-control outcome or exposure should show a null result under the proposed mechanism."
            ])
            modified["negative_control_tests"] = repaired["negative_control_tests"]
            addressed.append("negative_control_outcome_or_exposure")

        if "placebo_or_temporal_leakage_test" in missing_items:
            repaired["placebo_tests"] = _append_unique(repaired.get("placebo_tests"), [
                "Future-treatment or temporal-leakage placebo: later exposure must not predict earlier outcome."
            ])
            modified["placebo_tests"] = repaired["placebo_tests"]
            addressed.append("placebo_or_temporal_leakage_test")

        # Never let repairs upgrade epistemic strength.
        repaired["claim_level"] = "hypothesis_only"
        repaired["conclusion_strength"] = "hypothesis_only"
        repaired["claim_level_key"] = "candidate_hypothesis"
        repaired["claim_level_index"] = 2
        repaired["claim_level_label"] = "candidate hypothesis"
        meta = _as_dict(repaired.get("metadata"))
        meta.update({
            "repaired_by": "causalgate.scientific.hypothesis_repair_agent",
            "repair_id": "repair_" + uuid4().hex[:12],
            "claim_rule": "Repair may add structure but must not increase claim strength.",
        })
        repaired["metadata"] = meta

        unhandled = [item for item in missing_items if item not in set(addressed)]
        warnings = ["Repair preserved claim_level=hypothesis_only; CausalGate must re-audit before acceptance."]
        if unhandled:
            warnings.append("Some missing items require LLM or human revision: " + ", ".join(unhandled))

        patch = {
            "added": sorted(added.keys()),
            "modified": sorted(modified.keys()),
            "claim_level_changed": False,
            "reason_codes": reason_codes,
            "reason": "Applied targeted deterministic repair from CausalGate verdict.",
            "details": {"added": added, "modified": modified},
        }
        return HypothesisRepairResult(
            hypothesis_id=_clean_str(repaired.get("hypothesis_id")),
            repaired_hypothesis=repaired,
            revision_patch=patch,
            missing_items_addressed=addressed,
            missing_items_unhandled=unhandled,
            warnings=warnings,
        )


def repair_hypothesis(payload: Mapping[str, Any]) -> Dict[str, Any]:
    return HypothesisRepairAgent().repair(payload).to_dict()


__all__ = [
    "REPAIRABLE_ITEMS",
    "HypothesisRepairAgent",
    "HypothesisRepairResult",
    "repair_hypothesis",
]
