from common.pearl_release_manifest import (
    PEARL_SCOPED_RELEASE_MANIFEST_VERSION,
    code_manifest_digest,
    scoped_pearl_release_digest,
    verify_scoped_pearl_release_manifest,
)
from scm_parts.id_scoped_pearl_release_manifest import (
    build_current_scoped_pearl_release_manifest,
    run_scoped_pearl_release_manifest_matrix,
)
from scm_parts.id_scoped_pearl_scope_manifest import build_current_scoped_pearl_manifest
from scm_parts.id_status import id_capability_flags


def test_step89_current_scoped_pearl_release_manifest_binds_scope_and_code():
    scoped_manifest = build_current_scoped_pearl_manifest()
    release = build_current_scoped_pearl_release_manifest(scoped_manifest=scoped_manifest)

    assert release["release_manifest_version"] == PEARL_SCOPED_RELEASE_MANIFEST_VERSION
    assert release["scoped_pearl_manifest_digest"] == scoped_manifest["manifest_digest"]
    assert release["code_file_digests"]["runtime/causal_authority.py"]
    assert release["code_manifest_digest"] == code_manifest_digest(release["code_file_digests"])
    assert release["release_manifest_digest"] == scoped_pearl_release_digest(release)

    checked = verify_scoped_pearl_release_manifest(release, scoped_manifest=scoped_manifest)
    assert checked["scoped_pearl_release_verified"] == 1
    assert checked["scoped_pearl_release_digest_valid"] == 1
    assert checked["scoped_pearl_release_code_manifest_digest_valid"] == 1
    assert checked["scoped_pearl_release_mismatched_fields"] == ""


def test_step89_release_matrix_is_green_but_global_full_id_claim_stays_off():
    matrix = run_scoped_pearl_release_manifest_matrix()

    assert matrix["matrix_version"] == PEARL_SCOPED_RELEASE_MANIFEST_VERSION
    assert matrix["release_manifest_verified"] == 1
    assert matrix["scoped_pearl_veto_claim_allowed"] == 1
    assert matrix["global_full_recursive_id_implemented"] == 1
    assert matrix["global_full_id_claim_allowed"] == 1


def test_step89_release_manifest_blocks_rehashed_code_drift():
    scoped_manifest = build_current_scoped_pearl_manifest()
    release = build_current_scoped_pearl_release_manifest(scoped_manifest=scoped_manifest)
    tampered = dict(release)
    code_digests = dict(tampered["code_file_digests"])
    code_digests["runtime/causal_authority.py"] = "0" * 64
    tampered["code_file_digests"] = code_digests
    tampered["code_manifest_digest"] = code_manifest_digest(code_digests)
    tampered["release_manifest_digest"] = scoped_pearl_release_digest(tampered)

    checked = verify_scoped_pearl_release_manifest(tampered, scoped_manifest=scoped_manifest)

    assert checked["scoped_pearl_release_verified"] == 0
    assert checked["scoped_pearl_release_digest_valid"] == 1
    assert checked["scoped_pearl_release_code_manifest_digest_valid"] == 1
    assert "code_file_digests" in checked["scoped_pearl_release_mismatched_fields"]
    assert "code_manifest_digest" in checked["scoped_pearl_release_mismatched_fields"]


def test_step89_status_flags_are_exposed():
    flags = id_capability_flags()

    assert flags["id_scoped_pearl_release_manifest_step89_implemented"] == 1
    assert flags["id_scoped_pearl_release_manifest_version"] == PEARL_SCOPED_RELEASE_MANIFEST_VERSION
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1
