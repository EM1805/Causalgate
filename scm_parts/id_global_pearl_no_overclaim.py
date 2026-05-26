from __future__ import annotations

"""Step 96 adversarial no-overclaim suite for Global Pearl-complete veto.

After Step 94/95 the Global Full-ID backend and Global Pearl-complete runtime
veto are green.  This module keeps that release honest by running negative
claims that must remain blocked: stale cards, missing Step94 evidence, non-veto
runtime decisions, finite/template formula authority, and tampered/replayed
runtime attestations.
"""

import copy
import json
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Tuple

from common.pearl_global_veto_attestation import (
    PEARL_GLOBAL_REQUIRED_CONTROLLED_FLIP,
    PEARL_GLOBAL_REQUIRED_ORACLE_PARITY_MATRIX,
    PEARL_GLOBAL_REQUIRED_PROMOTION_GATE,
    PEARL_GLOBAL_REQUIRED_READINESS_MATRIX,
    PEARL_GLOBAL_VETO_ATTESTATION_VERSION,
    global_pearl_veto_attestation_digest,
    verify_global_pearl_veto_attestation,
    verify_global_pearl_veto_attestation_against_context,
)
from runtime.causal_authority import attach_causal_authority, build_veto_authority_readiness
from scm_parts.id_global_pearl_veto_release import build_current_global_pearl_authority_card

ID_GLOBAL_PEARL_NO_OVERCLAIM_MATRIX_VERSION = "veto_pearl_global_no_overclaim_adversarial_suite_v1_step96"
ID_GLOBAL_PEARL_NO_OVERCLAIM_LEVEL = (
    "adversarial_negative_suite_blocks_global_pearl_complete_veto_overclaim_"
    "for_stale_matrix_or_release_versions_missing_step94_non_veto_decisions_"
    "finite_authority_and_tampered_or_replayed_runtime_attestations"
)


Adversary = Tuple[str, str, Callable[[Dict[str, object]], Dict[str, object]], str]


def _write_card(cards_path: Path, card: Mapping[str, object]) -> None:
    cards_path.write_text(json.dumps(card, sort_keys=True), encoding="utf-8")


def _runtime_for_card(card: Mapping[str, object], *, decision: str = "HARD_BLOCK", path_id: str | None = None) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    with tempfile.TemporaryDirectory() as tmp:
        cards_path = Path(tmp) / "cards.jsonl"
        _write_card(cards_path, card)
        pid = path_id or str(card.get("path_id") or "global_pearl_path")
        paths = attach_causal_authority([{"path_id": pid}], cards_path=str(cards_path))
        readiness = build_veto_authority_readiness(paths, {"decision": decision})
        return paths, readiness


def _pearl(card: Dict[str, object]) -> Dict[str, object]:
    pearl = card.setdefault("pearl_veto_authority", {})
    if not isinstance(pearl, dict):
        pearl = {}
        card["pearl_veto_authority"] = pearl
    return pearl


def _mutate_runtime_use(card: Dict[str, object]) -> Dict[str, object]:
    card["runtime_use"] = "policy_or_structural_veto_only"
    return card


def _mutate_formula_authority(card: Dict[str, object]) -> Dict[str, object]:
    _pearl(card)["primary_formula_authority"] = "id_canonical_formula_step60"
    return card


def _mutate_claim_flag_zero(card: Dict[str, object]) -> Dict[str, object]:
    _pearl(card)["full_id_claim_allowed"] = 0
    return card


def _mutate_failure_coverage_missing(card: Dict[str, object]) -> Dict[str, object]:
    _pearl(card)["formal_failure_certificate_coverage_complete"] = 0
    _pearl(card)["formal_failure_certificate_coverage"] = "incomplete"
    return card


def _mutate_step94_missing(card: Dict[str, object]) -> Dict[str, object]:
    pearl = _pearl(card)
    pearl.pop("id_global_full_id_controlled_flip_passed", None)
    pearl.pop("global_full_id_controlled_flip_allowed", None)
    return card


def _mutate_promotion_gate_zero(card: Dict[str, object]) -> Dict[str, object]:
    _pearl(card)["id_full_promotion_gate_passed"] = 0
    return card


def _mutate_stale_readiness_matrix(card: Dict[str, object]) -> Dict[str, object]:
    _pearl(card)["id_full_readiness_matrix"] = "id_full_readiness_matrix_v0_stale"
    return card


def _mutate_stale_oracle_matrix(card: Dict[str, object]) -> Dict[str, object]:
    _pearl(card)["id_oracle_parity_matrix"] = "id_oracle_parity_matrix_v0_stale"
    return card


def _mutate_stale_promotion_gate(card: Dict[str, object]) -> Dict[str, object]:
    _pearl(card)["id_full_promotion_gate"] = "id_full_promotion_gate_v0_stale"
    return card


def _mutate_stale_controlled_flip(card: Dict[str, object]) -> Dict[str, object]:
    _pearl(card)["id_global_full_id_controlled_flip"] = "id_global_full_id_controlled_flip_v0_stale"
    return card


CARD_ADVERSARIES: List[Adversary] = [
    ("card_runtime_use_policy_only", "card_without_causal_runtime_use_must_not_unlock_global_pearl", _mutate_runtime_use, "pearl_complete_veto_requires_causal_veto_authorized_top_path_first"),
    ("card_finite_formula_authority", "finite_or_template_formula_authority_must_not_unlock_global_pearl", _mutate_formula_authority, "pearl_complete_formula_authority_allowed"),
    ("card_full_id_claim_flag_zero", "full_id_claim_allowed_zero_must_block_global_pearl", _mutate_claim_flag_zero, "full_id_claim_allowed"),
    ("card_failure_coverage_missing", "missing_failure_certificate_coverage_must_block_global_pearl", _mutate_failure_coverage_missing, "formal_failure_certificate_coverage_complete"),
    ("card_step94_evidence_missing", "missing_step94_controlled_flip_evidence_must_block_global_pearl", _mutate_step94_missing, "id_global_full_id_controlled_flip_passed"),
    ("card_promotion_gate_zero", "promotion_gate_zero_must_block_global_pearl", _mutate_promotion_gate_zero, "id_full_promotion_gate_passed"),
    ("card_stale_readiness_matrix_version", "stale_readiness_matrix_version_must_block_global_pearl", _mutate_stale_readiness_matrix, "id_full_readiness_matrix_version_matches"),
    ("card_stale_oracle_matrix_version", "stale_oracle_matrix_version_must_block_global_pearl", _mutate_stale_oracle_matrix, "id_oracle_parity_matrix_version_matches"),
    ("card_stale_promotion_gate_version", "stale_promotion_gate_version_must_block_global_pearl", _mutate_stale_promotion_gate, "id_full_promotion_gate_version_matches"),
    ("card_stale_controlled_flip_version", "stale_controlled_flip_version_must_block_global_pearl", _mutate_stale_controlled_flip, "id_global_full_id_controlled_flip_version_matches"),
]


def _build_attestation_context(readiness: Mapping[str, object], paths: List[Dict[str, object]]) -> Tuple[Dict[str, object], Dict[str, object]]:
    top_path_id = str(readiness.get("top_path_id") or "")
    top_source = next((p for p in paths if str(p.get("path_id") or "") == top_path_id), {})
    context = {
        "decision": readiness.get("decision"),
        "veto_like_decision": readiness.get("veto_like_decision"),
        "top_path_id": readiness.get("top_path_id"),
        "top_veto_authority_class": readiness.get("top_veto_authority_class"),
        "top_pearl_veto_authority_class": readiness.get("top_pearl_veto_authority_class"),
        "pearl_complete_veto_claim_allowed": readiness.get("pearl_complete_veto_claim_allowed"),
        "pearl_complete_veto_claim_reason": readiness.get("pearl_complete_veto_claim_reason"),
        "pearl_readiness_matrix": readiness.get("pearl_readiness_matrix"),
    }
    return context, top_source


def run_global_pearl_no_overclaim_suite() -> Dict[str, object]:
    rows: List[Dict[str, object]] = []

    # Positive control: the released card still passes.  This avoids a vacuous
    # negative suite that is green because the whole feature is accidentally off.
    control_card = build_current_global_pearl_authority_card("p1")
    control_paths, control_readiness = _runtime_for_card(control_card, decision="HARD_BLOCK", path_id="p1")
    control_attestation = dict(control_readiness.get("pearl_complete_veto_attestation") or {})
    control_passed = bool(control_readiness.get("pearl_complete_veto_claim_allowed")) and bool(control_readiness.get("pearl_complete_veto_attestation_verified"))
    rows.append({
        "case_id": "positive_control_global_pearl_veto_release",
        "adversarial": 0,
        "expected": "allowed",
        "observed_allowed": int(bool(control_readiness.get("pearl_complete_veto_claim_allowed"))),
        "blocked": int(not bool(control_readiness.get("pearl_complete_veto_claim_allowed"))),
        "passed": int(control_passed),
        "blocked_reason_contains": "",
        "observed_reason": str(control_readiness.get("pearl_complete_veto_claim_reason") or ""),
    })

    for case_id, description, mutator, expected_blocker in CARD_ADVERSARIES:
        card = mutator(copy.deepcopy(control_card))
        paths, readiness = _runtime_for_card(card, decision="HARD_BLOCK", path_id="p1")
        blocked = not bool(readiness.get("pearl_complete_veto_claim_allowed"))
        reason = str(readiness.get("pearl_complete_veto_claim_reason") or "")
        rows.append({
            "case_id": case_id,
            "description": description,
            "adversarial": 1,
            "expected": "blocked",
            "expected_blocker": expected_blocker,
            "observed_allowed": int(bool(readiness.get("pearl_complete_veto_claim_allowed"))),
            "causal_allowed": int(bool(readiness.get("causal_veto_claim_allowed"))),
            "attestation_emitted": int(bool(readiness.get("pearl_complete_veto_attestation"))),
            "blocked": int(blocked),
            "passed": int(blocked and (expected_blocker in reason or case_id.startswith("card_stale"))),
            "observed_reason": reason,
        })

    # Valid card + non-veto decision must not emit a Global Pearl veto claim.
    _, pass_readiness = _runtime_for_card(control_card, decision="PASS", path_id="p1")
    rows.append({
        "case_id": "runtime_non_veto_decision_pass",
        "description": "non_veto_decision_must_not_emit_global_pearl_attestation",
        "adversarial": 1,
        "expected": "blocked",
        "expected_blocker": "decision_is_not_a_veto_or_review_gate",
        "observed_allowed": int(bool(pass_readiness.get("pearl_complete_veto_claim_allowed"))),
        "attestation_emitted": int(bool(pass_readiness.get("pearl_complete_veto_attestation"))),
        "blocked": int(not bool(pass_readiness.get("pearl_complete_veto_claim_allowed")) and not bool(pass_readiness.get("pearl_complete_veto_attestation"))),
        "passed": int(not bool(pass_readiness.get("pearl_complete_veto_claim_allowed")) and not bool(pass_readiness.get("pearl_complete_veto_attestation"))),
        "observed_reason": str(pass_readiness.get("pearl_complete_veto_claim_reason") or ""),
    })

    # Attestation adversaries: the positive control attestation is modified and
    # must fail either intrinsic verification or contextual replay verification.
    context, top_source = _build_attestation_context(control_readiness, control_paths)

    tampered_decision = dict(control_attestation)
    tampered_decision["decision"] = "PASS"
    v = verify_global_pearl_veto_attestation(tampered_decision)
    rows.append({
        "case_id": "attestation_decision_tampered_no_rehash",
        "description": "decision_tampering_without_rehash_must_fail_digest_and_policy",
        "adversarial": 1,
        "expected": "blocked",
        "expected_blocker": "decision|attestation_digest",
        "observed_allowed": int(v.get("global_pearl_veto_attestation_verified", 0)),
        "digest_valid": int(v.get("global_pearl_veto_attestation_digest_valid", 0)),
        "blocked": int(not bool(v.get("global_pearl_veto_attestation_verified"))),
        "passed": int(not bool(v.get("global_pearl_veto_attestation_verified")) and "decision" in str(v.get("global_pearl_veto_attestation_mismatched_fields") or "")),
        "observed_reason": str(v.get("global_pearl_veto_attestation_mismatched_fields") or ""),
    })

    rehashed_pass = dict(control_attestation)
    rehashed_pass["decision"] = "PASS"
    rehashed_pass["attestation_digest"] = global_pearl_veto_attestation_digest(rehashed_pass)
    v = verify_global_pearl_veto_attestation(rehashed_pass)
    rows.append({
        "case_id": "attestation_non_veto_decision_rehashed",
        "description": "rehashed_non_veto_attestation_must_still_fail_policy",
        "adversarial": 1,
        "expected": "blocked",
        "expected_blocker": "decision",
        "observed_allowed": int(v.get("global_pearl_veto_attestation_verified", 0)),
        "digest_valid": int(v.get("global_pearl_veto_attestation_digest_valid", 0)),
        "blocked": int(not bool(v.get("global_pearl_veto_attestation_verified"))),
        "passed": int(not bool(v.get("global_pearl_veto_attestation_verified")) and int(v.get("global_pearl_veto_attestation_digest_valid", 0)) == 1),
        "observed_reason": str(v.get("global_pearl_veto_attestation_mismatched_fields") or ""),
    })

    replayed_other_path = dict(control_attestation)
    replayed_other_path["top_path_id"] = "evil_replayed_path"
    replayed_other_path["attestation_digest"] = global_pearl_veto_attestation_digest(replayed_other_path)
    v = verify_global_pearl_veto_attestation_against_context(replayed_other_path, readiness=context, top_path=top_source)
    rows.append({
        "case_id": "attestation_top_path_replayed_rehashed_contextual",
        "description": "rehashed_attestation_for_another_path_must_fail_contextual_verification",
        "adversarial": 1,
        "expected": "blocked",
        "expected_blocker": "top_path_id",
        "observed_allowed": int(v.get("global_pearl_veto_attestation_context_verified", 0)),
        "digest_valid": int(v.get("global_pearl_veto_attestation_digest_valid", 0)),
        "blocked": int(not bool(v.get("global_pearl_veto_attestation_context_verified"))),
        "passed": int(not bool(v.get("global_pearl_veto_attestation_context_verified")) and "top_path_id" in str(v.get("global_pearl_veto_attestation_context_mismatched_fields") or "")),
        "observed_reason": str(v.get("global_pearl_veto_attestation_context_mismatched_fields") or ""),
    })

    stale_readiness = dict(control_attestation)
    stale_readiness["id_full_readiness_matrix"] = "id_full_readiness_matrix_v0_stale"
    stale_readiness["attestation_digest"] = global_pearl_veto_attestation_digest(stale_readiness)
    v = verify_global_pearl_veto_attestation(stale_readiness)
    rows.append({
        "case_id": "attestation_stale_readiness_matrix_rehashed",
        "description": "stale_readiness_matrix_version_must_fail_even_when_rehashed",
        "adversarial": 1,
        "expected": "blocked",
        "expected_blocker": PEARL_GLOBAL_REQUIRED_READINESS_MATRIX,
        "observed_allowed": int(v.get("global_pearl_veto_attestation_verified", 0)),
        "digest_valid": int(v.get("global_pearl_veto_attestation_digest_valid", 0)),
        "blocked": int(not bool(v.get("global_pearl_veto_attestation_verified"))),
        "passed": int(not bool(v.get("global_pearl_veto_attestation_verified")) and "id_full_readiness_matrix" in str(v.get("global_pearl_veto_attestation_mismatched_fields") or "")),
        "observed_reason": str(v.get("global_pearl_veto_attestation_mismatched_fields") or ""),
    })

    stale_oracle = dict(control_attestation)
    stale_oracle["id_oracle_parity_matrix"] = "id_oracle_parity_matrix_v0_stale"
    stale_oracle["attestation_digest"] = global_pearl_veto_attestation_digest(stale_oracle)
    v = verify_global_pearl_veto_attestation(stale_oracle)
    rows.append({
        "case_id": "attestation_stale_oracle_matrix_rehashed",
        "description": "stale_oracle_matrix_version_must_fail_even_when_rehashed",
        "adversarial": 1,
        "expected": "blocked",
        "expected_blocker": PEARL_GLOBAL_REQUIRED_ORACLE_PARITY_MATRIX,
        "observed_allowed": int(v.get("global_pearl_veto_attestation_verified", 0)),
        "digest_valid": int(v.get("global_pearl_veto_attestation_digest_valid", 0)),
        "blocked": int(not bool(v.get("global_pearl_veto_attestation_verified"))),
        "passed": int(not bool(v.get("global_pearl_veto_attestation_verified")) and "id_oracle_parity_matrix" in str(v.get("global_pearl_veto_attestation_mismatched_fields") or "")),
        "observed_reason": str(v.get("global_pearl_veto_attestation_mismatched_fields") or ""),
    })

    stale_gate = dict(control_attestation)
    stale_gate["id_full_promotion_gate"] = "id_full_promotion_gate_v0_stale"
    stale_gate["attestation_digest"] = global_pearl_veto_attestation_digest(stale_gate)
    v = verify_global_pearl_veto_attestation(stale_gate)
    rows.append({
        "case_id": "attestation_stale_promotion_gate_rehashed",
        "description": "stale_promotion_gate_version_must_fail_even_when_rehashed",
        "adversarial": 1,
        "expected": "blocked",
        "expected_blocker": PEARL_GLOBAL_REQUIRED_PROMOTION_GATE,
        "observed_allowed": int(v.get("global_pearl_veto_attestation_verified", 0)),
        "digest_valid": int(v.get("global_pearl_veto_attestation_digest_valid", 0)),
        "blocked": int(not bool(v.get("global_pearl_veto_attestation_verified"))),
        "passed": int(not bool(v.get("global_pearl_veto_attestation_verified")) and "id_full_promotion_gate" in str(v.get("global_pearl_veto_attestation_mismatched_fields") or "")),
        "observed_reason": str(v.get("global_pearl_veto_attestation_mismatched_fields") or ""),
    })

    stale_flip = dict(control_attestation)
    stale_flip["id_global_full_id_controlled_flip"] = "id_global_full_id_controlled_flip_v0_stale"
    stale_flip["attestation_digest"] = global_pearl_veto_attestation_digest(stale_flip)
    v = verify_global_pearl_veto_attestation(stale_flip)
    rows.append({
        "case_id": "attestation_stale_controlled_flip_rehashed",
        "description": "stale_controlled_flip_version_must_fail_even_when_rehashed",
        "adversarial": 1,
        "expected": "blocked",
        "expected_blocker": PEARL_GLOBAL_REQUIRED_CONTROLLED_FLIP,
        "observed_allowed": int(v.get("global_pearl_veto_attestation_verified", 0)),
        "digest_valid": int(v.get("global_pearl_veto_attestation_digest_valid", 0)),
        "blocked": int(not bool(v.get("global_pearl_veto_attestation_verified"))),
        "passed": int(not bool(v.get("global_pearl_veto_attestation_verified")) and "id_global_full_id_controlled_flip" in str(v.get("global_pearl_veto_attestation_mismatched_fields") or "")),
        "observed_reason": str(v.get("global_pearl_veto_attestation_mismatched_fields") or ""),
    })

    missing_field = dict(control_attestation)
    missing_field.pop("runtime_use", None)
    v = verify_global_pearl_veto_attestation(missing_field)
    rows.append({
        "case_id": "attestation_missing_binding_field",
        "description": "missing_bound_runtime_use_field_must_fail",
        "adversarial": 1,
        "expected": "blocked",
        "expected_blocker": "runtime_use",
        "observed_allowed": int(v.get("global_pearl_veto_attestation_verified", 0)),
        "digest_valid": int(v.get("global_pearl_veto_attestation_digest_valid", 0)),
        "blocked": int(not bool(v.get("global_pearl_veto_attestation_verified"))),
        "passed": int(not bool(v.get("global_pearl_veto_attestation_verified")) and "runtime_use" in str(v.get("global_pearl_veto_attestation_missing_fields") or "")),
        "observed_reason": str(v.get("global_pearl_veto_attestation_missing_fields") or ""),
    })

    n_cases = len(rows)
    n_adversarial_cases = sum(int(r.get("adversarial", 0)) for r in rows)
    n_passed = sum(int(r.get("passed", 0)) for r in rows)
    failed_case_ids = "|".join(str(r.get("case_id")) for r in rows if not int(r.get("passed", 0)))
    return {
        "matrix_version": ID_GLOBAL_PEARL_NO_OVERCLAIM_MATRIX_VERSION,
        "level": ID_GLOBAL_PEARL_NO_OVERCLAIM_LEVEL,
        "global_pearl_veto_attestation_version": PEARL_GLOBAL_VETO_ATTESTATION_VERSION,
        "all_passed": int(n_passed == n_cases),
        "n_cases": n_cases,
        "n_passed": n_passed,
        "n_adversarial_cases": n_adversarial_cases,
        "n_adversarial_cases_blocked": sum(int(r.get("blocked", 0)) for r in rows if int(r.get("adversarial", 0))),
        "failed_case_ids": failed_case_ids,
        "positive_control_allowed": int(control_passed),
        "required_readiness_matrix": PEARL_GLOBAL_REQUIRED_READINESS_MATRIX,
        "required_oracle_matrix": PEARL_GLOBAL_REQUIRED_ORACLE_PARITY_MATRIX,
        "required_promotion_gate": PEARL_GLOBAL_REQUIRED_PROMOTION_GATE,
        "required_controlled_flip": PEARL_GLOBAL_REQUIRED_CONTROLLED_FLIP,
        "rows": rows,
    }


__all__ = [
    "ID_GLOBAL_PEARL_NO_OVERCLAIM_MATRIX_VERSION",
    "ID_GLOBAL_PEARL_NO_OVERCLAIM_LEVEL",
    "run_global_pearl_no_overclaim_suite",
]
