from scm_parts.id_full_promotion_gate import ID_FULL_PROMOTION_GATE_VERSION, run_id_full_promotion_gate
from scm_parts.id_full_recursive_authority_coverage import (
    ID_FULL_RECURSIVE_AUTHORITY_COVERAGE_VERSION,
    run_full_recursive_authority_coverage_matrix,
)
from scm_parts.id_status import id_capability_flags


def test_step86_recursive_trace_formula_authority_coverage_is_complete_but_no_global_claim():
    matrix = run_full_recursive_authority_coverage_matrix()

    assert matrix["matrix_version"] == ID_FULL_RECURSIVE_AUTHORITY_COVERAGE_VERSION
    assert matrix["matrix_version"] == "id_full_recursive_authority_coverage_v2_step86"
    assert matrix["n_identified_formula_rows_audited"] == 78
    assert matrix["n_formula_authority_rows_with_evidence"] == 78
    assert matrix["n_raw_delegated_formula_authority"] == 0
    assert matrix["n_missing_formula_authority"] == 0
    assert matrix["all_identified_formula_rows_public_clean"] == 1
    assert matrix["n_full_recursive_formula_authority"] == 78
    assert matrix["n_finite_or_template_formula_authority"] == 0
    assert matrix["n_primary_finite_or_template_formula_authority"] == 78
    assert matrix["n_recursive_trace_certified_formula_authority"] == 78
    assert matrix["pearl_formula_authority_coverage_complete"] == 1
    assert matrix["promotion_blocker_reason"] == "formula_authority_coverage_complete"
    assert matrix["full_id_claim_allowed"] == 1


def test_step86_promotion_gate_consumes_recursive_trace_coverage_and_is_green():
    gate = run_id_full_promotion_gate()

    assert gate["matrix_version"] == ID_FULL_PROMOTION_GATE_VERSION
    assert gate["matrix_version"] == "id_full_promotion_gate_v7_step94"
    assert gate["full_recursive_formula_authority_coverage_matrix"] == ID_FULL_RECURSIVE_AUTHORITY_COVERAGE_VERSION
    assert gate["all_identified_formula_rows_public_clean"] == 1
    assert gate["pearl_formula_authority_coverage_complete"] == 1
    assert gate["full_recursive_authority_coverage"]["promotion_blocker_reason"] == "formula_authority_coverage_complete"
    assert "pearl_formula_authority_coverage_complete" not in gate["missing_required_flags"]
    assert "formal_failure_certificate_coverage_complete" not in gate["missing_required_flags"]
    assert gate["promotion_allowed"] == 1
    assert gate["full_id_claim_allowed_after_promotion_gate"] == 1


def test_step86_status_flags_present_without_full_id_claim():
    flags = id_capability_flags()

    assert flags["id_full_recursive_authority_coverage_step85_implemented"] == 1
    assert flags["id_full_recursive_trace_authority_step86_implemented"] == 1
    assert flags["id_full_recursive_authority_coverage_version"] == ID_FULL_RECURSIVE_AUTHORITY_COVERAGE_VERSION
    assert flags["id_full_promotion_gate_version"] == "id_full_promotion_gate_v7_step94"
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1
