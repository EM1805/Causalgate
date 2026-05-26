from __future__ import annotations

"""Hypothesis expansion engine for CausalGate.

The expansion engine turns a veto/revision result into a structured next draft.
It does not invent evidence and it never upgrades a claim by force.  Its job is
to preserve the hypothesis lineage, add missing scientific structure, and route
it toward the next check until it can become ACCEPTED_CANDIDATE or must be
archived as unsupported.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .hypothesis_contract import normalize_scientific_hypothesis
from .hypothesis_veto import evaluate_hypothesis
from .revision_protocol import build_revision_protocol


EXPANSION_STATES = {
    "DRAFT",
    "NEEDS_STRUCTURE",
    "NEEDS_CONFOUNDERS",
    "NEEDS_IDENTIFICATION",
    "NEEDS_FALSIFICATION",
    "NEEDS_ESTIMATION",
    "NEEDS_COUNTERFACTUAL",
    "ACCEPTED_CANDIDATE",
    "ARCHIVED_UNSUPPORTED",
}


@dataclass
class HypothesisExpansionResult:
    hypothesis_id: str
    previous_version: int
    new_version: int
    state: str
    previous_decision: str
    accepted: bool = False
    should_continue: bool = True
    next_required_step: str = "revise_hypothesis"
    hypothesis: Dict[str, Any] = field(default_factory=dict)
    expanded_hypothesis: Dict[str, Any] = field(default_factory=dict)
    missing_items_fixed: List[str] = field(default_factory=list)
    missing_items_remaining: List[str] = field(default_factory=list)
    added_items: Dict[str, Any] = field(default_factory=dict)
    expansion_questions: List[str] = field(default_factory=list)
    revision_protocol: Dict[str, Any] = field(default_factory=dict)
    lineage: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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


def _version_from_metadata(hypothesis: Mapping[str, Any]) -> int:
    meta = _as_dict(hypothesis.get("metadata"))
    for raw in (meta.get("version"), hypothesis.get("version"), hypothesis.get("step")):
        try:
            return max(0, int(raw))
        except Exception:
            continue
    return 0


def _append_unique(values: List[str], additions: Iterable[str]) -> List[str]:
    out = list(values)
    seen = set(out)
    for item in additions:
        text = _clean_str(item)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _state_from_verdict(verdict: Mapping[str, Any], missing: List[str]) -> str:
    decision = _clean_str(verdict.get("decision"), "ABSTAIN")
    reason_codes = set(_str_list(verdict.get("reason_codes")))
    if decision == "FINAL_CANDIDATE":
        return "ACCEPTED_CANDIDATE"
    if decision == "BLOCK" and not missing:
        return "ARCHIVED_UNSUPPORTED"
    if {"claim", "treatment_or_cause", "outcome_or_effect", "dag_with_nodes_and_edges", "assumptions", "data_requirements"}.intersection(missing):
        return "NEEDS_STRUCTURE"
    if {"adjustment_set", "observed_confounder_measurements"}.intersection(missing) or "MISSING_CAUSE_OR_EFFECT_VARIABLE" in reason_codes:
        return "NEEDS_CONFOUNDERS"
    if "EFFECT_NOT_IDENTIFIED_OR_ID_UNAVAILABLE" in reason_codes:
        return "NEEDS_IDENTIFICATION"
    if any("falsification" in item or "negative_control" in item or "placebo" in item for item in missing) or "MISSING_FALSIFICATION_TESTS" in reason_codes:
        return "NEEDS_FALSIFICATION"
    if any("estimation" in item or "effect_size" in item for item in missing):
        return "NEEDS_ESTIMATION"
    if any("counterfactual" in item or "matched_control" in item for item in missing):
        return "NEEDS_COUNTERFACTUAL"
    return "DRAFT"


def _next_step_for_state(state: str) -> str:
    return {
        "DRAFT": "revise_hypothesis",
        "NEEDS_STRUCTURE": "add_scientific_structure",
        "NEEDS_CONFOUNDERS": "add_confounders_and_adjustment_set",
        "NEEDS_IDENTIFICATION": "run_scm_id_or_revise_dag",
        "NEEDS_FALSIFICATION": "add_falsification_tests",
        "NEEDS_ESTIMATION": "plan_effect_estimation",
        "NEEDS_COUNTERFACTUAL": "plan_counterfactual_validation",
        "ACCEPTED_CANDIDATE": "external_validation_or_experiment",
        "ARCHIVED_UNSUPPORTED": "archive_or_restart",
    }.get(state, "revise_hypothesis")


def _question_bank(missing: List[str], state: str) -> List[str]:
    questions: List[str] = []
    if "claim" in missing:
        questions.append("State the hypothesis as a precise, non-overclaiming sentence.")
    if "treatment_or_cause" in missing:
        questions.append("What is the putative cause/intervention variable X?")
    if "outcome_or_effect" in missing:
        questions.append("What is the outcome/effect variable Y and how is it measured?")
    if "dag_with_nodes_and_edges" in missing:
        questions.append("Provide a DAG with X, Y, mediators, observed confounders, and causal arrows.")
    if "assumptions" in missing:
        questions.append("List the assumptions that must hold for this causal interpretation.")
    if "data_requirements" in missing:
        questions.append("What observations, time order, sample size, and measurement windows are required?")
    if state == "NEEDS_CONFOUNDERS":
        questions.append("Which observed confounders could affect both X and Y, and which belong in the adjustment set?")
    if state == "NEEDS_IDENTIFICATION":
        questions.append("Can the effect be identified by adjustment, frontdoor, experiment, or a revised DAG?")
    if state == "NEEDS_FALSIFICATION":
        questions.append("Add negative controls, placebo/future-treatment tests, and at least two independent falsification checks.")
    if state == "NEEDS_ESTIMATION":
        questions.append("Define the estimand, effect metric, uncertainty interval, and minimum evidence threshold.")
    if state == "NEEDS_COUNTERFACTUAL":
        questions.append("Define matched controls or counterfactual comparisons that could disconfirm the claim.")
    if not questions:
        questions.append("Improve the hypothesis without increasing claim strength; keep it as a testable candidate.")
    return questions


def _build_template(hypothesis: Mapping[str, Any], state: str, missing: List[str]) -> Dict[str, Any]:
    out = dict(hypothesis or {})
    variables = _as_dict(out.get("variables"))
    treatment = _clean_str(out.get("treatment") or variables.get("treatment"))
    outcome = _clean_str(out.get("outcome") or variables.get("outcome"))

    out.setdefault("claim_level", "hypothesis_only")
    out.setdefault("conclusion_strength", "hypothesis_only")
    if not _clean_str(out.get("claim")):
        out["claim"] = "[DRAFT] X may causally affect Y under stated assumptions; replace X/Y with measured variables."
    if treatment:
        out["treatment"] = treatment
        variables.setdefault("treatment", treatment)
    if outcome:
        out["outcome"] = outcome
        variables.setdefault("outcome", outcome)
    out["variables"] = variables

    dag = _as_dict(out.get("dag"))
    if treatment and outcome and not dag.get("edges"):
        nodes = dag.get("nodes") or [treatment, outcome]
        dag = {**dag, "nodes": nodes, "edges": [{"source": treatment, "target": outcome, "edge_kind": "directed"}]}
        out["dag"] = dag

    if "assumptions" in missing and not _as_list(out.get("assumptions")):
        out["assumptions"] = [
            "No uncontrolled confounder fully explains the proposed X→Y relation.",
            "X is measured before Y or temporally prior to the outcome window.",
        ]
    if "data_requirements" in missing and not _as_list(out.get("data_requirements")):
        out["data_requirements"] = [
            "Time-ordered measurements of X and Y.",
            "Measurements of candidate confounders before or at treatment time.",
        ]
    if state == "NEEDS_FALSIFICATION" or "falsification_tests" in missing:
        out["falsification_tests"] = _append_unique(_str_list(out.get("falsification_tests")), [
            "Negative-control outcome/exposure should not move if the proposed mechanism is real.",
            "Temporal placebo: future X must not predict past/current Y.",
        ])
        out["negative_control_tests"] = _append_unique(_str_list(out.get("negative_control_tests")), [
            "Choose a negative-control variable and specify the expected null result.",
        ])
        out["placebo_tests"] = _append_unique(_str_list(out.get("placebo_tests")), [
            "Future-treatment leakage placebo test.",
        ])
    if state == "NEEDS_IDENTIFICATION":
        out.setdefault("identification_strategy", "Specify adjustment/frontdoor/experiment/revised-DAG strategy before promotion.")
        if _str_list(out.get("confounders")) and not _str_list(out.get("adjustment_set")):
            out["adjustment_set"] = _str_list(out.get("confounders"))

    meta = _as_dict(out.get("metadata"))
    meta["expanded_by"] = "causalgate.scientific.hypothesis_expansion"
    meta["expansion_state"] = state
    meta["claim_rule"] = "Expansion may improve structure, but must not claim proof or confirmed law."
    out["metadata"] = meta
    return out


class HypothesisExpansionEngine:
    """Preserve and mature rejected scientific hypotheses instead of dropping them."""

    def __init__(self, *, enable_identification: bool = True) -> None:
        self.enable_identification = enable_identification

    def expand(self, payload: Mapping[str, Any]) -> HypothesisExpansionResult:
        data = _as_dict(payload)
        raw_hypothesis = _as_dict(data.get("hypothesis")) or data
        hypothesis = normalize_scientific_hypothesis(raw_hypothesis).to_dict()
        verdict = _as_dict(data.get("verdict"))
        if not verdict:
            verdict = evaluate_hypothesis(hypothesis, enable_identification=bool(data.get("enable_identification", self.enable_identification)))

        missing = _str_list(verdict.get("missing_items"))
        decision = _clean_str(verdict.get("decision"), "ABSTAIN")
        state = _state_from_verdict(verdict, missing)
        previous_version = _version_from_metadata(hypothesis)
        new_version = previous_version + (0 if state in {"ACCEPTED_CANDIDATE", "ARCHIVED_UNSUPPORTED"} else 1)
        accepted = state == "ACCEPTED_CANDIDATE"
        should_continue = state not in {"ACCEPTED_CANDIDATE", "ARCHIVED_UNSUPPORTED"}

        expanded = dict(hypothesis) if accepted else _build_template(hypothesis, state, missing)
        expanded_meta = _as_dict(expanded.get("metadata"))
        expanded_meta.update({
            "version": new_version,
            "previous_version": previous_version,
            "previous_decision": decision,
            "lineage_parent_hypothesis_id": hypothesis.get("hypothesis_id", ""),
        })
        expanded["metadata"] = expanded_meta

        added_items = {}
        for key in ("claim", "dag", "assumptions", "data_requirements", "falsification_tests", "negative_control_tests", "placebo_tests", "identification_strategy", "adjustment_set"):
            if expanded.get(key) and expanded.get(key) != hypothesis.get(key):
                added_items[key] = expanded.get(key)

        fixed = [item for item in missing if item in {"claim", "assumptions", "data_requirements", "falsification_tests"} and expanded.get(item)]
        remaining = [item for item in missing if item not in fixed]
        revision_protocol = build_revision_protocol({
            "missing_items": missing,
            "required_tests": verdict.get("required_tests", []),
            "required_evidence": verdict.get("required_evidence", []),
        })

        warnings: List[str] = []
        if accepted:
            warnings.append("Accepted only as candidate-level science; external validation is still required.")
        elif state == "ARCHIVED_UNSUPPORTED":
            warnings.append("The current version is blocked without a safe expansion path; archive or restart with a new claim.")
        else:
            warnings.append("Expanded draft is not accepted yet; resubmit it through CausalGate veto/audit.")

        return HypothesisExpansionResult(
            hypothesis_id=_clean_str(hypothesis.get("hypothesis_id")),
            previous_version=previous_version,
            new_version=new_version,
            state=state,
            previous_decision=decision,
            accepted=accepted,
            should_continue=should_continue,
            next_required_step=_next_step_for_state(state),
            hypothesis=hypothesis,
            expanded_hypothesis=expanded,
            missing_items_fixed=fixed,
            missing_items_remaining=remaining,
            added_items=added_items,
            expansion_questions=_question_bank(missing, state),
            revision_protocol=revision_protocol,
            lineage={
                "parent_hypothesis_id": hypothesis.get("hypothesis_id", ""),
                "previous_version": previous_version,
                "new_version": new_version,
                "previous_decision": decision,
                "state": state,
            },
            warnings=warnings,
        )


def expand_hypothesis(payload: Mapping[str, Any], *, enable_identification: bool = True) -> Dict[str, Any]:
    return HypothesisExpansionEngine(enable_identification=enable_identification).expand(payload).to_dict()


__all__ = [
    "EXPANSION_STATES",
    "HypothesisExpansionEngine",
    "HypothesisExpansionResult",
    "expand_hypothesis",
]
