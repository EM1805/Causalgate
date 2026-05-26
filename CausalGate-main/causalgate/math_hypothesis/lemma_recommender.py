from __future__ import annotations

"""Recommendation engine for the mathematical hypothesis dialogue loop."""

from typing import Any, Dict, List, Mapping

from .claim_schema import normalize_math_claim


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def recommend_next_lemmas(payload: Mapping[str, Any], verdict: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    claim = normalize_math_claim(payload)
    verdict = _as_dict(verdict)
    reason_codes = set(str(x) for x in verdict.get("reason_codes", []) or [])
    open_problem = _clean_str(verdict.get("open_problem_detected"))
    suggestions: List[str] = []
    proof_obligations: List[Dict[str, str]] = []

    if "MISSING_CLAIM" in reason_codes:
        suggestions.append("Write one precise mathematical statement before attempting proof search.")
    if "NEEDS_FORMAL_STATEMENT" in reason_codes or not claim.formal_statement:
        suggestions.extend([
            "Define the domain, quantifiers, and all symbols in a minimal formal statement.",
            "Separate the main conjecture from auxiliary assumptions.",
        ])
        proof_obligations.append({"id": "formalize_main_statement", "kind": "formalization", "description": "Translate the claim into a checker-ready statement with explicit quantifiers."})
    if "PROOF_OVERCLAIM_WITHOUT_TRUSTED_FORMAL_ATTESTATION" in reason_codes:
        suggestions.extend([
            "Remove solved/proved wording and relabel the output as a proof sketch or conjecture.",
            "Extract the first unverified inference as a named lemma.",
            "Attach a checker task for the smallest lemma, not the whole theorem.",
        ])
        proof_obligations.append({"id": "first_unverified_inference", "kind": "lemma", "description": "State the smallest inference in the proof sketch that is not justified by a known theorem."})
    if open_problem == "riemann_hypothesis":
        suggestions.extend([
            "Do not attempt to claim RH solved; work on an equivalent or weaker lemma.",
            "Specify whether the statement concerns analytic continuation, functional equation, zero-free regions, or an equivalent criterion.",
            "Route any alleged proof to independent formal and expert review before public theorem language.",
        ])
        proof_obligations.extend([
            {"id": "rh_scope_definition", "kind": "formalization", "description": "State exactly which RH-equivalent formulation is being discussed."},
            {"id": "rh_gap_isolation", "kind": "gap_analysis", "description": "Identify the first step where zeros on the critical strip are constrained to Re(s)=1/2."},
        ])
    if "NUMERICAL_EVIDENCE_IS_NOT_PROOF" in reason_codes:
        suggestions.extend([
            "Convert computations into a falsifiable finite proposition and a symbolic conjecture explaining the pattern.",
            "Search for counterexamples outside the tested range before strengthening the claim.",
        ])
        proof_obligations.append({"id": "numeric_to_symbolic_bridge", "kind": "lemma", "description": "State a symbolic reason that would imply the observed numerical pattern."})
    if "NEEDS_LEMMA_DECOMPOSITION" in reason_codes:
        suggestions.extend([
            "Split the statement into prerequisites, reduction lemma, core lemma, and conclusion lemma.",
            "Mark each lemma as known, needs proof, or computationally tested only.",
        ])
        proof_obligations.append({"id": "lemma_decomposition", "kind": "planning", "description": "Produce at least three smaller proof obligations with dependencies."})
    if not suggestions:
        suggestions.extend([
            "Keep the claim bounded to proof-sketch language.",
            "Create the next formal proof obligation and run an external checker before upgrading claim level.",
        ])
        proof_obligations.append({"id": "next_checker_task", "kind": "proof_assistant_task", "description": "Formalize and verify the next unproven lemma."})

    # Stable de-duplication.
    deduped: List[str] = []
    seen = set()
    for item in suggestions:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    unique_obligations: List[Dict[str, str]] = []
    seen_ids = set()
    for item in proof_obligations:
        item_id = item.get("id", "")
        if item_id and item_id not in seen_ids:
            seen_ids.add(item_id)
            unique_obligations.append(item)

    return {
        "matrix_version": "math_lemma_recommender_v1_step99",
        "claim_id": claim.claim_id,
        "open_problem_detected": open_problem,
        "suggestions": deduped,
        "proof_obligations": unique_obligations,
        "next_llm_instruction": "Revise the claim using only the allowed claim level and return a smaller proof obligation, not a final theorem claim.",
    }


__all__ = ["recommend_next_lemmas"]
