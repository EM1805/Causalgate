from common.pearl_scope_manifest import (
    PEARL_SCOPED_EXPECTED_BINDINGS,
    PEARL_SCOPED_SCOPE_MANIFEST_VERSION,
    scoped_pearl_manifest_digest,
    verify_scoped_pearl_manifest,
)
from scm_parts.id_scoped_pearl_scope_manifest import (
    build_current_scoped_pearl_manifest,
    run_scoped_pearl_manifest_binding_matrix,
)
from scm_parts.id_status import id_capability_flags


def test_step88_current_scoped_pearl_manifest_is_digest_bound_to_audited_surface():
    manifest = build_current_scoped_pearl_manifest()

    assert manifest["manifest_version"] == PEARL_SCOPED_SCOPE_MANIFEST_VERSION
    assert manifest["manifest_digest"] == scoped_pearl_manifest_digest(manifest)
    for key, expected in PEARL_SCOPED_EXPECTED_BINDINGS.items():
        assert str(manifest[key]) == str(expected)

    verified = verify_scoped_pearl_manifest(manifest)
    assert verified["scoped_pearl_manifest_verified"] == 1
    assert verified["scoped_pearl_manifest_digest_valid"] == 1
    assert verified["scoped_pearl_manifest_mismatched_fields"] == ""
    assert verified["scoped_pearl_manifest_missing_fields"] == ""


def test_step88_manifest_binding_matrix_keeps_global_full_id_claim_off():
    matrix = run_scoped_pearl_manifest_binding_matrix()

    assert matrix["matrix_version"] == PEARL_SCOPED_SCOPE_MANIFEST_VERSION
    assert matrix["manifest_verified"] == 1
    assert matrix["scoped_pearl_veto_claim_allowed"] == 1
    assert matrix["global_full_recursive_id_implemented"] == 1
    assert matrix["global_full_id_claim_allowed"] == 1
    assert matrix["manifest"]["n_identified_formula_rows_audited"] == 78
    assert matrix["manifest"]["n_full_recursive_formula_authority"] == 78
    assert matrix["manifest"]["n_finite_or_template_formula_authority"] == 0


def test_step88_manifest_verifier_rejects_stale_digest_and_stale_scope_counts():
    manifest = build_current_scoped_pearl_manifest()
    stale_digest = dict(manifest)
    stale_digest["n_identified_formula_rows_audited"] = 77

    checked = verify_scoped_pearl_manifest(stale_digest)
    assert checked["scoped_pearl_manifest_verified"] == 0
    assert checked["scoped_pearl_manifest_digest_valid"] == 0
    assert "n_identified_formula_rows_audited" in checked["scoped_pearl_manifest_mismatched_fields"]
    assert "manifest_digest" in checked["scoped_pearl_manifest_mismatched_fields"]

    stale_but_rehashed = dict(stale_digest)
    stale_but_rehashed["manifest_digest"] = scoped_pearl_manifest_digest(stale_but_rehashed)
    checked_rehashed = verify_scoped_pearl_manifest(stale_but_rehashed)
    assert checked_rehashed["scoped_pearl_manifest_verified"] == 0
    assert checked_rehashed["scoped_pearl_manifest_digest_valid"] == 1
    assert checked_rehashed["scoped_pearl_manifest_mismatched_fields"] == "n_identified_formula_rows_audited"


def test_step88_status_flags_expose_manifest_binding_layer():
    flags = id_capability_flags()

    assert flags["id_scoped_pearl_scope_manifest_step88_implemented"] == 1
    assert flags["id_scoped_pearl_scope_manifest_version"] == PEARL_SCOPED_SCOPE_MANIFEST_VERSION
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1
