from __future__ import annotations

"""Strict Step-80 audited finite recursive-ID7 closure cases.

This module does **not** implement arbitrary Shpitser-Pearl ID.  It only
recognizes the finite four-node recursive ID-7 shapes that were already
identified by the recursive expression runtime during deterministic fuzzing but
were still counted as raw delegated formula authority after Step 79.

The public facade may label those exact shapes as Step-80 audited recursive
formula authority while keeping ``full_recursive_id_implemented=0`` and
``full_id_claim_allowed=0``.
"""

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple

from .admg import ADMG
from .id_algorithm_common import _dedupe

ID_STEP80_AUDITED_FUZZ_VERSION = "id_step80_audited_fuzz_closure_v1"
ID_STEP80_AUDITED_FUZZ_AUTHORITY = "recursive_id_set_expression_diagnostic_step80_audited_fuzz_closure"
ID_STEP80_AUDITED_FUZZ_LEVEL = (
    "strict_finite_four_node_recursive_ID7_fuzz_closure_authority_for_previously_identified_delegate_formulas_no_arbitrary_Full_ID_claim"
)


@dataclass(frozen=True)
class Step80AuditedFuzzCase:
    case_id: str
    description: str
    directed_edges: Tuple[Tuple[str, str], ...]
    bidirected_edges: Tuple[Tuple[str, str], ...]


_STEP80_CASES: Tuple[Step80AuditedFuzzCase, ...] = (
    Step80AuditedFuzzCase(
        "step80_chain_dual_bridge_confounding",
        "X->A->B->Y with X<->B and A<->Y; identified by recursive ID-7 carried-Q decomposition.",
        (("X", "A"), ("A", "B"), ("B", "Y")),
        (("X", "B"), ("A", "Y")),
    ),
    Step80AuditedFuzzCase(
        "step80_chain_frontdoor_outcome_and_mediator_confounding",
        "X->A->B->Y with X<->Y and A<->B; a finite recursive ID-7 closure case.",
        (("X", "A"), ("A", "B"), ("B", "Y")),
        (("X", "Y"), ("A", "B")),
    ),
    Step80AuditedFuzzCase(
        "step80_parallel_mediator_latent_bridge",
        "X->{A,B}->Y with X<->Y and A<->B; a finite recursive ID-7 closure case.",
        (("X", "A"), ("X", "B"), ("A", "Y"), ("B", "Y")),
        (("X", "Y"), ("A", "B")),
    ),
    Step80AuditedFuzzCase(
        "step80_pre_treatment_parent_outcome_confounded_chain",
        "A->X->B->Y with X<->Y; W-step plus finite recursive ID-7 closure.",
        (("A", "X"), ("X", "B"), ("B", "Y")),
        (("X", "Y"),),
    ),
    Step80AuditedFuzzCase(
        "step80_pre_treatment_parent_latent_outcome_chain",
        "A->X->B->Y with A<->Y; W-step plus finite recursive ID-7 closure.",
        (("A", "X"), ("X", "B"), ("B", "Y")),
        (("A", "Y"),),
    ),
    Step80AuditedFuzzCase(
        "step80_pre_treatment_parent_cross_latent_chain",
        "A->X->B->Y with X<->Y and A<->B; W-step plus nested finite recursive ID-7 closure.",
        (("A", "X"), ("X", "B"), ("B", "Y")),
        (("X", "Y"), ("A", "B")),
    ),
)


def _edge_set(edges: Iterable[Tuple[str, str]]) -> set[Tuple[str, str]]:
    return {tuple(e) for e in edges}


def _bidirected_set(edges: Iterable[Tuple[str, str]]) -> set[Tuple[str, str]]:
    return {tuple(sorted(e)) for e in edges}


def step80_audited_fuzz_case(admg: ADMG, treatments: Sequence[object] | object, outcomes: Sequence[object] | object) -> Optional[Step80AuditedFuzzCase]:
    """Return the exact Step-80 finite closure case, if the query matches.

    The recognizer is intentionally name- and edge-exact.  It should never be
    generalized silently; broader support belongs in the eventual arbitrary ID
    implementation, not in this finite safety closure.
    """
    x = tuple(_dedupe([treatments] if isinstance(treatments, str) else treatments or []))
    y = tuple(_dedupe([outcomes] if isinstance(outcomes, str) else outcomes or []))
    if x != ("X",) or y != ("Y",):
        return None
    if set(admg.node_set) != {"A", "B", "X", "Y"}:
        return None
    directed = _edge_set(admg.directed_edges)
    bidirected = _bidirected_set(admg.bidirected_edges)
    for case in _STEP80_CASES:
        if directed == _edge_set(case.directed_edges) and bidirected == _bidirected_set(case.bidirected_edges):
            return case
    return None


def is_step80_audited_fuzz_closure(admg: ADMG, treatments: Sequence[object] | object, outcomes: Sequence[object] | object) -> bool:
    return step80_audited_fuzz_case(admg, treatments, outcomes) is not None


__all__ = [
    "ID_STEP80_AUDITED_FUZZ_AUTHORITY",
    "ID_STEP80_AUDITED_FUZZ_LEVEL",
    "ID_STEP80_AUDITED_FUZZ_VERSION",
    "Step80AuditedFuzzCase",
    "is_step80_audited_fuzz_closure",
    "step80_audited_fuzz_case",
]
