from __future__ import annotations

"""Evidence requirement helpers for CausalGate scientific candidates."""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping

from .hypothesis_contract import ScientificHypothesisPackage, normalize_scientific_hypothesis


@dataclass
class EvidenceRequirementPlan:
    """Minimum evidence checklist inferred from a hypothesis contract."""

    required_observations: List[str] = field(default_factory=list)
    required_controls: List[str] = field(default_factory=list)
    required_temporal_information: List[str] = field(default_factory=list)
    required_validation_tests: List[str] = field(default_factory=list)
    external_validation_note: str = (
        "Passing CausalGate means the claim is a candidate for external validation, "
        "not a confirmed scientific law."
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def infer_evidence_requirements(payload: Mapping[str, Any] | ScientificHypothesisPackage) -> Dict[str, Any]:
    """Infer a conservative evidence checklist from a hypothesis."""

    hyp = payload if isinstance(payload, ScientificHypothesisPackage) else normalize_scientific_hypothesis(payload)

    observations: List[str] = []
    controls: List[str] = []
    temporal: List[str] = []
    validation: List[str] = []

    for var in list(hyp.treatments or ([hyp.treatment] if hyp.treatment else [])):
        observations.append(f"measure treatment/cause variable: {var}")
    for var in list(hyp.outcomes or ([hyp.outcome] if hyp.outcome else [])):
        observations.append(f"measure outcome/effect variable: {var}")
    for var in hyp.mediators:
        observations.append(f"measure mediator variable: {var}")
    for var in hyp.confounders:
        controls.append(f"measure and adjust for confounder: {var}")
    for var in hyp.adjustment_set:
        controls.append(f"include adjustment variable: {var}")

    temporal.append("verify treatment/cause precedes outcome/effect")
    temporal.append("define measurement window and lag structure")

    validation.extend([
        "negative control outcome or exposure",
        "placebo/future-treatment leakage test",
        "sensitivity or robustness check for hidden confounding",
    ])

    if hyp.measurable_predictions:
        validation.append("compare observed results against measurable predictions")

    return EvidenceRequirementPlan(
        required_observations=sorted(set(observations)),
        required_controls=sorted(set(controls)),
        required_temporal_information=sorted(set(temporal)),
        required_validation_tests=sorted(set(validation)),
    ).to_dict()


__all__ = ["EvidenceRequirementPlan", "infer_evidence_requirements"]
