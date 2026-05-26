from __future__ import annotations

"""Revision protocol helpers for LLM-facing scientific feedback."""

from typing import Any, Dict, Iterable, List, Mapping


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def build_revision_protocol(assessment: Mapping[str, Any]) -> Dict[str, Any]:
    """Convert a falsification assessment into concise LLM instructions."""

    missing = [str(x) for x in _as_list(assessment.get("missing_items")) if str(x)]
    tests = [str(x) for x in _as_list(assessment.get("required_tests")) if str(x)]
    evidence = [str(x) for x in _as_list(assessment.get("required_evidence")) if str(x)]

    checklist: List[str] = []
    if "measurable_prediction" in missing:
        checklist.append("Add a falsifiable prediction with direction, measurement window, and observable outcome.")
    if "adjustment_set" in missing:
        checklist.append("State the adjustment set for observed confounders.")
    if "negative_control_outcome_or_exposure" in missing or any("negative_control" in t for t in tests):
        checklist.append("Add a negative control outcome or exposure.")
    if "placebo_or_temporal_leakage_test" in missing or any("placebo" in t or "leakage" in t for t in tests):
        checklist.append("Add a placebo/future-treatment temporal leakage test.")
    if any("sensitivity" in t or "confounding" in t for t in tests):
        checklist.append("Add a hidden-confounding sensitivity or robustness check.")
    if evidence:
        checklist.append("State required observations/data and their temporal order.")

    if not checklist:
        checklist.append("Keep the claim as a testable candidate and do not upgrade it to a confirmed law.")

    return {
        "revision_checklist": checklist,
        "llm_output_rule": "Return a revised ScientificHypothesisPackage, not a confident conclusion.",
        "claim_strength_rule": "Use hypothesis_only or testable_candidate; never claim law/confirmed/proven without external validation.",
    }


__all__ = ["build_revision_protocol"]
