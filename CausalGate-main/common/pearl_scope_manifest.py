from __future__ import annotations

"""Step 88 scoped Pearl manifest binding helpers.

The scoped Pearl release from Step 87 is deliberately narrower than global
Full-ID.  These helpers bind that narrow claim to an explicit manifest of the
audited public surface.  Runtime code can verify a precomputed authority card
without rerunning the SCM audit, while still rejecting stale or tampered cards.
"""

import hashlib
import json
from typing import Any, Dict, Mapping

PEARL_SCOPED_SCOPE_MANIFEST_VERSION = "id_scoped_pearl_scope_manifest_v1_step88"
PEARL_SCOPED_SCOPE_MANIFEST_LEVEL = (
    "hash_bound_scope_manifest_for_step87_scoped_pearl_public_surface_"
    "readiness_oracle_fuzz_failure_recursive_trace_authority_step94_global_full_id_bound"
)
PEARL_SCOPED_SCOPE_MANIFEST_DIGEST_ALGORITHM = "sha256"

PEARL_SCOPED_EXPECTED_BINDINGS: Dict[str, object] = {
    "manifest_version": PEARL_SCOPED_SCOPE_MANIFEST_VERSION,
    "scope": "audited_public_readiness_oracle_fuzz_surface_step87",
    "id_scoped_pearl_promotion_gate": "id_scoped_pearl_promotion_gate_v1_step87",
    "id_scoped_pearl_promotion_gate_passed": 1,
    "id_full_readiness_matrix": "id_full_readiness_matrix_v11_step80",
    "id_full_readiness_matrix_passed": 1,
    "id_oracle_parity_matrix": "id_oracle_parity_matrix_v3_step80",
    "id_oracle_parity_fuzz_passed": 1,
    "failure_certificate_coverage_matrix": "id_failure_certificate_coverage_v2_step84",
    "formal_failure_certificate_coverage_complete": 1,
    "full_recursive_formula_authority_coverage_matrix": "id_full_recursive_authority_coverage_v2_step86",
    "pearl_formula_authority_coverage_complete": 1,
    "n_identified_formula_rows_audited": 78,
    "n_full_recursive_formula_authority": 78,
    "n_finite_or_template_formula_authority": 0,
    "n_technical_pending_not_certified": 0,
    "global_full_recursive_id_implemented": 1,
    "global_full_id_claim_allowed": 1,
    "scoped_promotion_allowed": 1,
    "scoped_pearl_veto_claim_allowed": 1,
}

PEARL_SCOPED_MANIFEST_BINDING_FIELDS = tuple(PEARL_SCOPED_EXPECTED_BINDINGS.keys())

_FLAT_MANIFEST_ALIASES = {
    "manifest_version": ("manifest_version", "scoped_pearl_manifest_version", "scoped_pearl_scope_manifest_version"),
    "manifest_digest": ("manifest_digest", "scoped_pearl_manifest_digest", "scoped_pearl_scope_manifest_digest"),
    "digest_algorithm": ("digest_algorithm", "scoped_pearl_manifest_digest_algorithm"),
    "scope": ("scope", "pearl_claim_scope"),
}


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "pass", "passed", "complete", "green"}


def _canonical_manifest_payload(manifest: Mapping[str, object]) -> Dict[str, object]:
    return {
        key: manifest.get(key)
        for key in PEARL_SCOPED_MANIFEST_BINDING_FIELDS
    }


def scoped_pearl_manifest_digest(manifest: Mapping[str, object]) -> str:
    payload = _canonical_manifest_payload(manifest)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_scoped_pearl_manifest_from_gate(gate: Mapping[str, object]) -> Dict[str, object]:
    manifest = dict(PEARL_SCOPED_EXPECTED_BINDINGS)
    # Prefer observed gate values where they are part of the binding.  This lets
    # tests inject a red/stale gate and get an explicit mismatch instead of a
    # fabricated green manifest.
    mapping = {
        "scope": "scope",
        "id_scoped_pearl_promotion_gate": "matrix_version",
        "id_scoped_pearl_promotion_gate_passed": "scoped_promotion_allowed",
        "id_full_readiness_matrix": "id_full_readiness_matrix",
        "id_oracle_parity_matrix": "id_oracle_parity_matrix",
        "failure_certificate_coverage_matrix": "failure_certificate_coverage_matrix",
        "full_recursive_formula_authority_coverage_matrix": "full_recursive_formula_authority_coverage_matrix",
        "n_identified_formula_rows_audited": "n_identified_formula_rows_audited",
        "n_full_recursive_formula_authority": "n_full_recursive_formula_authority",
        "n_finite_or_template_formula_authority": "n_finite_or_template_formula_authority",
        "n_technical_pending_not_certified": "n_technical_pending_not_certified",
        "global_full_recursive_id_implemented": "global_full_recursive_id_implemented",
        "global_full_id_claim_allowed": "global_full_id_claim_allowed",
        "scoped_promotion_allowed": "scoped_promotion_allowed",
        "scoped_pearl_veto_claim_allowed": "scoped_pearl_veto_claim_allowed",
    }
    for out_key, gate_key in mapping.items():
        if gate_key in gate:
            manifest[out_key] = gate.get(gate_key)
    # These pass/fail values are already requirements inside the scoped gate;
    # keep them explicit in the manifest so runtime can reject stale cards.
    for key in (
        "id_full_readiness_matrix_passed",
        "id_oracle_parity_fuzz_passed",
        "formal_failure_certificate_coverage_complete",
        "pearl_formula_authority_coverage_complete",
    ):
        if key in gate:
            manifest[key] = int(_truthy(gate.get(key)))
    manifest["manifest_version"] = PEARL_SCOPED_SCOPE_MANIFEST_VERSION
    manifest["manifest_level"] = PEARL_SCOPED_SCOPE_MANIFEST_LEVEL
    manifest["digest_algorithm"] = PEARL_SCOPED_SCOPE_MANIFEST_DIGEST_ALGORITHM
    manifest["binding_fields"] = list(PEARL_SCOPED_MANIFEST_BINDING_FIELDS)
    manifest["manifest_digest"] = scoped_pearl_manifest_digest(manifest)
    return manifest


def _maybe_json_mapping(value: object) -> Dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def normalize_scoped_pearl_manifest(raw: object) -> Dict[str, object]:
    """Return a manifest mapping from nested or flattened card evidence."""
    payload = _maybe_json_mapping(raw)
    if not payload:
        return {}
    nested = _maybe_json_mapping(payload.get("scoped_pearl_manifest"))
    if nested:
        return nested
    if payload.get("manifest_version") == PEARL_SCOPED_SCOPE_MANIFEST_VERSION:
        return dict(payload)
    if payload.get("scoped_pearl_manifest_version") or payload.get("scoped_pearl_scope_manifest_version"):
        manifest: Dict[str, object] = {}
        for field in PEARL_SCOPED_MANIFEST_BINDING_FIELDS:
            aliases = _FLAT_MANIFEST_ALIASES.get(field, (field, f"scoped_pearl_manifest_{field}"))
            for alias in aliases:
                if alias in payload:
                    manifest[field] = payload.get(alias)
                    break
        for out_key, aliases in _FLAT_MANIFEST_ALIASES.items():
            for alias in aliases:
                if alias in payload:
                    manifest[out_key] = payload.get(alias)
                    break
        return manifest
    return {}


def verify_scoped_pearl_manifest(raw: object, *, evidence: Mapping[str, object] | None = None) -> Dict[str, object]:
    """Verify that a scoped Pearl card is bound to the Step-88 audit manifest."""
    manifest = normalize_scoped_pearl_manifest(raw)
    missing = []
    mismatched = []
    if not manifest:
        return {
            "scoped_pearl_manifest_present": 0,
            "scoped_pearl_manifest_verified": 0,
            "scoped_pearl_manifest_version": "",
            "scoped_pearl_manifest_digest": "",
            "scoped_pearl_manifest_digest_algorithm": PEARL_SCOPED_SCOPE_MANIFEST_DIGEST_ALGORITHM,
            "scoped_pearl_manifest_missing_fields": "manifest",
            "scoped_pearl_manifest_mismatched_fields": "",
            "scoped_pearl_manifest_digest_valid": 0,
            "scoped_pearl_manifest_reason": "missing_scoped_pearl_scope_manifest_step88",
        }

    for field, expected in PEARL_SCOPED_EXPECTED_BINDINGS.items():
        if field not in manifest:
            missing.append(field)
            continue
        observed = manifest.get(field)
        if str(observed) != str(expected):
            mismatched.append(field)

    digest_observed = str(manifest.get("manifest_digest") or manifest.get("scoped_pearl_manifest_digest") or "")
    digest_expected = scoped_pearl_manifest_digest(manifest)
    digest_valid = int(bool(digest_observed) and digest_observed == digest_expected)
    if not digest_valid:
        mismatched.append("manifest_digest")

    evidence_mismatches = []
    if evidence:
        evidence_pairs = {
            "scope": "scope",
            "id_scoped_pearl_promotion_gate": "id_scoped_pearl_promotion_gate",
            "id_full_readiness_matrix": "id_full_readiness_matrix",
            "id_oracle_parity_matrix": "id_oracle_parity_matrix",
            "id_full_readiness_matrix_passed": "id_full_readiness_matrix_passed",
            "id_oracle_parity_fuzz_passed": "id_oracle_parity_fuzz_passed",
            "formal_failure_certificate_coverage_complete": "formal_failure_certificate_coverage_complete",
            "global_full_recursive_id_implemented": "global_full_recursive_id_implemented",
            "global_full_id_claim_allowed": "global_full_id_claim_allowed",
        }
        for manifest_key, evidence_key in evidence_pairs.items():
            if evidence_key in evidence and str(evidence.get(evidence_key)) != str(manifest.get(manifest_key)):
                evidence_mismatches.append(f"{evidence_key}!={manifest_key}")

    verified = int(not missing and not mismatched and not evidence_mismatches)
    reason = "scoped_pearl_scope_manifest_verified_step88" if verified else "scoped_pearl_scope_manifest_blocked_step88"
    return {
        "scoped_pearl_manifest_present": 1,
        "scoped_pearl_manifest_verified": verified,
        "scoped_pearl_manifest_version": str(manifest.get("manifest_version") or ""),
        "scoped_pearl_manifest_digest": digest_observed,
        "scoped_pearl_manifest_expected_digest": digest_expected,
        "scoped_pearl_manifest_digest_algorithm": PEARL_SCOPED_SCOPE_MANIFEST_DIGEST_ALGORITHM,
        "scoped_pearl_manifest_missing_fields": "|".join(missing),
        "scoped_pearl_manifest_mismatched_fields": "|".join(mismatched),
        "scoped_pearl_manifest_evidence_mismatches": "|".join(evidence_mismatches),
        "scoped_pearl_manifest_digest_valid": digest_valid,
        "scoped_pearl_manifest_reason": reason,
    }


__all__ = [
    "PEARL_SCOPED_SCOPE_MANIFEST_VERSION",
    "PEARL_SCOPED_SCOPE_MANIFEST_LEVEL",
    "PEARL_SCOPED_SCOPE_MANIFEST_DIGEST_ALGORITHM",
    "PEARL_SCOPED_EXPECTED_BINDINGS",
    "PEARL_SCOPED_MANIFEST_BINDING_FIELDS",
    "scoped_pearl_manifest_digest",
    "build_scoped_pearl_manifest_from_gate",
    "normalize_scoped_pearl_manifest",
    "verify_scoped_pearl_manifest",
]
