from __future__ import annotations

"""Falsification and evidence policy for CausalGate scientific candidates.

Step 5 makes the scientific layer stricter.  A hypothesis cannot become
``FINAL_CANDIDATE`` just because it has a DAG and a causal-looking sentence.
It must also provide a falsifiable prediction, negative/placebo controls,
required evidence, and an adjustment strategy when confounding is present.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Set

from .hypothesis_contract import ScientificHypothesisPackage, normalize_scientific_hypothesis


_NEGATIVE_CONTROL_TERMS = (
    "negative control",
    "negative_control",
    "null outcome",
    "control outcome",
    "unaffected outcome",
    "irrelevant outcome",
)

_PLACEBO_TERMS = (
    "placebo",
    "future-x",
    "future x",
    "future treatment",
    "temporal leakage",
    "leakage",
    "sham",
    "permutation",
    "randomized label",
)

_SENSITIVITY_TERMS = (
    "sensitivity",
    "hidden confounding",
    "unobserved confounding",
    "robustness",
    "e-value",
    "bounds",
    "placebo",
    "negative control",
)

_MEASUREMENT_TERMS = (
    "increase",
    "decrease",
    "higher",
    "lower",
    "rise",
    "fall",
    "positive",
    "negative",
    "direction",
    "within",
    "after",
    "before",
    "window",
    "lag",
    "measured",
    "observed",
    "%",
    "unit",
    "units",
)


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
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, Mapping)):
        return list(value)
    return [value]


def _as_str_list(value: Any) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for item in _as_list(value):
        text = _clean_str(item)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _contains_any(texts: List[str], terms: Iterable[str]) -> bool:
    low = "\n".join(texts).lower()
    return any(term in low for term in terms)


def _prediction_is_measurable(prediction: str) -> bool:
    low = prediction.lower()
    # A prediction must be more than "X affects Y": it needs direction,
    # measurable observation, timing, or a concrete comparative statement.
    return any(term in low for term in _MEASUREMENT_TERMS)


def _edge_pairs(hypothesis: ScientificHypothesisPackage) -> List[tuple[str, str]]:
    edges = []
    for edge in _as_list(hypothesis.dag.get("edges")):
        if isinstance(edge, Mapping):
            source = _clean_str(edge.get("source") or edge.get("from") or edge.get("src"))
            target = _clean_str(edge.get("target") or edge.get("to") or edge.get("dst"))
            if source and target:
                edges.append((source, target))
        else:
            parts = _as_list(edge)
            if len(parts) >= 2:
                source = _clean_str(parts[0])
                target = _clean_str(parts[1])
                if source and target:
                    edges.append((source, target))
    return edges


def _has_dag_confounder_pattern(hypothesis: ScientificHypothesisPackage) -> bool:
    treatment_nodes = set(hypothesis.treatments or ([hypothesis.treatment] if hypothesis.treatment else []))
    outcome_nodes = set(hypothesis.outcomes or ([hypothesis.outcome] if hypothesis.outcome else []))
    if not treatment_nodes or not outcome_nodes:
        return False

    edges = _edge_pairs(hypothesis)
    into_treatment = {src for src, dst in edges if dst in treatment_nodes}
    into_outcome = {src for src, dst in edges if dst in outcome_nodes}
    shared = (into_treatment & into_outcome) - treatment_nodes - outcome_nodes
    return bool(shared)


@dataclass
class FalsificationAssessment:
    """Structured output from the Step 5 falsification/evidence gate."""

    decision_hint: str = "FINAL_CANDIDATE"
    falsifiability_status: str = "unknown"
    evidence_status: str = "unknown"
    reason_codes: List[str] = field(default_factory=list)
    missing_items: List[str] = field(default_factory=list)
    required_tests: List[str] = field(default_factory=list)
    required_evidence: List[str] = field(default_factory=list)
    next_instruction: str = ""
    audit_payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FalsificationPolicy:
    """Conservative policy for hypothesis falsifiability and evidence readiness."""

    def assess(self, payload: Mapping[str, Any] | ScientificHypothesisPackage) -> FalsificationAssessment:
        hyp = payload if isinstance(payload, ScientificHypothesisPackage) else normalize_scientific_hypothesis(payload)

        reason_codes: List[str] = []
        missing_items: List[str] = []
        required_tests: List[str] = []
        required_evidence: List[str] = []

        falsification_texts = _as_str_list(hyp.falsification_tests)
        prediction_texts = _as_str_list(hyp.measurable_predictions)
        negative_controls = _as_str_list(getattr(hyp, "negative_control_variables", None) or hyp.negative_controls)
        negative_control_tests = _as_str_list(getattr(hyp, "negative_control_tests", None))
        placebo_tests = _as_str_list(hyp.placebo_tests)
        sensitivity_checks = _as_str_list(hyp.sensitivity_checks)

        combined_test_texts = (
            falsification_texts
            + prediction_texts
            + negative_control_tests
            + placebo_tests
            + sensitivity_checks
            + _as_str_list(hyp.test_plan)
            + _as_str_list(hyp.simulation_plan)
        )

        if not prediction_texts:
            reason_codes.append("MISSING_MEASURABLE_PREDICTION")
            missing_items.append("measurable_prediction")
            required_tests.append("add_directional_measurable_prediction")
        elif not any(_prediction_is_measurable(p) for p in prediction_texts):
            reason_codes.append("PREDICTION_NOT_MEASURABLE")
            missing_items.append("prediction_direction_or_time_window")
            required_tests.append("specify_direction_magnitude_or_time_window")

        has_negative_control = bool(negative_controls) or bool(negative_control_tests) or _contains_any(combined_test_texts, _NEGATIVE_CONTROL_TERMS)
        if not has_negative_control:
            reason_codes.append("MISSING_NEGATIVE_CONTROL")
            missing_items.append("negative_control_outcome_or_exposure")
            required_tests.append("negative_control_outcome")

        has_placebo = bool(placebo_tests) or _contains_any(combined_test_texts, _PLACEBO_TERMS)
        if not has_placebo:
            reason_codes.append("MISSING_PLACEBO_OR_LEAKAGE_TEST")
            missing_items.append("placebo_or_temporal_leakage_test")
            required_tests.append("future_x_placebo_or_temporal_leakage_test")

        has_sensitivity = bool(sensitivity_checks) or _contains_any(combined_test_texts, _SENSITIVITY_TERMS)
        if not has_sensitivity:
            # Sensitivity is not always a hard block for a first candidate, but it
            # is required before claiming robust support.
            reason_codes.append("MISSING_SENSITIVITY_CHECK")
            required_tests.append("hidden_confounding_or_robustness_sensitivity_check")

        has_confounding = bool(hyp.confounders) or _has_dag_confounder_pattern(hyp)
        if has_confounding and not hyp.adjustment_set:
            reason_codes.append("MISSING_ADJUSTMENT_SET_FOR_CONFOUNDING")
            missing_items.append("adjustment_set")
            required_tests.append("state_adjustment_set_for_observed_confounders")

        if not hyp.data_requirements:
            reason_codes.append("MISSING_EVIDENCE_REQUIREMENTS")
            missing_items.append("data_requirements")
            required_evidence.append("state_required_observations_and_measurement_window")
        else:
            required_evidence.extend(hyp.data_requirements)

        if has_confounding and hyp.confounders:
            measurement_map = _as_dict(getattr(hyp, "observed_confounder_measurements", None))
            observed_text = " ".join(hyp.data_requirements + hyp.assumptions).lower()
            missing_observed = [
                z for z in hyp.confounders
                if z
                and z not in measurement_map
                and z.lower() not in observed_text
                and "confounder" not in observed_text
            ]
            if missing_observed:
                reason_codes.append("CONFOUNDER_OBSERVATION_NOT_SPECIFIED")
                missing_items.append("observed_confounder_measurements")
                required_evidence.append("specify that all adjustment/confounder variables are measured")

        if not (hyp.test_plan or hyp.simulation_plan or falsification_texts):
            reason_codes.append("MISSING_TEST_PLAN")
            missing_items.append("test_plan_or_simulation_plan")
            required_tests.append("write_empirical_or_simulation_test_plan")

        hard_revision = {
            "MISSING_MEASURABLE_PREDICTION",
            "PREDICTION_NOT_MEASURABLE",
            "MISSING_ADJUSTMENT_SET_FOR_CONFOUNDING",
            "MISSING_EVIDENCE_REQUIREMENTS",
            "CONFOUNDER_OBSERVATION_NOT_SPECIFIED",
        }
        more_tests = {
            "MISSING_NEGATIVE_CONTROL",
            "MISSING_PLACEBO_OR_LEAKAGE_TEST",
            "MISSING_SENSITIVITY_CHECK",
            "MISSING_TEST_PLAN",
        }

        if hard_revision.intersection(reason_codes):
            decision_hint = "REVISE"
        elif more_tests.intersection(reason_codes):
            decision_hint = "TEST_MORE"
        else:
            decision_hint = "FINAL_CANDIDATE"

        if "MISSING_MEASURABLE_PREDICTION" in reason_codes:
            falsifiability_status = "missing"
        elif {"MISSING_NEGATIVE_CONTROL", "MISSING_PLACEBO_OR_LEAKAGE_TEST"}.intersection(reason_codes):
            falsifiability_status = "weak"
        elif "PREDICTION_NOT_MEASURABLE" in reason_codes:
            falsifiability_status = "weak"
        else:
            falsifiability_status = "testable"

        if "MISSING_EVIDENCE_REQUIREMENTS" in reason_codes:
            evidence_status = "insufficient"
        elif {"CONFOUNDER_OBSERVATION_NOT_SPECIFIED", "MISSING_ADJUSTMENT_SET_FOR_CONFOUNDING"}.intersection(reason_codes):
            evidence_status = "incomplete_confounding_controls"
        elif "MISSING_SENSITIVITY_CHECK" in reason_codes:
            evidence_status = "minimum_requirements_specified"
        else:
            evidence_status = "ready_for_external_validation"

        next_instruction = self._build_instruction(
            missing_items=missing_items,
            required_tests=required_tests,
            required_evidence=required_evidence,
            decision_hint=decision_hint,
        )

        return FalsificationAssessment(
            decision_hint=decision_hint,
            falsifiability_status=falsifiability_status,
            evidence_status=evidence_status,
            reason_codes=reason_codes,
            missing_items=sorted(set(missing_items)),
            required_tests=sorted(set(required_tests)),
            required_evidence=sorted(set(required_evidence)),
            next_instruction=next_instruction,
            audit_payload={
                "hypothesis_id": hyp.hypothesis_id,
                "has_negative_control": has_negative_control,
                "has_placebo_or_leakage_test": has_placebo,
                "has_sensitivity_check": has_sensitivity,
                "has_confounding": has_confounding,
                "adjustment_set": list(hyp.adjustment_set),
                "observed_confounder_measurements": dict(getattr(hyp, "observed_confounder_measurements", {}) or {}),
                "negative_control_variables": list(negative_controls),
                "negative_control_tests": list(negative_control_tests),
            },
        )

    def _build_instruction(
        self,
        *,
        missing_items: List[str],
        required_tests: List[str],
        required_evidence: List[str],
        decision_hint: str,
    ) -> str:
        if decision_hint == "FINAL_CANDIDATE":
            return (
                "Keep the claim as a testable candidate. Do not call it confirmed; "
                "run the specified empirical or simulation tests before stronger claims."
            )

        parts: List[str] = []
        if missing_items:
            parts.append("Add or fix: " + ", ".join(sorted(set(missing_items))) + ".")
        if required_tests:
            parts.append("Required tests: " + ", ".join(sorted(set(required_tests))) + ".")
        if required_evidence:
            parts.append("Required evidence: " + ", ".join(sorted(set(required_evidence))) + ".")
        if not parts:
            parts.append("Revise the hypothesis into a falsifiable, measurable, evidence-bound candidate.")
        return " ".join(parts)


def assess_falsification(payload: Mapping[str, Any], *, as_dict: bool = True) -> Dict[str, Any] | FalsificationAssessment:
    """Functional helper for MCP/API integrations."""

    assessment = FalsificationPolicy().assess(payload)
    return assessment.to_dict() if as_dict else assessment


__all__ = [
    "FalsificationAssessment",
    "FalsificationPolicy",
    "assess_falsification",
]
