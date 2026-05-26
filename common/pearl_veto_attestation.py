from __future__ import annotations

"""Step 90 runtime attestation helpers for scoped Pearl veto claims.

Step 88 binds the scoped Pearl evidence bundle to an audited public-surface
manifest.  Step 89 binds that manifest to the release/code surface.  Step 90
binds the *runtime wording decision* to both manifests: a renderer or downstream
agent gets a compact, digest-checked envelope that says exactly which veto-like
decision, top path, authority class, manifest digest and release digest allowed
scoped Pearl wording.

This layer intentionally does not authorize global Pearl-complete claims.  It is
a runtime attestation for the already-scoped Step 87/88/89 claim only.
"""

import hashlib
import json
from typing import Dict, Mapping

PEARL_SCOPED_VETO_ATTESTATION_VERSION = "veto_pearl_scoped_runtime_attestation_v1_step90"
PEARL_SCOPED_VETO_ATTESTATION_LEVEL = (
    "runtime_bound_scoped_pearl_veto_attestation_for_step87_step88_step89_"
    "with_step94_global_full_id_claim_bound"
)
PEARL_SCOPED_VETO_ATTESTATION_DIGEST_ALGORITHM = "sha256"
PEARL_SCOPED_VETO_ATTESTATION_SCOPE = "runtime_bound_scoped_pearl_veto_claim_step90"

PEARL_SCOPED_VETO_ATTESTATION_BINDING_FIELDS = (
    "attestation_version",
    "attestation_scope",
    "decision",
    "veto_like_decision",
    "top_path_id",
    "top_veto_authority_class",
    "top_pearl_scoped_veto_authority_class",
    "pearl_scoped_veto_claim_allowed",
    "pearl_scoped_veto_claim_reason",
    "pearl_scoped_readiness_matrix",
    "scoped_pearl_manifest_version",
    "scoped_pearl_manifest_digest",
    "scoped_pearl_release_manifest_version",
    "scoped_pearl_release_manifest_digest",
    "primary_formula_authority",
    "id_full_readiness_matrix",
    "id_oracle_parity_matrix",
    "formal_failure_certificate_coverage_complete",
    "id_scoped_pearl_promotion_gate",
    "global_full_recursive_id_implemented",
    "global_full_id_claim_allowed",
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
    return {key: attestation.get(key) for key in PEARL_SCOPED_VETO_ATTESTATION_BINDING_FIELDS}


def scoped_pearl_veto_attestation_digest(attestation: Mapping[str, object]) -> str:
    return _sha256_text(_stable_json(_attestation_payload(attestation)))


def build_scoped_pearl_veto_attestation(
    readiness: Mapping[str, object],
    top_path: Mapping[str, object] | None,
) -> Dict[str, object]:
    """Build a digest-bound attestation for a scoped Pearl runtime veto claim.

    The attestation is intentionally derived from runtime readiness and the top
    activated path.  It does not trust a precomputed boolean carried in the card.
    """
    top = dict(top_path or {})
    authority = _as_mapping(top.get("pearl_scoped_veto_authority"))
    causal_authority = _as_mapping(top.get("causal_authority"))
    attestation: Dict[str, object] = {
        "attestation_version": PEARL_SCOPED_VETO_ATTESTATION_VERSION,
        "attestation_level": PEARL_SCOPED_VETO_ATTESTATION_LEVEL,
        "attestation_scope": PEARL_SCOPED_VETO_ATTESTATION_SCOPE,
        "digest_algorithm": PEARL_SCOPED_VETO_ATTESTATION_DIGEST_ALGORITHM,
        "decision": str(readiness.get("decision") or ""),
        "veto_like_decision": int(_truthy(readiness.get("veto_like_decision"))),
        "top_path_id": str(readiness.get("top_path_id") or top.get("path_id") or ""),
        "top_veto_authority_class": str(readiness.get("top_veto_authority_class") or top.get("veto_authority_class") or ""),
        "top_pearl_scoped_veto_authority_class": str(
            readiness.get("top_pearl_scoped_veto_authority_class") or top.get("pearl_scoped_veto_authority_class") or ""
        ),
        "pearl_scoped_veto_claim_allowed": int(_truthy(readiness.get("pearl_scoped_veto_claim_allowed"))),
        "pearl_scoped_veto_claim_reason": str(readiness.get("pearl_scoped_veto_claim_reason") or top.get("pearl_scoped_veto_claim_reason") or ""),
        "pearl_scoped_readiness_matrix": str(readiness.get("pearl_scoped_readiness_matrix") or ""),
        "scoped_pearl_manifest_version": str(authority.get("scoped_pearl_manifest_version") or ""),
        "scoped_pearl_manifest_digest": str(authority.get("scoped_pearl_manifest_digest") or ""),
        "scoped_pearl_release_manifest_version": str(authority.get("scoped_pearl_release_manifest_version") or ""),
        "scoped_pearl_release_manifest_digest": str(authority.get("scoped_pearl_release_manifest_digest") or ""),
        "primary_formula_authority": str(authority.get("primary_formula_authority") or ""),
        "id_full_readiness_matrix": str(authority.get("id_full_readiness_matrix") or ""),
        "id_oracle_parity_matrix": str(authority.get("id_oracle_parity_matrix") or ""),
        "formal_failure_certificate_coverage_complete": int(_truthy(authority.get("formal_failure_certificate_coverage_complete"))),
        "id_scoped_pearl_promotion_gate": str(authority.get("id_scoped_pearl_promotion_gate") or ""),
        "global_full_recursive_id_implemented": int(_truthy(authority.get("global_full_recursive_id_implemented"))),
        "global_full_id_claim_allowed": int(_truthy(authority.get("global_full_id_claim_allowed"))),
        "runtime_use": str(causal_authority.get("runtime_use") or ""),
        "authority_level": str(causal_authority.get("authority_level") or ""),
        "binding_fields": list(PEARL_SCOPED_VETO_ATTESTATION_BINDING_FIELDS),
    }
    attestation["attestation_digest"] = scoped_pearl_veto_attestation_digest(attestation)
    return attestation


def verify_scoped_pearl_veto_attestation(raw: object) -> Dict[str, object]:
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
            "scoped_pearl_veto_attestation_present": 0,
            "scoped_pearl_veto_attestation_verified": 0,
            "scoped_pearl_veto_attestation_version": "",
            "scoped_pearl_veto_attestation_digest": "",
            "scoped_pearl_veto_attestation_digest_valid": 0,
            "scoped_pearl_veto_attestation_missing_fields": "attestation",
            "scoped_pearl_veto_attestation_mismatched_fields": "",
            "scoped_pearl_veto_attestation_reason": "missing_scoped_pearl_runtime_attestation_step90",
        }

    missing = []
    mismatched = []
    for field in PEARL_SCOPED_VETO_ATTESTATION_BINDING_FIELDS:
        if field not in attestation:
            missing.append(field)

    expected_static = {
        "attestation_version": PEARL_SCOPED_VETO_ATTESTATION_VERSION,
        "attestation_scope": PEARL_SCOPED_VETO_ATTESTATION_SCOPE,
        "pearl_scoped_veto_claim_allowed": 1,
        "veto_like_decision": 1,
        "top_veto_authority_class": "causal_veto_authorized",
        "top_pearl_scoped_veto_authority_class": "pearl_scoped_veto_authorized",
        "formal_failure_certificate_coverage_complete": 1,
        "global_full_recursive_id_implemented": 1,
        "global_full_id_claim_allowed": 1,
    }
    for field, expected in expected_static.items():
        if field in attestation and str(attestation.get(field)) != str(expected):
            mismatched.append(field)

    if str(attestation.get("decision") or "") not in {"HARD_BLOCK", "REVIEW"}:
        mismatched.append("decision")
    if not str(attestation.get("scoped_pearl_manifest_digest") or ""):
        mismatched.append("scoped_pearl_manifest_digest")
    if not str(attestation.get("scoped_pearl_release_manifest_digest") or ""):
        mismatched.append("scoped_pearl_release_manifest_digest")
    if not str(attestation.get("primary_formula_authority") or ""):
        mismatched.append("primary_formula_authority")

    observed_digest = str(attestation.get("attestation_digest") or "")
    expected_digest = scoped_pearl_veto_attestation_digest(attestation)
    digest_valid = int(bool(observed_digest) and observed_digest == expected_digest)
    if not digest_valid:
        mismatched.append("attestation_digest")

    missing = list(dict.fromkeys(missing))
    mismatched = list(dict.fromkeys(mismatched))
    verified = int(not missing and not mismatched)
    reason = "scoped_pearl_runtime_attestation_verified_step90" if verified else "scoped_pearl_runtime_attestation_blocked_step90"
    return {
        "scoped_pearl_veto_attestation_present": 1,
        "scoped_pearl_veto_attestation_verified": verified,
        "scoped_pearl_veto_attestation_version": str(attestation.get("attestation_version") or ""),
        "scoped_pearl_veto_attestation_digest": observed_digest,
        "scoped_pearl_veto_attestation_expected_digest": expected_digest,
        "scoped_pearl_veto_attestation_digest_algorithm": PEARL_SCOPED_VETO_ATTESTATION_DIGEST_ALGORITHM,
        "scoped_pearl_veto_attestation_digest_valid": digest_valid,
        "scoped_pearl_veto_attestation_missing_fields": "|".join(missing),
        "scoped_pearl_veto_attestation_mismatched_fields": "|".join(mismatched),
        "scoped_pearl_veto_attestation_reason": reason,
    }


__all__ = [
    "PEARL_SCOPED_VETO_ATTESTATION_VERSION",
    "PEARL_SCOPED_VETO_ATTESTATION_LEVEL",
    "PEARL_SCOPED_VETO_ATTESTATION_DIGEST_ALGORITHM",
    "PEARL_SCOPED_VETO_ATTESTATION_SCOPE",
    "PEARL_SCOPED_VETO_ATTESTATION_BINDING_FIELDS",
    "scoped_pearl_veto_attestation_digest",
    "build_scoped_pearl_veto_attestation",
    "verify_scoped_pearl_veto_attestation",
]
