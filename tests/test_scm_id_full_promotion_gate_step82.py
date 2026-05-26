from scm_parts.id_full_promotion_gate import (
    FULL_RECURSIVE_FORMULA_AUTHORITIES,
    ID_FULL_PROMOTION_GATE_VERSION,
    run_id_full_promotion_gate,
)
from scm_parts.id_status import id_capability_flags


def test_step82_current_backend_blocks_full_id_pearl_promotion_with_explicit_reasons():
    gate = run_id_full_promotion_gate()

    assert gate["matrix_version"] == ID_FULL_PROMOTION_GATE_VERSION
    assert gate["promotion_allowed"] == 1
    assert gate["full_recursive_id_implemented"] == 1
    assert gate["full_id_claim_allowed"] == 1
    assert gate["id_full_readiness_matrix_passed"] == 1
    assert gate["id_oracle_parity_fuzz_passed"] == 1
    assert gate["no_raw_delegated_formula_authority"] == 1
    assert gate["full_recursive_formula_authority_present"] == 1
    assert gate["missing_required_flags"] == ""
    assert "full_recursive_formula_authority_present" not in gate["missing_required_flags"]
    assert gate["full_id_claim_allowed_after_promotion_gate"] == 1


def test_step82_finite_and_template_authorities_are_not_enough_for_promotion():
    readiness = {
        "matrix_version": "id_full_readiness_matrix_fixture",
        "all_passed": 1,
        "n_passed": 1,
        "n_cases": 1,
        "n_delegated_formula_authority": 0,
        "rows": [
            {
                "identified": 1,
                "primary_formula_authority": "id_canonical_formula_step60",
                "joint_primary_formula_authority": "",
            }
        ],
    }
    oracle = {
        "matrix_version": "id_oracle_fixture",
        "all_passed": 1,
        "n_oracle_delegated_formula_gaps": 0,
        "rows": [],
        "fuzz": {"n_delegated_identified_formula_authority": 0, "rows": []},
    }
    flags = dict(id_capability_flags())
    flags["full_recursive_id_implemented"] = 1
    flags["full_id_claim_allowed"] = 1

    gate = run_id_full_promotion_gate(
        readiness=readiness,
        oracle=oracle,
        capability_flags=flags,
        formal_failure_certificate_coverage_complete=1,
    )

    assert gate["promotion_allowed"] == 0
    assert gate["full_recursive_formula_authority_present"] == 0
    assert gate["no_finite_or_template_only_formula_authority_for_promotion"] == 0
    assert "id_canonical_formula_step60" in gate["finite_or_template_authorities_observed"]
    assert "full_recursive_formula_authority_present" in gate["missing_required_flags"]
    assert "no_finite_or_template_only_formula_authority_for_promotion" in gate["missing_required_flags"]


def test_step82_promotion_gate_can_turn_green_only_with_full_recursive_authority_and_all_flags():
    authority = sorted(FULL_RECURSIVE_FORMULA_AUTHORITIES)[0]
    readiness = {
        "matrix_version": "id_full_readiness_matrix_future",
        "all_passed": 1,
        "n_passed": 1,
        "n_cases": 1,
        "n_delegated_formula_authority": 0,
        "rows": [
            {
                "identified": 1,
                "primary_formula_authority": authority,
                "joint_primary_formula_authority": "",
                "formula_ast_present": 1,
            }
        ],
    }
    oracle = {
        "matrix_version": "id_oracle_parity_matrix_future",
        "all_passed": 1,
        "n_oracle_delegated_formula_gaps": 0,
        "rows": [],
        "fuzz": {"n_delegated_identified_formula_authority": 0, "rows": []},
    }
    flags = dict(id_capability_flags())
    flags["full_recursive_id_implemented"] = 1
    flags["full_id_claim_allowed"] = 1

    gate = run_id_full_promotion_gate(
        readiness=readiness,
        oracle=oracle,
        capability_flags=flags,
        formal_failure_certificate_coverage_complete=1,
    )

    assert gate["promotion_allowed"] == 1
    assert gate["missing_required_flags"] == ""
    assert gate["full_recursive_formula_authority_present"] == 1
    assert gate["no_finite_or_template_only_formula_authority_for_promotion"] == 1
    assert gate["full_id_claim_allowed_after_promotion_gate"] == 1
    assert all(row["passed"] for row in gate["requirements"])


def test_step82_gate_exports_version_for_veto_pearl_evidence():
    gate = run_id_full_promotion_gate()
    assert gate["matrix_version"] == ID_FULL_PROMOTION_GATE_VERSION
    assert "id_full_promotion_gate_v7_step94" == gate["matrix_version"]
