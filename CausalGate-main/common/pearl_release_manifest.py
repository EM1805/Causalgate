from __future__ import annotations

"""Step 89 scoped Pearl release manifest helpers.

Step 88 binds a scoped Pearl card to the audited public-surface manifest.  Step
89 adds a release binding around that manifest: matrix versions, counts, the
Step-88 manifest digest, and hashes of the code files that define the scoped
Pearl/veto authority path must match the current checked-out release.  Runtime
therefore rejects stale cards even when their Step-88 manifest is internally
valid but was built against a different release surface.
"""

import hashlib
import json
from pathlib import Path
from typing import Dict, Mapping

from common.pearl_scope_manifest import (
    PEARL_SCOPED_SCOPE_MANIFEST_VERSION,
    normalize_scoped_pearl_manifest,
)

PEARL_SCOPED_RELEASE_MANIFEST_VERSION = "id_scoped_pearl_release_manifest_v1_step89"
PEARL_SCOPED_RELEASE_MANIFEST_LEVEL = (
    "release_bound_scoped_pearl_manifest_for_step87_step88_public_surface_"
    "with_code_digest_registry_and_no_global_full_id_claim"
)
PEARL_SCOPED_RELEASE_DIGEST_ALGORITHM = "sha256"
PEARL_SCOPED_RELEASE_SCOPE = "release_bound_audited_public_readiness_oracle_fuzz_surface_step89"

PEARL_SCOPED_RELEASE_CODE_FILES = (
    "common/pearl_scope_manifest.py",
    "common/pearl_release_manifest.py",
    "scm_parts/id_scoped_pearl_promotion.py",
    "scm_parts/id_scoped_pearl_scope_manifest.py",
    "scm_parts/id_full_promotion_gate.py",
    "scm_parts/id_failure_certificate_coverage.py",
    "scm_parts/id_full_recursive_authority_coverage.py",
    "scm_parts/id_full_recursive_trace_authority.py",
    "runtime/causal_authority.py",
    "contracts/causal_authority_for_veto.py",
)

PEARL_SCOPED_RELEASE_BINDING_FIELDS = (
    "release_manifest_version",
    "release_scope",
    "scoped_pearl_manifest_version",
    "scoped_pearl_manifest_digest",
    "scoped_pearl_scope",
    "id_scoped_pearl_promotion_gate",
    "id_full_readiness_matrix",
    "id_oracle_parity_matrix",
    "failure_certificate_coverage_matrix",
    "full_recursive_formula_authority_coverage_matrix",
    "n_identified_formula_rows_audited",
    "n_full_recursive_formula_authority",
    "n_finite_or_template_formula_authority",
    "n_technical_pending_not_certified",
    "global_full_recursive_id_implemented",
    "global_full_id_claim_allowed",
    "code_digest_algorithm",
    "code_file_digests",
    "code_manifest_digest",
)


def _project_root_from_here() -> Path:
    return Path(__file__).resolve().parents[1]


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _stable_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def code_file_digests(*, project_root: str | Path | None = None) -> Dict[str, str]:
    """Return stable sha256 digests for the Step-89 release-critical files."""
    root = Path(project_root) if project_root is not None else _project_root_from_here()
    digests: Dict[str, str] = {}
    for rel in PEARL_SCOPED_RELEASE_CODE_FILES:
        path = root / rel
        digests[rel] = _sha256_bytes(path.read_bytes()) if path.exists() else "MISSING"
    return digests


def code_manifest_digest(file_digests: Mapping[str, object]) -> str:
    return _sha256_bytes(_stable_json(dict(file_digests)).encode("utf-8"))


def _release_payload(release_manifest: Mapping[str, object]) -> Dict[str, object]:
    return {key: release_manifest.get(key) for key in PEARL_SCOPED_RELEASE_BINDING_FIELDS}


def scoped_pearl_release_digest(release_manifest: Mapping[str, object]) -> str:
    return _sha256_bytes(_stable_json(_release_payload(release_manifest)).encode("utf-8"))


def build_scoped_pearl_release_manifest(
    scoped_manifest: Mapping[str, object],
    *,
    project_root: str | Path | None = None,
) -> Dict[str, object]:
    """Build the current Step-89 release manifest around a Step-88 manifest."""
    manifest = dict(scoped_manifest)
    files = code_file_digests(project_root=project_root)
    release: Dict[str, object] = {
        "release_manifest_version": PEARL_SCOPED_RELEASE_MANIFEST_VERSION,
        "release_level": PEARL_SCOPED_RELEASE_MANIFEST_LEVEL,
        "release_scope": PEARL_SCOPED_RELEASE_SCOPE,
        "digest_algorithm": PEARL_SCOPED_RELEASE_DIGEST_ALGORITHM,
        "scoped_pearl_manifest_version": manifest.get("manifest_version", ""),
        "scoped_pearl_manifest_digest": manifest.get("manifest_digest", ""),
        "scoped_pearl_scope": manifest.get("scope", ""),
        "id_scoped_pearl_promotion_gate": manifest.get("id_scoped_pearl_promotion_gate", ""),
        "id_full_readiness_matrix": manifest.get("id_full_readiness_matrix", ""),
        "id_oracle_parity_matrix": manifest.get("id_oracle_parity_matrix", ""),
        "failure_certificate_coverage_matrix": manifest.get("failure_certificate_coverage_matrix", ""),
        "full_recursive_formula_authority_coverage_matrix": manifest.get("full_recursive_formula_authority_coverage_matrix", ""),
        "n_identified_formula_rows_audited": manifest.get("n_identified_formula_rows_audited", 0),
        "n_full_recursive_formula_authority": manifest.get("n_full_recursive_formula_authority", 0),
        "n_finite_or_template_formula_authority": manifest.get("n_finite_or_template_formula_authority", 0),
        "n_technical_pending_not_certified": manifest.get("n_technical_pending_not_certified", 0),
        "global_full_recursive_id_implemented": manifest.get("global_full_recursive_id_implemented", 0),
        "global_full_id_claim_allowed": manifest.get("global_full_id_claim_allowed", 0),
        "code_digest_algorithm": PEARL_SCOPED_RELEASE_DIGEST_ALGORITHM,
        "code_file_digests": files,
        "code_manifest_digest": code_manifest_digest(files),
        "binding_fields": list(PEARL_SCOPED_RELEASE_BINDING_FIELDS),
    }
    release["release_manifest_digest"] = scoped_pearl_release_digest(release)
    return release


def normalize_scoped_pearl_release_manifest(raw: object) -> Dict[str, object]:
    if isinstance(raw, Mapping):
        payload = dict(raw)
    elif isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        payload = dict(parsed) if isinstance(parsed, Mapping) else {}
    else:
        payload = {}
    if not payload:
        return {}
    nested = payload.get("scoped_pearl_release_manifest")
    if isinstance(nested, Mapping):
        return dict(nested)
    if payload.get("release_manifest_version") == PEARL_SCOPED_RELEASE_MANIFEST_VERSION:
        return payload
    if payload.get("scoped_pearl_release_manifest_version"):
        release: Dict[str, object] = {}
        aliases = {
            "release_manifest_version": ("release_manifest_version", "scoped_pearl_release_manifest_version"),
            "release_manifest_digest": ("release_manifest_digest", "scoped_pearl_release_manifest_digest"),
            "release_scope": ("release_scope", "scoped_pearl_release_scope"),
        }
        for field in PEARL_SCOPED_RELEASE_BINDING_FIELDS:
            for alias in aliases.get(field, (field, f"scoped_pearl_release_{field}")):
                if alias in payload:
                    release[field] = payload.get(alias)
                    break
        for field, field_aliases in aliases.items():
            for alias in field_aliases:
                if alias in payload:
                    release[field] = payload.get(alias)
                    break
        return release
    return {}


def verify_scoped_pearl_release_manifest(
    raw: object,
    *,
    scoped_manifest: Mapping[str, object] | None = None,
    project_root: str | Path | None = None,
) -> Dict[str, object]:
    """Verify that a scoped Pearl card is bound to the current Step-89 release."""
    release = normalize_scoped_pearl_release_manifest(raw)
    scoped = normalize_scoped_pearl_manifest(scoped_manifest or {})
    if not release:
        return {
            "scoped_pearl_release_present": 0,
            "scoped_pearl_release_verified": 0,
            "scoped_pearl_release_manifest_version": "",
            "scoped_pearl_release_manifest_digest": "",
            "scoped_pearl_release_digest_algorithm": PEARL_SCOPED_RELEASE_DIGEST_ALGORITHM,
            "scoped_pearl_release_missing_fields": "release_manifest",
            "scoped_pearl_release_mismatched_fields": "",
            "scoped_pearl_release_digest_valid": 0,
            "scoped_pearl_release_code_manifest_digest_valid": 0,
            "scoped_pearl_release_reason": "missing_scoped_pearl_release_manifest_step89",
        }
    if not scoped:
        return {
            "scoped_pearl_release_present": 1,
            "scoped_pearl_release_verified": 0,
            "scoped_pearl_release_manifest_version": str(release.get("release_manifest_version", "")),
            "scoped_pearl_release_manifest_digest": str(release.get("release_manifest_digest", "")),
            "scoped_pearl_release_digest_algorithm": PEARL_SCOPED_RELEASE_DIGEST_ALGORITHM,
            "scoped_pearl_release_missing_fields": "scoped_pearl_manifest",
            "scoped_pearl_release_mismatched_fields": "",
            "scoped_pearl_release_digest_valid": 0,
            "scoped_pearl_release_code_manifest_digest_valid": 0,
            "scoped_pearl_release_reason": "missing_scoped_pearl_scope_manifest_for_release_step89",
        }

    expected = build_scoped_pearl_release_manifest(scoped, project_root=project_root)
    missing = []
    mismatched = []
    for field in PEARL_SCOPED_RELEASE_BINDING_FIELDS:
        if field not in release:
            missing.append(field)
            continue
        if release.get(field) != expected.get(field):
            mismatched.append(field)

    observed_digest = str(release.get("release_manifest_digest") or release.get("scoped_pearl_release_manifest_digest") or "")
    expected_digest = scoped_pearl_release_digest(release)
    digest_valid = int(bool(observed_digest) and observed_digest == expected_digest)
    if not digest_valid:
        mismatched.append("release_manifest_digest")

    observed_code_digests = release.get("code_file_digests") if isinstance(release.get("code_file_digests"), Mapping) else {}
    observed_code_digest = str(release.get("code_manifest_digest") or "")
    observed_code_digest_valid = int(bool(observed_code_digest) and observed_code_digest == code_manifest_digest(observed_code_digests))
    if not observed_code_digest_valid and "code_manifest_digest" not in mismatched:
        mismatched.append("code_manifest_digest")

    # De-duplicate while preserving order for stable test/debug output.
    mismatched = list(dict.fromkeys(mismatched))
    verified = int(not missing and not mismatched)
    reason = "scoped_pearl_release_manifest_verified_step89" if verified else "scoped_pearl_release_manifest_blocked_step89"
    return {
        "scoped_pearl_release_present": 1,
        "scoped_pearl_release_verified": verified,
        "scoped_pearl_release_manifest_version": str(release.get("release_manifest_version", "")),
        "scoped_pearl_release_manifest_digest": observed_digest,
        "scoped_pearl_release_digest_algorithm": PEARL_SCOPED_RELEASE_DIGEST_ALGORITHM,
        "scoped_pearl_release_missing_fields": "|".join(missing),
        "scoped_pearl_release_mismatched_fields": "|".join(mismatched),
        "scoped_pearl_release_digest_valid": digest_valid,
        "scoped_pearl_release_code_manifest_digest_valid": observed_code_digest_valid,
        "scoped_pearl_release_expected_manifest_digest": str(expected.get("release_manifest_digest", "")),
        "scoped_pearl_release_expected_code_manifest_digest": str(expected.get("code_manifest_digest", "")),
        "scoped_pearl_release_reason": reason,
    }


__all__ = [
    "PEARL_SCOPED_RELEASE_MANIFEST_VERSION",
    "PEARL_SCOPED_RELEASE_MANIFEST_LEVEL",
    "PEARL_SCOPED_RELEASE_DIGEST_ALGORITHM",
    "PEARL_SCOPED_RELEASE_SCOPE",
    "PEARL_SCOPED_RELEASE_CODE_FILES",
    "PEARL_SCOPED_RELEASE_BINDING_FIELDS",
    "code_file_digests",
    "code_manifest_digest",
    "scoped_pearl_release_digest",
    "build_scoped_pearl_release_manifest",
    "normalize_scoped_pearl_release_manifest",
    "verify_scoped_pearl_release_manifest",
]
