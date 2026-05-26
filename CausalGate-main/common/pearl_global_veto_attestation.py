from __future__ import annotations

"""Step 96 runtime attestation helpers for global Pearl-complete veto claims.

Step 94 flips the backend Global Full-ID claim only after the Step-93 dry-run and
live promotion gate are green.  Step 95 binds that global release evidence to a
runtime veto-like decision.  Step 96 hardens the envelope with no-overclaim
checks: required release/matrix versions are exact, and a contextual verifier can
compare an attestation back to the runtime decision/top path that produced it.
"""

import hashlib
import json
from typing import Dict, Mapping

PEARL_GLOBAL_VETO_ATTESTATION_VERSION = "veto_pearl_global_runtime_attestation_v2_step96"
PEARL_GLOBAL_VETO_ATTESTATION_LEVEL = (
    "runtime_bound_global_pearl_complete_veto_attestation_requires_step94_"
    "controlled_global_full_id_flip_and_live_full_id_promotion_gate"
)
PEARL_GLOBAL_VETO_ATTESTATION_DIGEST_ALGORITHM = "sha256"
PEARL_GLOBAL_VETO_ATTESTATION_SCOPE = "runtime_bound_global_pearl_complete_veto_claim_step96"

# Step 96: a valid global Pearl veto attestation must be bound to the
# currently released backend/matrix versions, not merely to non-empty strings.
PEARL_GLOBAL_REQUIRED_READINESS_MATRIX = "id_full_readiness_matrix_v11_step80"
PEARL_GLOBAL_REQUIRED_ORACLE_PARITY_MATRIX = "id_oracle_parity_matrix_v3_step80"
PEARL_GLOBAL_REQUIRED_PROMOTION_GATE = "id_full_promotion_gate_v7_step94"
PEARL_GLOBAL_REQUIRED_CONTROLLED_FLIP = "id_global_full_id_controlled_flip_v1_step94"
PEARL_GLOBAL_REQUIRED_READINESS_MATRIX_VERSION = "veto_pearl_complete_authority_readiness_v5_step96"

PEARL_GLOBAL_ALLOWED_FORMULA_AUTHORITIES = {
    "full_recursive_id_canonical_formula_authority",
    "full_recursive_id_formula_authority",
    "shpitser_pearl_full_recursive_id_authority",
}

PEARL_GLOBAL_VETO_ATTESTATION_BINDING_FIELDS = (
    "attestation_version",
    "attestation_scope",
    "decision",
    "veto_like_decision",
    "top_path_id",
    "top_veto_authority_class",
    "top_pearl_veto_authority_class",
    "pearl_complete_veto_claim_allowed",
    "pearl_complete_veto_claim_reason",
    "pearl_complete_readiness_matrix",
    "full_recursive_id_implemented",
    "full_id_claim_allowed",
    "id_full_readiness_matrix",
    "id_full_readiness_matrix_passed",
    "id_oracle_parity_matrix",
    "id_oracle_parity_fuzz_passed",
    "formal_failure_certificate_coverage_complete",
    "id_full_promotion_gate",
    "id_full_promotion_gate_passed",
    "id_global_full_id_controlled_flip",
    "id_global_full_id_controlled_flip_passed",
    "global_full_id_controlled_flip_allowed",
    "primary_formula_authority",
    "runtime_use",
    "authority_level",
)


def _stable_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "pass", "passed", "complete", "green"}


def _as_mapping(value: object) -> Dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _attestation_payload(attestation: Mapping[str, object]) -> Dict[str, object]:
    return {key: attestation.get(key) for key in PEARL_GLOBAL_VETO_ATTESTATION_BINDING_FIELDS}


def global_pearl_veto_attestation_digest(attestation: Mapping[str, object]) -> str:
    return _sha256_text(_stable_json(_attestation_payload(attestation)))


def build_global_pearl_veto_attestation(
    readiness: Mapping[str, object],
    top_path: Mapping[str, object] | None,
) -> Dict[str, object]:
    """Build a digest-bound attestation for a Global Pearl-complete runtime veto."""
    top = dict(top_path or {})
    authority = _as_mapping(top.get("pearl_veto_authority"))
    causal_authority = _as_mapping(top.get("causal_authority"))
    attestation: Dict[str, object] = {
        "attestation_version": PEARL_GLOBAL_VETO_ATTESTATION_VERSION,
        "attestation_level": PEARL_GLOBAL_VETO_ATTESTATION_LEVEL,
        "attestation_scope": PEARL_GLOBAL_VETO_ATTESTATION_SCOPE,
        "digest_algorithm": PEARL_GLOBAL_VETO_ATTESTATION_DIGEST_ALGORITHM,
        "decision": str(readiness.get("decision") or ""),
        "veto_like_decision": int(_truthy(readiness.get("veto_like_decision"))),
        "top_path_id": str(readiness.get("top_path_id") or top.get("path_id") or ""),
        "top_veto_authority_class": str(readiness.get("top_veto_authority_class") or top.get("veto_authority_class") or ""),
        "top_pearl_veto_authority_class": str(readiness.get("top_pearl_veto_authority_class") or top.get("pearl_veto_authority_class") or ""),
        "pearl_complete_veto_claim_allowed": int(_truthy(readiness.get("pearl_complete_veto_claim_allowed"))),
        "pearl_complete_veto_claim_reason": str(readiness.get("pearl_complete_veto_claim_reason") or top.get("pearl_complete_veto_claim_reason") or ""),
        "pearl_complete_readiness_matrix": str(readiness.get("pearl_readiness_matrix") or ""),
        "full_recursive_id_implemented": int(_truthy(authority.get("full_recursive_id_implemented"))),
        "full_id_claim_allowed": int(_truthy(authority.get("full_id_claim_allowed"))),
        "id_full_readiness_matrix": str(authority.get("id_full_readiness_matrix") or ""),
        "id_full_readiness_matrix_passed": int(_truthy(authority.get("id_full_readiness_matrix_passed"))),
        "id_oracle_parity_matrix": str(authority.get("id_oracle_parity_matrix") or ""),
        "id_oracle_parity_fuzz_passed": int(_truthy(authority.get("id_oracle_parity_fuzz_passed"))),
        "formal_failure_certificate_coverage_complete": int(_truthy(authority.get("formal_failure_certificate_coverage_complete"))),
        "id_full_promotion_gate": str(authority.get("id_full_promotion_gate") or ""),
        "id_full_promotion_gate_passed": int(_truthy(authority.get("id_full_promotion_gate_passed"))),
        "id_global_full_id_controlled_flip": str(authority.get("id_global_full_id_controlled_flip") or ""),
        "id_global_full_id_controlled_flip_passed": int(_truthy(authority.get("id_global_full_id_controlled_flip_passed"))),
        "global_full_id_controlled_flip_allowed": int(_truthy(authority.get("global_full_id_controlled_flip_allowed"))),
        "primary_formula_authority": str(authority.get("primary_formula_authority") or ""),
        "runtime_use": str(causal_authority.get("runtime_use") or ""),
        "authority_level": str(causal_authority.get("authority_level") or ""),
        "binding_fields": list(PEARL_GLOBAL_VETO_ATTESTATION_BINDING_FIELDS),
    }
    attestation["attestation_digest"] = global_pearl_veto_attestation_digest(attestation)
    return attestation


def verify_global_pearl_veto_attestation(raw: object) -> Dict[str, object]:
    if isinstance(raw, Mapping):
        attestation = dict(raw)
    elif isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except Exception:
            attestation = {}
        else:
            attestation = dict(parsed) if isinstance(parsed, Mapping) else {}
    else:
        attestation = {}

    if not attestation:
        return {
            "global_pearl_veto_attestation_present": 0,
            "global_pearl_veto_attestation_verified": 0,
            "global_pearl_veto_attestation_version": "",
            "global_pearl_veto_attestation_digest": "",
            "global_pearl_veto_attestation_digest_valid": 0,
            "global_pearl_veto_attestation_missing_fields": "attestation",
            "global_pearl_veto_attestation_mismatched_fields": "",
            "global_pearl_veto_attestation_reason": "missing_global_pearl_runtime_attestation_step96",
        }

    missing = []
    mismatched = []
    for field in PEARL_GLOBAL_VETO_ATTESTATION_BINDING_FIELDS:
        if field not in attestation:
            missing.append(field)

    expected_static = {
        "attestation_version": PEARL_GLOBAL_VETO_ATTESTATION_VERSION,
        "attestation_scope": PEARL_GLOBAL_VETO_ATTESTATION_SCOPE,
        "pearl_complete_veto_claim_allowed": 1,
        "veto_like_decision": 1,
        "top_veto_authority_class": "causal_veto_authorized",
        "top_pearl_veto_authority_class": "pearl_complete_veto_authorized",
        "full_recursive_id_implemented": 1,
        "full_id_claim_allowed": 1,
        "id_full_readiness_matrix_passed": 1,
        "id_oracle_parity_fuzz_passed": 1,
        "formal_failure_certificate_coverage_complete": 1,
        "id_full_promotion_gate_passed": 1,
        "id_global_full_id_controlled_flip_passed": 1,
        "global_full_id_controlled_flip_allowed": 1,
        "id_full_readiness_matrix": PEARL_GLOBAL_REQUIRED_READINESS_MATRIX,
        "id_oracle_parity_matrix": PEARL_GLOBAL_REQUIRED_ORACLE_PARITY_MATRIX,
        "id_full_promotion_gate": PEARL_GLOBAL_REQUIRED_PROMOTION_GATE,
        "id_global_full_id_controlled_flip": PEARL_GLOBAL_REQUIRED_CONTROLLED_FLIP,
        "pearl_complete_readiness_matrix": PEARL_GLOBAL_REQUIRED_READINESS_MATRIX_VERSION,
    }
    for field, expected in expected_static.items():
        if field in attestation and str(attestation.get(field)) != str(expected):
            mismatched.append(field)

    if str(attestation.get("decision") or "") not in {"HARD_BLOCK", "REVIEW"}:
        mismatched.append("decision")
    if str(attestation.get("primary_formula_authority") or "") not in PEARL_GLOBAL_ALLOWED_FORMULA_AUTHORITIES:
        mismatched.append("primary_formula_authority")
    if not str(attestation.get("top_path_id") or ""):
        mismatched.append("top_path_id")

    observed_digest = str(attestation.get("attestation_digest") or "")
    expected_digest = global_pearl_veto_attestation_digest(attestation)
    digest_valid = int(bool(observed_digest) and observed_digest == expected_digest)
    if not digest_valid:
        mismatched.append("attestation_digest")

    missing = list(dict.fromkeys(missing))
    mismatched = list(dict.fromkeys(mismatched))
    verified = int(not missing and not mismatched)
    reason = "global_pearl_runtime_attestation_verified_step96" if verified else "global_pearl_runtime_attestation_blocked_step96"
    return {
        "global_pearl_veto_attestation_present": 1,
        "global_pearl_veto_attestation_verified": verified,
        "global_pearl_veto_attestation_version": str(attestation.get("attestation_version") or ""),
        "global_pearl_veto_attestation_digest": observed_digest,
        "global_pearl_veto_attestation_expected_digest": expected_digest,
        "global_pearl_veto_attestation_digest_algorithm": PEARL_GLOBAL_VETO_ATTESTATION_DIGEST_ALGORITHM,
        "global_pearl_veto_attestation_digest_valid": digest_valid,
        "global_pearl_veto_attestation_missing_fields": "|".join(missing),
        "global_pearl_veto_attestation_mismatched_fields": "|".join(mismatched),
        "global_pearl_veto_attestation_reason": reason,
    }


def verify_global_pearl_veto_attestation_against_context(
    raw: object,
    *,
    readiness: Mapping[str, object],
    top_path: Mapping[str, object] | None,
) -> Dict[str, object]:
    """Verify a Global Pearl attestation against the runtime context that emitted it.

    ``verify_global_pearl_veto_attestation`` proves the envelope is internally
    valid.  This contextual verifier additionally proves that the envelope still
    matches the current runtime decision and top path.  It prevents a rehashed
    attestation for another path or decision from being replayed as if it came
    from the current veto.
    """
    base = verify_global_pearl_veto_attestation(raw)
    if isinstance(raw, Mapping):
        attestation = dict(raw)
    elif isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except Exception:
            attestation = {}
        else:
            attestation = dict(parsed) if isinstance(parsed, Mapping) else {}
    else:
        attestation = {}

    expected = build_global_pearl_veto_attestation(readiness, top_path)
    context_mismatches = []
    for field in PEARL_GLOBAL_VETO_ATTESTATION_BINDING_FIELDS:
        if str(attestation.get(field, "")) != str(expected.get(field, "")):
            context_mismatches.append(field)
    if str(attestation.get("attestation_digest") or "") != str(expected.get("attestation_digest") or ""):
        context_mismatches.append("attestation_digest")
    context_mismatches = list(dict.fromkeys(context_mismatches))
    context_verified = int(bool(base.get("global_pearl_veto_attestation_verified")) and not context_mismatches)
    payload = dict(base)
    payload.update({
        "global_pearl_veto_attestation_context_verified": context_verified,
        "global_pearl_veto_attestation_context_mismatched_fields": "|".join(context_mismatches),
        "global_pearl_veto_attestation_context_expected_digest": expected.get("attestation_digest", ""),
        "global_pearl_veto_attestation_context_reason": (
            "global_pearl_runtime_attestation_context_verified_step96"
            if context_verified else
            "global_pearl_runtime_attestation_context_blocked_step96"
        ),
    })
    return payload


__all__ = [
    "PEARL_GLOBAL_VETO_ATTESTATION_VERSION",
    "PEARL_GLOBAL_VETO_ATTESTATION_LEVEL",
    "PEARL_GLOBAL_VETO_ATTESTATION_SCOPE",
    "PEARL_GLOBAL_VETO_ATTESTATION_DIGEST_ALGORITHM",
    "PEARL_GLOBAL_ALLOWED_FORMULA_AUTHORITIES",
    "PEARL_GLOBAL_REQUIRED_READINESS_MATRIX",
    "PEARL_GLOBAL_REQUIRED_ORACLE_PARITY_MATRIX",
    "PEARL_GLOBAL_REQUIRED_PROMOTION_GATE",
    "PEARL_GLOBAL_REQUIRED_CONTROLLED_FLIP",
    "PEARL_GLOBAL_REQUIRED_READINESS_MATRIX_VERSION",
    "PEARL_GLOBAL_VETO_ATTESTATION_BINDING_FIELDS",
    "global_pearl_veto_attestation_digest",
    "build_global_pearl_veto_attestation",
    "verify_global_pearl_veto_attestation",
    "verify_global_pearl_veto_attestation_against_context",
]
