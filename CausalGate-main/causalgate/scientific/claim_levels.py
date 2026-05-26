from __future__ import annotations

"""Scientific claim-level authority for CausalGate.

This module is intentionally stdlib-only.  It gives the scientific agent a
stable, machine-checkable ladder for saying *how strong* a scientific claim is
allowed to be.  The ladder is conservative: a strong causal or law-like claim
requires evidence and validation flags that a normal LLM response will not have.
"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Mapping, Optional


@dataclass(frozen=True)
class ScientificClaimLevel:
    """One rung in the scientific claim-authority ladder."""

    index: int
    key: str
    label: str
    allowed_assertion: str
    minimum_requirements: tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


CLAIM_LEVELS: tuple[ScientificClaimLevel, ...] = (
    ScientificClaimLevel(
        0,
        "blocked",
        "blocked",
        "No scientific claim is allowed; the output must be revised or rejected.",
        ("valid_non_empty_claim",),
    ),
    ScientificClaimLevel(
        1,
        "speculative_idea",
        "speculative idea",
        "May be discussed only as an intuition or research idea.",
        ("claim",),
    ),
    ScientificClaimLevel(
        2,
        "candidate_hypothesis",
        "candidate hypothesis",
        "May be framed as a candidate hypothesis, not as evidence-backed causality.",
        ("claim", "treatment", "outcome"),
    ),
    ScientificClaimLevel(
        3,
        "testable_hypothesis",
        "testable hypothesis",
        "May be tested with a specified DAG, assumptions, data needs, and falsification plan.",
        ("claim", "treatment", "outcome", "dag", "assumptions", "falsification_tests", "data_requirements"),
    ),
    ScientificClaimLevel(
        4,
        "statistically_supported",
        "statistically supported",
        "May report statistical support, while avoiding causal language unless ID also passes.",
        ("level_3", "effect_estimate", "uncertainty", "robustness_or_replication_split"),
    ),
    ScientificClaimLevel(
        5,
        "causally_identified",
        "causally identified",
        "May make a bounded causal-identification claim under explicit assumptions.",
        ("level_3", "scm_id_passed", "valid_estimand", "assumptions_declared"),
    ),
    ScientificClaimLevel(
        6,
        "experimentally_validated",
        "experimentally validated",
        "May claim experimental validation inside the tested domain and design limits.",
        ("level_5", "intervention_or_rct", "pre_registered_or_auditable_protocol"),
    ),
    ScientificClaimLevel(
        7,
        "independently_replicated",
        "independently replicated",
        "May claim robust external support after independent replication.",
        ("level_6", "independent_replication", "external_validity_notes"),
    ),
)

_LEVEL_BY_INDEX = {level.index: level for level in CLAIM_LEVELS}
_LEVEL_BY_KEY = {level.key: level for level in CLAIM_LEVELS}

_ALIAS_TO_KEY = {
    "0": "blocked",
    "level_0": "blocked",
    "level 0": "blocked",
    "block": "blocked",
    "blocked": "blocked",
    "abstain": "blocked",
    "observation_only": "speculative_idea",
    "observational": "speculative_idea",
    "idea": "speculative_idea",
    "speculative": "speculative_idea",
    "speculative_idea": "speculative_idea",
    "level_1": "speculative_idea",
    "level 1": "speculative_idea",
    "hypothesis_only": "candidate_hypothesis",
    "candidate": "candidate_hypothesis",
    "candidate_hypothesis": "candidate_hypothesis",
    "level_2": "candidate_hypothesis",
    "level 2": "candidate_hypothesis",
    "testable_candidate": "testable_hypothesis",
    "testable": "testable_hypothesis",
    "testable_hypothesis": "testable_hypothesis",
    "level_3": "testable_hypothesis",
    "level 3": "testable_hypothesis",
    "supported_candidate": "statistically_supported",
    "statistical_support": "statistically_supported",
    "statistically_supported": "statistically_supported",
    "level_4": "statistically_supported",
    "level 4": "statistically_supported",
    "identified_candidate": "causally_identified",
    "identified": "causally_identified",
    "causally_identified": "causally_identified",
    "level_5": "causally_identified",
    "level 5": "causally_identified",
    "validated_external": "independently_replicated",
    "experimental": "experimentally_validated",
    "experimentally_validated": "experimentally_validated",
    "level_6": "experimentally_validated",
    "level 6": "experimentally_validated",
    "replicated": "independently_replicated",
    "independently_replicated": "independently_replicated",
    "level_7": "independently_replicated",
    "level 7": "independently_replicated",
}


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip().lower().replace("-", "_")
    return text or default


def normalize_claim_level(value: Any, default: str = "candidate_hypothesis") -> ScientificClaimLevel:
    """Normalize legacy strings, numeric levels, and new canonical keys."""

    if isinstance(value, ScientificClaimLevel):
        return value
    if isinstance(value, int):
        return _LEVEL_BY_INDEX.get(max(0, min(7, value)), _LEVEL_BY_KEY[default])
    text = _clean(value)
    if text.startswith("level ") and text[-1:].isdigit():
        return _LEVEL_BY_INDEX.get(int(text[-1]), _LEVEL_BY_KEY[default])
    if text.startswith("level_") and text[-1:].isdigit():
        return _LEVEL_BY_INDEX.get(int(text[-1]), _LEVEL_BY_KEY[default])
    if text.isdigit():
        return _LEVEL_BY_INDEX.get(max(0, min(7, int(text))), _LEVEL_BY_KEY[default])
    key = _ALIAS_TO_KEY.get(text, text)
    return _LEVEL_BY_KEY.get(key, _LEVEL_BY_KEY[default])


def claim_level_payload(level: Any) -> Dict[str, Any]:
    return normalize_claim_level(level).to_dict()


def max_allowed_level_from_evidence(
    *,
    decision: str,
    missing_items: Iterable[str] = (),
    identification: Optional[Mapping[str, Any]] = None,
    falsification: Optional[Mapping[str, Any]] = None,
    has_effect_estimate: bool = False,
    has_experimental_validation: bool = False,
    has_independent_replication: bool = False,
) -> ScientificClaimLevel:
    """Compute the strongest claim level CausalGate should allow.

    The result is a ceiling, not a reward.  Downstream components may always
    downgrade further.  Step 1 intentionally treats a clean hypothesis package
    as at most Level 3 unless stronger evidence is explicitly available.
    """

    decision = _clean(decision, "abstain").upper()
    missing = {str(x) for x in (missing_items or []) if str(x)}
    identification = dict(identification or {})
    falsification = dict(falsification or {})

    if decision in {"BLOCK", "ABSTAIN"} or "claim" in missing:
        return _LEVEL_BY_INDEX[0]
    if decision in {"REVISE", "TEST_MORE"} or missing:
        if {"treatment_or_cause", "outcome_or_effect"}.intersection(missing):
            return _LEVEL_BY_INDEX[1]
        return _LEVEL_BY_INDEX[2]

    # FINAL_CANDIDATE with complete structure and falsifiability earns Level 3.
    max_index = 3

    identified = bool(identification.get("identified"))
    if identified:
        max_index = max(max_index, 5)
    if has_effect_estimate and max_index >= 3:
        max_index = max(max_index, 4)
    if has_experimental_validation and max_index >= 5:
        max_index = max(max_index, 6)
    if has_independent_replication and max_index >= 6:
        max_index = max(max_index, 7)

    return _LEVEL_BY_INDEX[max_index]


def clamp_requested_claim_level(requested: Any, max_allowed: Any) -> ScientificClaimLevel:
    requested_level = normalize_claim_level(requested)
    ceiling = normalize_claim_level(max_allowed)
    return _LEVEL_BY_INDEX[min(requested_level.index, ceiling.index)]


def claim_level_audit(
    requested: Any,
    *,
    decision: str,
    missing_items: Iterable[str] = (),
    identification: Optional[Mapping[str, Any]] = None,
    falsification: Optional[Mapping[str, Any]] = None,
    has_effect_estimate: bool = False,
    has_experimental_validation: bool = False,
    has_independent_replication: bool = False,
) -> Dict[str, Any]:
    """Return a compact audit object for LLM/agent-facing scientific claims."""

    requested_level = normalize_claim_level(requested)
    max_allowed = max_allowed_level_from_evidence(
        decision=decision,
        missing_items=missing_items,
        identification=identification,
        falsification=falsification,
        has_effect_estimate=has_effect_estimate,
        has_experimental_validation=has_experimental_validation,
        has_independent_replication=has_independent_replication,
    )
    final_level = clamp_requested_claim_level(requested_level, max_allowed)
    downgraded = final_level.index < requested_level.index
    return {
        "requested": requested_level.to_dict(),
        "max_allowed": max_allowed.to_dict(),
        "final": final_level.to_dict(),
        "downgraded": downgraded,
        "reason": (
            "requested_claim_exceeds_current_evidence_ceiling"
            if downgraded
            else "requested_claim_within_current_evidence_ceiling"
        ),
    }


__all__ = [
    "ScientificClaimLevel",
    "CLAIM_LEVELS",
    "normalize_claim_level",
    "claim_level_payload",
    "max_allowed_level_from_evidence",
    "clamp_requested_claim_level",
    "claim_level_audit",
]
