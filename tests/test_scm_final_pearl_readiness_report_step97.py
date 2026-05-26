from scm_parts.id_final_pearl_readiness_report import (
    ID_FINAL_PEARL_READINESS_REPORT_VERSION,
    final_pearl_readiness_report_digest,
    run_final_pearl_readiness_report,
)
from scm_parts.id_status import id_capability_flags


def test_step97_final_pearl_readiness_report_is_green():
    report = run_final_pearl_readiness_report(include_subreports=False)

    assert report["matrix_version"] == ID_FINAL_PEARL_READINESS_REPORT_VERSION
    assert report["final_pearl_readiness_allowed"] == 1
    assert report["global_full_id_backend_ready"] == 1
    assert report["pearl_complete_veto_runtime_ready"] == 1
    assert report["adversarial_no_overclaim_passed"] == 1
    assert report["full_recursive_id_implemented"] == 1
    assert report["full_id_claim_allowed"] == 1
    assert report["n_requirements_passed"] == report["n_requirements"]
    assert report["missing_required_flags"] == ""
    assert report["n_kernel_passed"] == report["n_kernel_cases"]
    assert report["n_oracle_expansion_passed"] == report["n_oracle_expansion_cases"]
    assert report["n_full_recursive_formula_authority"] == report["n_identified_formula_rows_audited"]
    assert report["n_adversarial_cases_blocked"] == 19
    assert report["report_digest"] == final_pearl_readiness_report_digest(report)


def test_step97_report_blocks_if_no_overclaim_suite_is_red():
    bad_no_overclaim = {
        "matrix_version": "veto_pearl_global_no_overclaim_adversarial_suite_v1_step96",
        "all_passed": 0,
        "n_cases": 20,
        "n_passed": 19,
        "n_adversarial_cases": 19,
        "n_adversarial_cases_blocked": 18,
    }

    report = run_final_pearl_readiness_report(
        no_overclaim=bad_no_overclaim,
        include_subreports=False,
    )

    assert report["final_pearl_readiness_allowed"] == 0
    assert "global_pearl_no_overclaim_suite_green" in report["missing_required_flags"]
    assert "global_pearl_no_overclaim_suite_not_green" in report["blocker_classes"]


def test_step97_report_blocks_if_promotion_gate_is_red():
    bad_gate = {
        "matrix_version": "id_full_promotion_gate_v7_step94",
        "promotion_allowed": 0,
        "missing_required_flags": "formal_failure_certificate_coverage_complete",
        "full_recursive_id_implemented": 1,
        "full_id_claim_allowed": 1,
        "id_full_recursive_kernel_matrix_passed": 1,
        "id_full_recursive_oracle_expansion_passed": 1,
        "formal_failure_certificate_coverage_complete": 0,
        "all_public_failure_channels_green": 1,
        "pearl_formula_authority_coverage_complete": 1,
        "full_recursive_formula_authority_present": 1,
        "full_recursive_kernel_matrix": {"matrix_version": "id_full_recursive_kernel_v1_step91", "n_cases": 7, "n_passed": 7},
        "full_recursive_oracle_expansion": {"matrix_version": "id_full_recursive_oracle_expansion_v1_step92", "n_cases": 106, "n_passed": 106},
        "failure_certificate_coverage": {"n_technical_pending_not_certified": 0},
        "full_recursive_authority_coverage": {"matrix_version": "id_full_recursive_authority_coverage_v2_step86"},
        "n_full_recursive_formula_authority": 78,
        "n_identified_formula_rows_audited": 78,
    }

    report = run_final_pearl_readiness_report(
        promotion_gate=bad_gate,
        include_subreports=False,
    )

    assert report["final_pearl_readiness_allowed"] == 0
    assert "global_full_id_promotion_gate_green" in report["missing_required_flags"]
    assert "failure_certificate_coverage_complete" in report["missing_required_flags"]


def test_step97_report_digest_detects_tampering():
    report = run_final_pearl_readiness_report(include_subreports=False)
    original_digest = report["report_digest"]

    tampered = dict(report)
    tampered["full_id_claim_allowed"] = 0

    assert final_pearl_readiness_report_digest(tampered) != original_digest


def test_step97_status_flags_are_exposed():
    flags = id_capability_flags()

    assert flags["id_final_pearl_readiness_report_step97_implemented"] == 1
    assert flags["id_final_pearl_readiness_report_version"] == ID_FINAL_PEARL_READINESS_REPORT_VERSION
    assert flags["id_final_pearl_readiness_report_matrix_version"] == ID_FINAL_PEARL_READINESS_REPORT_VERSION
