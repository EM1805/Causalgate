from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

from common.pearl_scope_manifest import (
    PEARL_SCOPED_SCOPE_MANIFEST_VERSION,
    verify_scoped_pearl_manifest,
)
from common.pearl_release_manifest import (
    PEARL_SCOPED_RELEASE_MANIFEST_VERSION,
    verify_scoped_pearl_release_manifest,
)
from common.pearl_veto_attestation import (
    PEARL_SCOPED_VETO_ATTESTATION_VERSION,
    build_scoped_pearl_veto_attestation,
    verify_scoped_pearl_veto_attestation,
)
from common.pearl_global_veto_attestation import (
    PEARL_GLOBAL_REQUIRED_CONTROLLED_FLIP,
    PEARL_GLOBAL_REQUIRED_ORACLE_PARITY_MATRIX,
    PEARL_GLOBAL_REQUIRED_PROMOTION_GATE,
    PEARL_GLOBAL_REQUIRED_READINESS_MATRIX,
    PEARL_GLOBAL_VETO_ATTESTATION_VERSION,
    build_global_pearl_veto_attestation,
    verify_global_pearl_veto_attestation,
    verify_global_pearl_veto_attestation_against_context,
)

CAUSAL_VETO_ALLOWED_RUNTIME_USES = {
    "causal_veto_allowed",
    "causal_veto_allowed_with_aggregate_outcome_caution",
}

VETO_LIKE_DECISIONS = {"HARD_BLOCK", "REVIEW"}

# Step 82: a causal-veto authority card is not enough to call a veto
# "Pearl-complete".  Pearl-complete wording is a stronger claim and is gated by
# explicit evidence that the offline identification backend has raised the
# Full-ID completeness claim **and** that the path-level formula authority is a
# true full-recursive-ID authority.  Finite audited closures (Step 75/79/80) may
# authorize local causal language, but they cannot authorize Pearl-complete
# wording.  The current CausalGate backend deliberately keeps the global Full-ID
# flags at 0, so this layer is expected to block Pearl-complete wording unless a
# future card carries the full evidence bundle.
PEARL_COMPLETE_VETO_REQUIRED_FLAGS = (
    "full_recursive_id_implemented",
    "full_id_claim_allowed",
    "id_oracle_parity_fuzz_passed",
    "formal_failure_certificate_coverage_complete",
    "id_full_promotion_gate_passed",
    "id_global_full_id_controlled_flip_passed",
)
PEARL_COMPLETE_VETO_REQUIRED_DERIVED_FLAGS = (
    "id_full_readiness_matrix_passed",
    "pearl_complete_formula_authority_allowed",
    "id_full_readiness_matrix_version_matches",
    "id_oracle_parity_matrix_version_matches",
    "id_full_promotion_gate_version_matches",
    "id_global_full_id_controlled_flip_version_matches",
)
PEARL_COMPLETE_FORMULA_AUTHORITIES = {
    "full_recursive_id_canonical_formula_authority",
    "full_recursive_id_formula_authority",
    "shpitser_pearl_full_recursive_id_authority",
}
PEARL_COMPLETE_VETO_CLASS_AUTHORIZED = "pearl_complete_veto_authorized"
PEARL_COMPLETE_VETO_CLASS_BLOCKED = "pearl_complete_veto_not_authorized"
PEARL_COMPLETE_VETO_CLASS_NOT_CAUSAL = "not_causal_veto"
PEARL_COMPLETE_VETO_READINESS_MATRIX = "veto_pearl_complete_authority_readiness_v5_step96"

# Step 87/88: scoped Pearl-veto wording is narrower than Pearl-complete wording.
# It can be authorized only for the audited public readiness/oracle/fuzz surface
# that carries Step-84 failure-certificate coverage and Step-86 recursive-trace
# formula authority.  Step 88 additionally requires a hash-bound scope
# manifest, so stale/tampered authority cards cannot unlock scoped Pearl
# wording.  It deliberately does not raise the global Full-ID flags.
PEARL_SCOPED_VETO_REQUIRED_FLAGS = (
    "scoped_full_recursive_id_implemented",
    "scoped_full_id_claim_allowed",
    "id_full_readiness_matrix_passed",
    "id_oracle_parity_fuzz_passed",
    "formal_failure_certificate_coverage_complete",
    "id_scoped_pearl_promotion_gate_passed",
)
PEARL_SCOPED_VETO_REQUIRED_DERIVED_FLAGS = (
    "pearl_scoped_formula_authority_allowed",
    "scoped_pearl_manifest_verified",
    "scoped_pearl_release_verified",
)
PEARL_SCOPED_FORMULA_AUTHORITIES = set(PEARL_COMPLETE_FORMULA_AUTHORITIES) | {
    "full_recursive_id_trace_formula_authority_step86",
}
PEARL_SCOPED_VETO_CLASS_AUTHORIZED = "pearl_scoped_veto_authorized"
PEARL_SCOPED_VETO_CLASS_BLOCKED = "pearl_scoped_veto_not_authorized"
PEARL_SCOPED_VETO_CLASS_NOT_CAUSAL = "not_causal_veto"
PEARL_SCOPED_VETO_READINESS_MATRIX = "veto_pearl_scoped_authority_readiness_v4_step90"



def load_causal_authority_cards(path: str = "out/veto/causal_authority_cards.jsonl") -> Dict[str, Dict[str, Any]]:
    """Load precomputed offline causal authority cards keyed by path_id.

    Missing files are not errors: runtime must remain bounded and conservative.
    """
    p = Path(path)
    if not p.exists():
        return {}
    cards: Dict[str, Dict[str, Any]] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            card = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(card, dict):
            continue
        path_id = str(card.get("path_id") or "").strip()
        if path_id:
            cards[path_id] = card
    return cards


def _truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "pass", "passed", "complete", "green"}


def _as_mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _causal_claim_class_for_path(path: Dict[str, Any]) -> str:
    """Classify how a runtime veto path may be described.

    The class is intentionally conservative.  A path is called
    ``causal_veto_authorized`` only when an offline authority card explicitly
    grants one of the runtime causal-veto uses.  Every other path is downgraded
    to a policy/structural class even when it contains causal context.
    """
    row = dict(path or {})
    authority = row.get("causal_authority") if isinstance(row.get("causal_authority"), dict) else {}
    runtime_use = str((authority or {}).get("runtime_use") or "").strip()
    authority_level = str((authority or {}).get("authority_level") or "").strip()

    if bool(row.get("causal_veto_authorized")) and runtime_use in CAUSAL_VETO_ALLOWED_RUNTIME_USES:
        return "causal_veto_authorized"

    if runtime_use and runtime_use not in {"policy_or_structural_veto_only", ""}:
        return "causal_veto_not_authorized"

    if authority_level and authority_level not in {"not_available", "", "none"}:
        return "structural_veto"

    structural_evidence = str(row.get("evidence_strength") or row.get("structural_tier") or "").lower()
    if (
        bool(row.get("graph_supported"))
        or str(row.get("severity") or "").lower() in {"high", "critical"}
        or "structural" in structural_evidence
        or bool(row.get("hard_block_hits"))
    ):
        return "structural_veto"

    return "policy_veto"


def _causal_claim_reason_for_path(path: Dict[str, Any], claim_class: str) -> str:
    authority = path.get("causal_authority") if isinstance(path.get("causal_authority"), dict) else {}
    if claim_class == "causal_veto_authorized":
        return str(authority.get("authority_reason") or "precomputed_causal_authority_card_allows_causal_veto_claim")
    if claim_class == "causal_veto_not_authorized":
        return str(authority.get("authority_reason") or "causal_context_exists_but_runtime_use_does_not_authorize_causal_veto_claim")
    if claim_class == "structural_veto":
        return "runtime_path_is_structural_or_graph_supported_but_lacks_explicit_causal_veto_authority"
    return "runtime_decision_is_policy_guardrail_without_explicit_causal_veto_authority"


def _pearl_evidence_from_card(card: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the Step-78 Pearl-complete evidence bundle from an authority card.

    Cards may carry the evidence under ``pearl_veto_authority`` or, for
    forward-compatible test fixtures, as top-level fields.  We derive the final
    allow/block decision at runtime rather than trusting a single boolean claim.
    """
    pearl = _as_mapping(card.get("pearl_veto_authority"))

    def pick(key: str, default: Any = 0) -> Any:
        if key in pearl:
            return pearl.get(key)
        return card.get(key, default)

    matrix = str(pick("id_full_readiness_matrix", "") or pick("readiness_matrix", "") or "")
    oracle_matrix = str(pick("id_oracle_parity_matrix", "") or "")
    promotion_gate = str(pick("id_full_promotion_gate", "") or "")
    controlled_flip = str(pick("id_global_full_id_controlled_flip", "") or "")
    formula_authority = str(pick("primary_formula_authority", "") or card.get("contract_authority_level", "") or "")
    identification_status = str(pick("identification_status", "") or card.get("contract_identification_status", "") or "")
    failure_coverage_raw = pick("formal_failure_certificate_coverage_complete", None)
    if failure_coverage_raw is None:
        failure_coverage_raw = pick("formal_failure_certificate_coverage", "")
    coverage_complete = _truthy_flag(failure_coverage_raw)

    formula_authority_allowed = formula_authority in PEARL_COMPLETE_FORMULA_AUTHORITIES
    evidence = {
        "full_recursive_id_implemented": int(_truthy_flag(pick("full_recursive_id_implemented", 0))),
        "full_id_claim_allowed": int(_truthy_flag(pick("full_id_claim_allowed", 0))),
        "id_full_readiness_matrix": matrix,
        "id_full_readiness_matrix_passed": int(_truthy_flag(pick("id_full_readiness_matrix_passed", 0))),
        "id_full_readiness_matrix_expected": PEARL_GLOBAL_REQUIRED_READINESS_MATRIX,
        "id_full_readiness_matrix_version_matches": int(matrix == PEARL_GLOBAL_REQUIRED_READINESS_MATRIX),
        "id_oracle_parity_matrix": oracle_matrix,
        "id_oracle_parity_fuzz_passed": int(_truthy_flag(pick("id_oracle_parity_fuzz_passed", 0))),
        "id_oracle_parity_matrix_expected": PEARL_GLOBAL_REQUIRED_ORACLE_PARITY_MATRIX,
        "id_oracle_parity_matrix_version_matches": int(oracle_matrix == PEARL_GLOBAL_REQUIRED_ORACLE_PARITY_MATRIX),
        "formal_failure_certificate_coverage_complete": int(coverage_complete),
        "id_full_promotion_gate": promotion_gate,
        "id_full_promotion_gate_passed": int(_truthy_flag(pick("id_full_promotion_gate_passed", 0))),
        "id_full_promotion_gate_expected": PEARL_GLOBAL_REQUIRED_PROMOTION_GATE,
        "id_full_promotion_gate_version_matches": int(promotion_gate == PEARL_GLOBAL_REQUIRED_PROMOTION_GATE),
        "id_global_full_id_controlled_flip": controlled_flip,
        "id_global_full_id_controlled_flip_passed": int(_truthy_flag(pick("id_global_full_id_controlled_flip_passed", pick("global_full_id_controlled_flip_allowed", 0)))),
        "id_global_full_id_controlled_flip_expected": PEARL_GLOBAL_REQUIRED_CONTROLLED_FLIP,
        "id_global_full_id_controlled_flip_version_matches": int(controlled_flip == PEARL_GLOBAL_REQUIRED_CONTROLLED_FLIP),
        "global_full_id_controlled_flip_allowed": int(_truthy_flag(pick("global_full_id_controlled_flip_allowed", pick("id_global_full_id_controlled_flip_passed", 0)))),
        "formal_failure_certificate_coverage": "complete" if coverage_complete else str(pick("formal_failure_certificate_coverage", "not_asserted") or "not_asserted"),
        "primary_formula_authority": formula_authority,
        "pearl_complete_formula_authority_allowed": int(formula_authority_allowed),
        "pearl_complete_allowed_formula_authorities": sorted(PEARL_COMPLETE_FORMULA_AUTHORITIES),
        "identification_status": identification_status,
        "pearl_claim_source": str(pick("pearl_claim_source", "authority_card_evidence_bundle") or "authority_card_evidence_bundle"),
    }
    missing = [k for k in PEARL_COMPLETE_VETO_REQUIRED_FLAGS if not _truthy_flag(evidence.get(k))]
    for key in PEARL_COMPLETE_VETO_REQUIRED_DERIVED_FLAGS:
        if not _truthy_flag(evidence.get(key)):
            missing.append(key)
    evidence["missing_required_flags"] = missing
    evidence["pearl_complete_evidence_bundle_present"] = int(not missing)
    return evidence


def _default_pearl_evidence(reason: str = "no_precomputed_pearl_complete_authority_bundle_for_path") -> Dict[str, Any]:
    return {
        "full_recursive_id_implemented": 0,
        "full_id_claim_allowed": 0,
        "id_full_readiness_matrix": "",
        "id_full_readiness_matrix_passed": 0,
        "id_full_readiness_matrix_expected": PEARL_GLOBAL_REQUIRED_READINESS_MATRIX,
        "id_full_readiness_matrix_version_matches": 0,
        "id_oracle_parity_matrix": "",
        "id_oracle_parity_fuzz_passed": 0,
        "id_oracle_parity_matrix_expected": PEARL_GLOBAL_REQUIRED_ORACLE_PARITY_MATRIX,
        "id_oracle_parity_matrix_version_matches": 0,
        "formal_failure_certificate_coverage_complete": 0,
        "id_full_promotion_gate": "",
        "id_full_promotion_gate_passed": 0,
        "id_full_promotion_gate_expected": PEARL_GLOBAL_REQUIRED_PROMOTION_GATE,
        "id_full_promotion_gate_version_matches": 0,
        "id_global_full_id_controlled_flip": "",
        "id_global_full_id_controlled_flip_passed": 0,
        "id_global_full_id_controlled_flip_expected": PEARL_GLOBAL_REQUIRED_CONTROLLED_FLIP,
        "id_global_full_id_controlled_flip_version_matches": 0,
        "global_full_id_controlled_flip_allowed": 0,
        "formal_failure_certificate_coverage": "not_asserted",
        "primary_formula_authority": "",
        "identification_status": "",
        "pearl_claim_source": reason,
        "pearl_complete_formula_authority_allowed": 0,
        "pearl_complete_allowed_formula_authorities": sorted(PEARL_COMPLETE_FORMULA_AUTHORITIES),
        "missing_required_flags": list(PEARL_COMPLETE_VETO_REQUIRED_FLAGS) + list(PEARL_COMPLETE_VETO_REQUIRED_DERIVED_FLAGS),
        "pearl_complete_evidence_bundle_present": 0,
    }


def _pearl_scoped_evidence_from_card(card: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the Step-87 scoped Pearl-veto evidence bundle from a card."""
    scoped = _as_mapping(card.get("pearl_scoped_veto_authority"))

    def pick(key: str, default: Any = 0) -> Any:
        if key in scoped:
            return scoped.get(key)
        return card.get(key, default)

    formula_authority = str(pick("primary_formula_authority", "") or card.get("contract_authority_level", "") or "")
    coverage_raw = pick("formal_failure_certificate_coverage_complete", None)
    if coverage_raw is None:
        coverage_raw = pick("formal_failure_certificate_coverage", "")
    coverage_complete = _truthy_flag(coverage_raw)
    formula_authority_allowed = formula_authority in PEARL_SCOPED_FORMULA_AUTHORITIES
    evidence = {
        "scoped_full_recursive_id_implemented": int(_truthy_flag(pick("scoped_full_recursive_id_implemented", 0))),
        "scoped_full_id_claim_allowed": int(_truthy_flag(pick("scoped_full_id_claim_allowed", 0))),
        "global_full_recursive_id_implemented": int(_truthy_flag(pick("global_full_recursive_id_implemented", pick("full_recursive_id_implemented", 0)))),
        "global_full_id_claim_allowed": int(_truthy_flag(pick("global_full_id_claim_allowed", pick("full_id_claim_allowed", 0)))),
        "id_full_readiness_matrix": str(pick("id_full_readiness_matrix", "") or ""),
        "id_full_readiness_matrix_passed": int(_truthy_flag(pick("id_full_readiness_matrix_passed", 0))),
        "id_oracle_parity_matrix": str(pick("id_oracle_parity_matrix", "") or ""),
        "id_oracle_parity_fuzz_passed": int(_truthy_flag(pick("id_oracle_parity_fuzz_passed", 0))),
        "formal_failure_certificate_coverage_complete": int(coverage_complete),
        "formal_failure_certificate_coverage": "complete" if coverage_complete else str(pick("formal_failure_certificate_coverage", "not_asserted") or "not_asserted"),
        "id_scoped_pearl_promotion_gate": str(pick("id_scoped_pearl_promotion_gate", "") or ""),
        "id_scoped_pearl_promotion_gate_passed": int(_truthy_flag(pick("id_scoped_pearl_promotion_gate_passed", 0))),
        "scope": str(pick("scope", "") or pick("pearl_claim_scope", "") or ""),
        "primary_formula_authority": formula_authority,
        "pearl_scoped_formula_authority_allowed": int(formula_authority_allowed),
        "pearl_scoped_allowed_formula_authorities": sorted(PEARL_SCOPED_FORMULA_AUTHORITIES),
        "pearl_claim_source": str(pick("pearl_claim_source", "scoped_pearl_authority_card_evidence_bundle") or "scoped_pearl_authority_card_evidence_bundle"),
    }
    manifest_raw = pick("scoped_pearl_manifest", {})
    manifest_verification = verify_scoped_pearl_manifest(manifest_raw, evidence=evidence)
    evidence.update(manifest_verification)
    evidence["scoped_pearl_required_manifest_version"] = PEARL_SCOPED_SCOPE_MANIFEST_VERSION
    release_raw = pick("scoped_pearl_release_manifest", {})
    release_verification = verify_scoped_pearl_release_manifest(release_raw, scoped_manifest=manifest_raw)
    evidence.update(release_verification)
    evidence["scoped_pearl_required_release_manifest_version"] = PEARL_SCOPED_RELEASE_MANIFEST_VERSION
    missing = [k for k in PEARL_SCOPED_VETO_REQUIRED_FLAGS if not _truthy_flag(evidence.get(k))]
    for key in PEARL_SCOPED_VETO_REQUIRED_DERIVED_FLAGS:
        if not _truthy_flag(evidence.get(key)):
            missing.append(key)
    evidence["missing_required_flags"] = missing
    evidence["pearl_scoped_evidence_bundle_present"] = int(not missing)
    return evidence


def _default_pearl_scoped_evidence(reason: str = "no_precomputed_scoped_pearl_authority_bundle_for_path") -> Dict[str, Any]:
    return {
        "scoped_full_recursive_id_implemented": 0,
        "scoped_full_id_claim_allowed": 0,
        "global_full_recursive_id_implemented": 0,
        "global_full_id_claim_allowed": 0,
        "id_full_readiness_matrix": "",
        "id_full_readiness_matrix_passed": 0,
        "id_oracle_parity_matrix": "",
        "id_oracle_parity_fuzz_passed": 0,
        "formal_failure_certificate_coverage_complete": 0,
        "formal_failure_certificate_coverage": "not_asserted",
        "id_scoped_pearl_promotion_gate": "",
        "id_scoped_pearl_promotion_gate_passed": 0,
        "scope": "",
        "primary_formula_authority": "",
        "pearl_scoped_formula_authority_allowed": 0,
        "pearl_scoped_allowed_formula_authorities": sorted(PEARL_SCOPED_FORMULA_AUTHORITIES),
        "scoped_pearl_manifest_present": 0,
        "scoped_pearl_manifest_verified": 0,
        "scoped_pearl_manifest_version": "",
        "scoped_pearl_manifest_digest": "",
        "scoped_pearl_required_manifest_version": PEARL_SCOPED_SCOPE_MANIFEST_VERSION,
        "scoped_pearl_manifest_reason": reason,
        "scoped_pearl_release_present": 0,
        "scoped_pearl_release_verified": 0,
        "scoped_pearl_release_manifest_version": "",
        "scoped_pearl_release_manifest_digest": "",
        "scoped_pearl_required_release_manifest_version": PEARL_SCOPED_RELEASE_MANIFEST_VERSION,
        "scoped_pearl_release_reason": reason,
        "pearl_claim_source": reason,
        "missing_required_flags": list(PEARL_SCOPED_VETO_REQUIRED_FLAGS) + list(PEARL_SCOPED_VETO_REQUIRED_DERIVED_FLAGS),
        "pearl_scoped_evidence_bundle_present": 0,
    }


def _pearl_scoped_claim_for_path(path: Dict[str, Any]) -> Tuple[str, bool, str]:
    if _causal_claim_class_for_path(path) != "causal_veto_authorized":
        return (
            PEARL_SCOPED_VETO_CLASS_NOT_CAUSAL,
            False,
            "pearl_scoped_veto_requires_causal_veto_authorized_top_path_first",
        )
    evidence = _as_mapping(path.get("pearl_scoped_veto_authority"))
    if not evidence:
        return (
            PEARL_SCOPED_VETO_CLASS_BLOCKED,
            False,
            "missing_scoped_pearl_authority_evidence_bundle",
        )
    missing = [str(v) for v in evidence.get("missing_required_flags", []) or []]
    if missing:
        return (
            PEARL_SCOPED_VETO_CLASS_BLOCKED,
            False,
            "pearl_scoped_veto_blocked_missing_" + "|".join(missing),
        )
    return (
        PEARL_SCOPED_VETO_CLASS_AUTHORIZED,
        True,
        "scoped_pearl_readiness_recursive_trace_scope_manifest_and_release_manifest_allow_pearl_veto_claim_step89",
    )


def _pearl_complete_claim_for_path(path: Dict[str, Any]) -> Tuple[str, bool, str]:
    if _causal_claim_class_for_path(path) != "causal_veto_authorized":
        return (
            PEARL_COMPLETE_VETO_CLASS_NOT_CAUSAL,
            False,
            "pearl_complete_veto_requires_causal_veto_authorized_top_path_first",
        )
    evidence = _as_mapping(path.get("pearl_veto_authority"))
    if not evidence:
        return (
            PEARL_COMPLETE_VETO_CLASS_BLOCKED,
            False,
            "missing_pearl_complete_authority_evidence_bundle",
        )
    missing = [str(v) for v in evidence.get("missing_required_flags", []) or []]
    if missing:
        return (
            PEARL_COMPLETE_VETO_CLASS_BLOCKED,
            False,
            "pearl_complete_veto_blocked_missing_" + "|".join(missing),
        )
    return (
        PEARL_COMPLETE_VETO_CLASS_AUTHORIZED,
        True,
        "global_full_id_step94_and_readiness_evidence_allow_pearl_complete_veto_claim_step95",
    )


def attach_causal_authority(paths: List[Dict[str, Any]], cards_path: str = "out/veto/causal_authority_cards.jsonl") -> List[Dict[str, Any]]:
    """Attach causal-authority metadata to activated runtime paths.

    This function intentionally does not change risk scores or veto decisions.
    It labels whether the path is authorized for a causal-veto claim by the
    offline PCMCI/SCM/estimation handoff, and it adds enforceable claim classes
    so downstream renderers cannot describe a veto as causal or Pearl-complete
    without explicit authority evidence.
    """
    cards = load_causal_authority_cards(cards_path)
    enriched: List[Dict[str, Any]] = []
    for path in paths or []:
        row = dict(path)
        path_id = str(row.get("path_id") or "").strip()
        card = cards.get(path_id)
        if card:
            row["causal_authority"] = {
                "authority_level": card.get("authority_level", ""),
                "runtime_use": card.get("runtime_use", ""),
                "authority_reason": card.get("authority_reason", ""),
                "contract_insight_id": card.get("contract_insight_id", ""),
                "contract_identification_status": card.get("contract_identification_status", ""),
                "contract_authority_level": card.get("contract_authority_level", ""),
                # Runtime-safe estimation summary. This is copied from the
                # precomputed authority card; the runtime does not read raw
                # effect_estimates.csv or sensitivity_analysis.csv directly.
                "estimation_evidence": card.get("estimation_evidence", {}),
            }
            row["causal_veto_authorized"] = card.get("runtime_use") in CAUSAL_VETO_ALLOWED_RUNTIME_USES
            row["pearl_veto_authority"] = _pearl_evidence_from_card(card)
            row["pearl_scoped_veto_authority"] = _pearl_scoped_evidence_from_card(card)
        else:
            row["causal_authority"] = {
                "authority_level": "not_available",
                "runtime_use": "policy_or_structural_veto_only",
                "authority_reason": "no_precomputed_causal_authority_card_for_path",
            }
            row["causal_veto_authorized"] = False
            row["pearl_veto_authority"] = _default_pearl_evidence()
            row["pearl_scoped_veto_authority"] = _default_pearl_scoped_evidence()

        claim_class = _causal_claim_class_for_path(row)
        row["veto_authority_class"] = claim_class
        row["causal_veto_claim_allowed"] = claim_class == "causal_veto_authorized"
        row["causal_veto_claim_reason"] = _causal_claim_reason_for_path(row, claim_class)
        pearl_class, pearl_allowed, pearl_reason = _pearl_complete_claim_for_path(row)
        row["pearl_veto_authority_class"] = pearl_class
        row["pearl_complete_veto_claim_allowed"] = bool(pearl_allowed)
        row["pearl_complete_veto_claim_reason"] = pearl_reason
        pearl_scoped_class, pearl_scoped_allowed, pearl_scoped_reason = _pearl_scoped_claim_for_path(row)
        row["pearl_scoped_veto_authority_class"] = pearl_scoped_class
        row["pearl_scoped_veto_claim_allowed"] = bool(pearl_scoped_allowed)
        row["pearl_scoped_veto_claim_reason"] = pearl_scoped_reason
        enriched.append(row)
    return enriched


def build_veto_authority_readiness(
    paths: List[Dict[str, Any]],
    decision: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Summarize whether a runtime veto may be described as causal/Pearl-complete.

    The matrix is an enforcement/readiness layer, not a decision layer: it does
    not flip PASS/REVIEW/HARD_BLOCK outcomes.  It makes the permitted wording
    explicit and blocks causal-veto or Pearl-complete-veto claims unless the top
    activated path carries the required precomputed authority evidence.
    """
    decision = dict(decision or {})
    path_rows = list(paths or [])
    class_counts: Dict[str, int] = {
        "policy_veto": 0,
        "structural_veto": 0,
        "causal_veto_authorized": 0,
        "causal_veto_not_authorized": 0,
    }
    pearl_class_counts: Dict[str, int] = {
        PEARL_COMPLETE_VETO_CLASS_AUTHORIZED: 0,
        PEARL_COMPLETE_VETO_CLASS_BLOCKED: 0,
        PEARL_COMPLETE_VETO_CLASS_NOT_CAUSAL: 0,
    }
    pearl_scoped_class_counts: Dict[str, int] = {
        PEARL_SCOPED_VETO_CLASS_AUTHORIZED: 0,
        PEARL_SCOPED_VETO_CLASS_BLOCKED: 0,
        PEARL_SCOPED_VETO_CLASS_NOT_CAUSAL: 0,
    }
    path_matrix: List[Dict[str, Any]] = []
    for path in path_rows:
        row = dict(path or {})
        claim_class = str(row.get("veto_authority_class") or _causal_claim_class_for_path(row))
        if claim_class not in class_counts:
            claim_class = "policy_veto"
        class_counts[claim_class] += 1
        if "pearl_veto_authority" not in row:
            row["pearl_veto_authority"] = _default_pearl_evidence("path_missing_pearl_complete_authority_bundle")
        if "pearl_scoped_veto_authority" not in row:
            row["pearl_scoped_veto_authority"] = _default_pearl_scoped_evidence("path_missing_scoped_pearl_authority_bundle")
        pearl_class, pearl_allowed, pearl_reason = _pearl_complete_claim_for_path(row)
        if pearl_class not in pearl_class_counts:
            pearl_class = PEARL_COMPLETE_VETO_CLASS_BLOCKED
        pearl_class_counts[pearl_class] += 1
        pearl_scoped_class, pearl_scoped_allowed, pearl_scoped_reason = _pearl_scoped_claim_for_path(row)
        if pearl_scoped_class not in pearl_scoped_class_counts:
            pearl_scoped_class = PEARL_SCOPED_VETO_CLASS_BLOCKED
        pearl_scoped_class_counts[pearl_scoped_class] += 1
        path_matrix.append({
            "path_id": row.get("path_id"),
            "veto_authority_class": claim_class,
            "causal_veto_claim_allowed": claim_class == "causal_veto_authorized",
            "causal_veto_claim_reason": row.get("causal_veto_claim_reason") or _causal_claim_reason_for_path(row, claim_class),
            "runtime_use": (row.get("causal_authority") or {}).get("runtime_use") if isinstance(row.get("causal_authority"), dict) else "",
            "authority_level": (row.get("causal_authority") or {}).get("authority_level") if isinstance(row.get("causal_authority"), dict) else "",
            "pearl_veto_authority_class": pearl_class,
            "pearl_complete_veto_claim_allowed": bool(pearl_allowed),
            "pearl_complete_veto_claim_reason": pearl_reason,
            "pearl_veto_authority": row.get("pearl_veto_authority"),
            "pearl_scoped_veto_authority_class": pearl_scoped_class,
            "pearl_scoped_veto_claim_allowed": bool(pearl_scoped_allowed),
            "pearl_scoped_veto_claim_reason": pearl_scoped_reason,
            "pearl_scoped_veto_authority": row.get("pearl_scoped_veto_authority"),
        })

    top = path_matrix[0] if path_matrix else None
    decision_name = str(decision.get("decision") or "PASS")
    veto_like = decision_name in VETO_LIKE_DECISIONS
    top_class = str((top or {}).get("veto_authority_class") or ("policy_veto" if veto_like else "none"))
    claim_allowed = bool(veto_like and top_class == "causal_veto_authorized")
    blocked = bool(veto_like and not claim_allowed)
    if not veto_like:
        reason = "decision_is_not_a_veto_or_review_gate"
    elif top is None:
        reason = "veto_like_decision_has_no_path_authority_card_and_must_remain_policy_or_invariant_veto"
    else:
        reason = str(top.get("causal_veto_claim_reason") or "top_path_lacks_explicit_causal_veto_authority")

    top_pearl_class = str((top or {}).get("pearl_veto_authority_class") or (PEARL_COMPLETE_VETO_CLASS_NOT_CAUSAL if veto_like else "none"))
    pearl_allowed = bool(veto_like and top_pearl_class == PEARL_COMPLETE_VETO_CLASS_AUTHORIZED)
    pearl_blocked = bool(veto_like and not pearl_allowed)
    if not veto_like:
        pearl_reason = "decision_is_not_a_veto_or_review_gate"
    elif top is None:
        pearl_reason = "veto_like_decision_has_no_path_and_no_pearl_complete_authority_bundle"
    else:
        pearl_reason = str(top.get("pearl_complete_veto_claim_reason") or "top_path_lacks_pearl_complete_authority")

    global_attestation: Dict[str, Any] = {}
    global_attestation_verification = {
        "global_pearl_veto_attestation_present": 0,
        "global_pearl_veto_attestation_verified": 0,
        "global_pearl_veto_attestation_reason": "pearl_complete_veto_claim_not_allowed_no_attestation_emitted_step96",
    }
    if pearl_allowed:
        readiness_for_global_attestation = {
            "decision": decision_name,
            "veto_like_decision": veto_like,
            "top_path_id": (top or {}).get("path_id"),
            "top_veto_authority_class": top_class,
            "top_pearl_veto_authority_class": top_pearl_class,
            "pearl_complete_veto_claim_allowed": pearl_allowed,
            "pearl_complete_veto_claim_reason": pearl_reason,
            "pearl_readiness_matrix": PEARL_COMPLETE_VETO_READINESS_MATRIX,
        }
        top_source = next((p for p in path_rows if p.get("path_id") == (top or {}).get("path_id")), {}) if top else {}
        global_attestation = build_global_pearl_veto_attestation(readiness_for_global_attestation, top_source)
        global_attestation_verification = verify_global_pearl_veto_attestation_against_context(
            global_attestation,
            readiness=readiness_for_global_attestation,
            top_path=top_source,
        )
        if not bool(global_attestation_verification.get("global_pearl_veto_attestation_verified")):
            pearl_allowed = False
            pearl_blocked = bool(veto_like)
            pearl_reason = str(global_attestation_verification.get("global_pearl_veto_attestation_reason") or "global_pearl_runtime_attestation_blocked_step96")

    top_pearl_scoped_class = str((top or {}).get("pearl_scoped_veto_authority_class") or (PEARL_SCOPED_VETO_CLASS_NOT_CAUSAL if veto_like else "none"))
    pearl_scoped_allowed = bool(veto_like and top_pearl_scoped_class == PEARL_SCOPED_VETO_CLASS_AUTHORIZED)
    pearl_scoped_blocked = bool(veto_like and not pearl_scoped_allowed)
    if not veto_like:
        pearl_scoped_reason = "decision_is_not_a_veto_or_review_gate"
    elif top is None:
        pearl_scoped_reason = "veto_like_decision_has_no_path_and_no_scoped_pearl_authority_bundle"
    else:
        pearl_scoped_reason = str(top.get("pearl_scoped_veto_claim_reason") or "top_path_lacks_scoped_pearl_authority")

    attestation: Dict[str, Any] = {}
    attestation_verification = {
        "scoped_pearl_veto_attestation_present": 0,
        "scoped_pearl_veto_attestation_verified": 0,
        "scoped_pearl_veto_attestation_reason": "scoped_pearl_veto_claim_not_allowed_no_attestation_emitted_step90",
    }
    if pearl_scoped_allowed:
        readiness_for_attestation = {
            "decision": decision_name,
            "veto_like_decision": veto_like,
            "top_path_id": (top or {}).get("path_id"),
            "top_veto_authority_class": top_class,
            "top_pearl_scoped_veto_authority_class": top_pearl_scoped_class,
            "pearl_scoped_veto_claim_allowed": pearl_scoped_allowed,
            "pearl_scoped_veto_claim_reason": pearl_scoped_reason,
            "pearl_scoped_readiness_matrix": PEARL_SCOPED_VETO_READINESS_MATRIX,
        }
        top_source = next((p for p in path_rows if p.get("path_id") == (top or {}).get("path_id")), {}) if top else {}
        attestation = build_scoped_pearl_veto_attestation(readiness_for_attestation, top_source)
        attestation_verification = verify_scoped_pearl_veto_attestation(attestation)
        if not bool(attestation_verification.get("scoped_pearl_veto_attestation_verified")):
            pearl_scoped_allowed = False
            pearl_scoped_blocked = bool(veto_like)
            pearl_scoped_reason = str(attestation_verification.get("scoped_pearl_veto_attestation_reason") or "scoped_pearl_runtime_attestation_blocked_step90")

    return {
        "readiness_matrix": "veto_causal_authority_enforcement_readiness_v1_step77",
        "readiness_matrices": [
            "veto_causal_authority_enforcement_readiness_v1_step77",
            PEARL_COMPLETE_VETO_READINESS_MATRIX,
            PEARL_GLOBAL_VETO_ATTESTATION_VERSION,
            "veto_pearl_global_no_overclaim_adversarial_suite_v1_step96",
            PEARL_SCOPED_VETO_READINESS_MATRIX,
            PEARL_SCOPED_VETO_ATTESTATION_VERSION,
        ],
        "pearl_readiness_matrix": PEARL_COMPLETE_VETO_READINESS_MATRIX,
        "pearl_scoped_readiness_matrix": PEARL_SCOPED_VETO_READINESS_MATRIX,
        "claim_guard": "no_causal_veto_claim_without_explicit_authority_card",
        "pearl_complete_claim_guard": "no_pearl_complete_veto_claim_without_full_id_readiness_and_full_recursive_id_evidence",
        "pearl_complete_formula_authority_guard": "no_pearl_complete_veto_claim_without_full_recursive_id_formula_authority",
        "pearl_complete_promotion_gate_guard": "no_pearl_complete_veto_claim_without_step82_full_id_promotion_gate_and_step94_controlled_global_full_id_flip",
        "pearl_complete_attestation_guard": "no_pearl_complete_veto_claim_without_digest_bound_context_verified_runtime_attestation_for_top_path_decision_and_step94_global_full_id_release_step96",
        "pearl_scoped_claim_guard": "no_scoped_pearl_veto_claim_without_step87_gate_step86_trace_authority_step88_scope_manifest_step89_release_manifest_and_step90_runtime_attestation",
        "pearl_scoped_attestation_guard": "no_scoped_pearl_veto_claim_without_digest_bound_runtime_attestation_for_top_path_and_decision",
        "enforcement_enabled": True,
        "pearl_complete_enforcement_enabled": True,
        "pearl_scoped_enforcement_enabled": True,
        "decision": decision_name,
        "veto_like_decision": veto_like,
        "activated_path_count": len(path_rows),
        "class_counts": class_counts,
        "pearl_class_counts": pearl_class_counts,
        "pearl_scoped_class_counts": pearl_scoped_class_counts,
        "path_matrix": path_matrix,
        "top_path_id": (top or {}).get("path_id"),
        "top_veto_authority_class": top_class,
        "top_pearl_veto_authority_class": top_pearl_class,
        "top_pearl_scoped_veto_authority_class": top_pearl_scoped_class,
        "causal_veto_claim_allowed": claim_allowed,
        "causal_veto_claim_blocked": blocked,
        "causal_veto_claim_reason": reason,
        "pearl_complete_veto_claim_allowed": pearl_allowed,
        "pearl_complete_veto_claim_blocked": pearl_blocked,
        "pearl_complete_veto_claim_reason": pearl_reason,
        "pearl_complete_veto_attestation": global_attestation,
        "pearl_complete_veto_attestation_verified": bool(global_attestation_verification.get("global_pearl_veto_attestation_verified")),
        "pearl_complete_veto_attestation_digest": global_attestation.get("attestation_digest", "") if global_attestation else "",
        "pearl_complete_veto_attestation_verification": global_attestation_verification,
        "pearl_scoped_veto_claim_allowed": pearl_scoped_allowed,
        "pearl_scoped_veto_claim_blocked": pearl_scoped_blocked,
        "pearl_scoped_veto_claim_reason": pearl_scoped_reason,
        "pearl_scoped_veto_attestation": attestation,
        "pearl_scoped_veto_attestation_verified": bool(attestation_verification.get("scoped_pearl_veto_attestation_verified")),
        "pearl_scoped_veto_attestation_digest": attestation.get("attestation_digest", "") if attestation else "",
        "pearl_scoped_veto_attestation_verification": attestation_verification,
        "allowed_runtime_uses": sorted(CAUSAL_VETO_ALLOWED_RUNTIME_USES),
        "pearl_complete_required_flags": list(PEARL_COMPLETE_VETO_REQUIRED_FLAGS) + list(PEARL_COMPLETE_VETO_REQUIRED_DERIVED_FLAGS),
        "pearl_complete_allowed_formula_authorities": sorted(PEARL_COMPLETE_FORMULA_AUTHORITIES),
        "pearl_complete_required_attestation_version": PEARL_GLOBAL_VETO_ATTESTATION_VERSION,
        "pearl_scoped_required_flags": list(PEARL_SCOPED_VETO_REQUIRED_FLAGS) + list(PEARL_SCOPED_VETO_REQUIRED_DERIVED_FLAGS),
        "pearl_scoped_allowed_formula_authorities": sorted(PEARL_SCOPED_FORMULA_AUTHORITIES),
        "pearl_scoped_required_manifest_version": PEARL_SCOPED_SCOPE_MANIFEST_VERSION,
        "pearl_scoped_required_release_manifest_version": PEARL_SCOPED_RELEASE_MANIFEST_VERSION,
        "pearl_scoped_required_attestation_version": PEARL_SCOPED_VETO_ATTESTATION_VERSION,
    }


def assert_causal_veto_claim_allowed(paths: List[Dict[str, Any]], decision: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Return the readiness matrix or raise when a causal-veto claim is unsafe."""
    readiness = build_veto_authority_readiness(paths, decision=decision)
    if not readiness.get("causal_veto_claim_allowed", False):
        raise ValueError(str(readiness.get("causal_veto_claim_reason") or "causal_veto_claim_not_authorized"))
    return readiness


def assert_pearl_complete_veto_claim_allowed(paths: List[Dict[str, Any]], decision: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Return readiness or raise when Pearl-complete veto wording is unsafe."""
    readiness = build_veto_authority_readiness(paths, decision=decision)
    if not readiness.get("pearl_complete_veto_claim_allowed", False):
        raise ValueError(str(readiness.get("pearl_complete_veto_claim_reason") or "pearl_complete_veto_claim_not_authorized"))
    return readiness


def assert_pearl_scoped_veto_claim_allowed(paths: List[Dict[str, Any]], decision: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Return readiness or raise when scoped Pearl-veto wording is unsafe."""
    readiness = build_veto_authority_readiness(paths, decision=decision)
    if not readiness.get("pearl_scoped_veto_claim_allowed", False):
        raise ValueError(str(readiness.get("pearl_scoped_veto_claim_reason") or "pearl_scoped_veto_claim_not_authorized"))
    return readiness


__all__ = [
    "CAUSAL_VETO_ALLOWED_RUNTIME_USES",
    "PEARL_COMPLETE_VETO_READINESS_MATRIX",
    "PEARL_COMPLETE_VETO_REQUIRED_FLAGS",
    "PEARL_COMPLETE_VETO_REQUIRED_DERIVED_FLAGS",
    "PEARL_COMPLETE_FORMULA_AUTHORITIES",
    "PEARL_GLOBAL_VETO_ATTESTATION_VERSION",
    "PEARL_SCOPED_VETO_READINESS_MATRIX",
    "PEARL_SCOPED_VETO_REQUIRED_FLAGS",
    "PEARL_SCOPED_VETO_REQUIRED_DERIVED_FLAGS",
    "PEARL_SCOPED_FORMULA_AUTHORITIES",
    "PEARL_SCOPED_SCOPE_MANIFEST_VERSION",
    "PEARL_SCOPED_RELEASE_MANIFEST_VERSION",
    "PEARL_SCOPED_VETO_ATTESTATION_VERSION",
    "load_causal_authority_cards",
    "attach_causal_authority",
    "build_veto_authority_readiness",
    "assert_causal_veto_claim_allowed",
    "assert_pearl_complete_veto_claim_allowed",
    "assert_pearl_scoped_veto_claim_allowed",
]
