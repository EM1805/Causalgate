from __future__ import annotations

"""Step 88 current scoped Pearl manifest.

This module materializes the hash-bound manifest for the Step-87 scoped Pearl
release gate.  It is intentionally scope-bound and keeps the global Full-ID
claim disabled.
"""

from typing import Dict, Mapping

from common.pearl_scope_manifest import (
    PEARL_SCOPED_SCOPE_MANIFEST_VERSION,
    PEARL_SCOPED_SCOPE_MANIFEST_LEVEL,
    PEARL_SCOPED_SCOPE_MANIFEST_DIGEST_ALGORITHM,
    PEARL_SCOPED_EXPECTED_BINDINGS,
    PEARL_SCOPED_MANIFEST_BINDING_FIELDS,
    build_scoped_pearl_manifest_from_gate,
    verify_scoped_pearl_manifest,
)
from .id_scoped_pearl_promotion import run_scoped_pearl_promotion_gate


def build_current_scoped_pearl_manifest(*, gate: Mapping[str, object] | None = None) -> Dict[str, object]:
    """Return the current Step-88 manifest with a stable digest."""
    payload = dict(gate or run_scoped_pearl_promotion_gate())
    return build_scoped_pearl_manifest_from_gate(payload)


def run_scoped_pearl_manifest_binding_matrix(*, gate: Mapping[str, object] | None = None) -> Dict[str, object]:
    manifest = build_current_scoped_pearl_manifest(gate=gate)
    verification = verify_scoped_pearl_manifest(manifest)
    return {
        "matrix_version": PEARL_SCOPED_SCOPE_MANIFEST_VERSION,
        "level": PEARL_SCOPED_SCOPE_MANIFEST_LEVEL,
        "digest_algorithm": PEARL_SCOPED_SCOPE_MANIFEST_DIGEST_ALGORITHM,
        "manifest_digest": manifest["manifest_digest"],
        "manifest_verified": int(verification["scoped_pearl_manifest_verified"]),
        "scope": manifest["scope"],
        "id_scoped_pearl_promotion_gate": manifest["id_scoped_pearl_promotion_gate"],
        "binding_fields": "|".join(PEARL_SCOPED_MANIFEST_BINDING_FIELDS),
        "expected_bindings": dict(PEARL_SCOPED_EXPECTED_BINDINGS),
        "manifest": manifest,
        "verification": verification,
        "global_full_id_claim_allowed": int(manifest["global_full_id_claim_allowed"]),
        "global_full_recursive_id_implemented": int(manifest["global_full_recursive_id_implemented"]),
        "scoped_pearl_veto_claim_allowed": int(manifest["scoped_pearl_veto_claim_allowed"]),
    }


__all__ = [
    "PEARL_SCOPED_SCOPE_MANIFEST_VERSION",
    "PEARL_SCOPED_SCOPE_MANIFEST_LEVEL",
    "PEARL_SCOPED_SCOPE_MANIFEST_DIGEST_ALGORITHM",
    "PEARL_SCOPED_EXPECTED_BINDINGS",
    "PEARL_SCOPED_MANIFEST_BINDING_FIELDS",
    "build_current_scoped_pearl_manifest",
    "run_scoped_pearl_manifest_binding_matrix",
]
