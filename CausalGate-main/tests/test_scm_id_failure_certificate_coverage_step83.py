from scm_parts.id_failure_certificate_coverage import (
    ID_FAILURE_CERTIFICATE_COVERAGE_VERSION,
    run_failure_certificate_coverage_matrix,
)
from scm_parts.id_full_promotion_gate import ID_FULL_PROMOTION_GATE_VERSION, run_id_full_promotion_gate
from scm_parts.id_status import id_capability_flags


def test_step84_failure_certificate_coverage_matrix_closes_pending_fuzz_failures_without_silent_outputs():
    matrix = run_failure_certificate_coverage_matrix()

    assert matrix["matrix_version"] == ID_FAILURE_CERTIFICATE_COVERAGE_VERSION
    assert matrix["matrix_version"] == "id_failure_certificate_coverage_v2_step84"
    assert matrix["n_nonidentified_rows_audited"] == 27
    assert matrix["n_public_failure_channels_covered"] == 27
    assert matrix["all_public_failure_channels_green"] == 1
    assert matrix["n_formal_hedge_certified"] == 22
    assert matrix["n_explicit_rejections"] == 5
    assert matrix["n_technical_pending_not_certified"] == 0
    assert matrix["formal_failure_certificate_coverage_complete"] == 1
    assert matrix["technical_pending_case_ids"] == ""
    assert matrix["promotion_blocker_reason"] == "no_failure_certificate_coverage_blocker_step84"
    assert matrix["full_id_claim_allowed"] == 1


def test_step84_promotion_gate_uses_green_failure_certificate_coverage_but_stays_blocked_on_full_recursive_id():
    gate = run_id_full_promotion_gate()

    assert gate["matrix_version"] == ID_FULL_PROMOTION_GATE_VERSION
    assert gate["matrix_version"] == "id_full_promotion_gate_v7_step94"
    assert gate["failure_certificate_coverage_matrix"] == ID_FAILURE_CERTIFICATE_COVERAGE_VERSION
    assert gate["all_public_failure_channels_green"] == 1
    assert gate["formal_failure_certificate_coverage_complete"] == 1
    assert gate["n_technical_pending_not_certified"] == 0
    assert gate["failure_certificate_coverage"]["technical_pending_case_ids"] == ""
    assert "formal_failure_certificate_coverage_complete" not in gate["missing_required_flags"]
    assert "all_public_failure_channels_green" not in gate["missing_required_flags"]
    assert gate["missing_required_flags"] == ""
    assert gate["promotion_allowed"] == 1
    assert gate["full_id_claim_allowed_after_promotion_gate"] == 1


def test_step84_status_flags_present_without_full_id_claim():
    flags = id_capability_flags()

    assert flags["id_full_failure_certificate_coverage_step83_implemented"] == 1
    assert flags["id_full_subforest_hedge_certificates_step84_implemented"] == 1
    assert flags["id_failure_certificate_coverage_version"] == ID_FAILURE_CERTIFICATE_COVERAGE_VERSION
    assert flags["id_full_promotion_gate_version"] == "id_full_promotion_gate_v7_step94"
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1
