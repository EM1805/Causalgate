from __future__ import annotations

"""Step 89 current scoped Pearl release manifest."""

from typing import Dict, Mapping

from common.pearl_release_manifest import (
    PEARL_SCOPED_RELEASE_MANIFEST_VERSION,
    PEARL_SCOPED_RELEASE_MANIFEST_LEVEL,
    PEARL_SCOPED_RELEASE_DIGEST_ALGORITHM,
    PEARL_SCOPED_RELEASE_SCOPE,
    PEARL_SCOPED_RELEASE_CODE_FILES,
    PEARL_SCOPED_RELEASE_BINDING_FIELDS,
    build_scoped_pearl_release_manifest,
    verify_scoped_pearl_release_manifest,
)
from .id_scoped_pearl_scope_manifest import build_current_scoped_pearl_manifest


def build_current_scoped_pearl_release_manifest(
    *,
    scoped_manifest: Mapping[str, object] | None = None,
    project_root: str | None = None,
) -> Dict[str, object]:
    manifest = dict(scoped_manifest or build_current_scoped_pearl_manifest())
    return build_scoped_pearl_release_manifest(manifest, project_root=project_root)


def run_scoped_pearl_release_manifest_matrix(
    *,
    scoped_manifest: Mapping[str, object] | None = None,
    project_root: str | None = None,
) -> Dict[str, object]:
    manifest = dict(scoped_manifest or build_current_scoped_pearl_manifest())
    release = build_current_scoped_pearl_release_manifest(scoped_manifest=manifest, project_root=project_root)
    verification = verify_scoped_pearl_release_manifest(release, scoped_manifest=manifest, project_root=project_root)
    return {
        "matrix_version": PEARL_SCOPED_RELEASE_MANIFEST_VERSION,
        "level": PEARL_SCOPED_RELEASE_MANIFEST_LEVEL,
        "release_scope": PEARL_SCOPED_RELEASE_SCOPE,
        "digest_algorithm": PEARL_SCOPED_RELEASE_DIGEST_ALGORITHM,
        "release_manifest_digest": release["release_manifest_digest"],
        "code_manifest_digest": release["code_manifest_digest"],
        "release_manifest_verified": int(verification["scoped_pearl_release_verified"]),
        "scoped_pearl_manifest_version": manifest.get("manifest_version", ""),
        "scoped_pearl_manifest_digest": manifest.get("manifest_digest", ""),
        "code_files": "|".join(PEARL_SCOPED_RELEASE_CODE_FILES),
        "binding_fields": "|".join(PEARL_SCOPED_RELEASE_BINDING_FIELDS),
        "release_manifest": release,
        "verification": verification,
        "global_full_id_claim_allowed": int(manifest.get("global_full_id_claim_allowed", 0)),
        "global_full_recursive_id_implemented": int(manifest.get("global_full_recursive_id_implemented", 0)),
        "scoped_pearl_veto_claim_allowed": int(manifest.get("scoped_pearl_veto_claim_allowed", 0)),
    }


__all__ = [
    "PEARL_SCOPED_RELEASE_MANIFEST_VERSION",
    "PEARL_SCOPED_RELEASE_MANIFEST_LEVEL",
    "PEARL_SCOPED_RELEASE_DIGEST_ALGORITHM",
    "PEARL_SCOPED_RELEASE_SCOPE",
    "PEARL_SCOPED_RELEASE_CODE_FILES",
    "PEARL_SCOPED_RELEASE_BINDING_FIELDS",
    "build_current_scoped_pearl_release_manifest",
    "run_scoped_pearl_release_manifest_matrix",
]
