from scm_parts.id_oracle_parity import (
    ID_ORACLE_PARITY_MATRIX_VERSION,
    run_id_oracle_parity_matrix,
    run_no_overclaim_fuzz_matrix,
)
from scm_parts.id_status import id_capability_flags


def test_step80_oracle_parity_matrix_passes_and_closes_audited_fuzz_gap():
    matrix = run_id_oracle_parity_matrix()
    rows = {row["case_id"]: row for row in matrix["rows"]}

    assert matrix["matrix_version"] == ID_ORACLE_PARITY_MATRIX_VERSION
    assert matrix["all_passed"] == 1
    assert matrix["n_oracle_cases"] == 7
    assert matrix["n_oracle_delegated_formula_gaps"] == 0
    assert matrix["full_id_claim_allowed"] == 1

    closed = rows["oracle_downstream_confounded_chain_canonical_step79"]
    assert closed["passed"] is True
    assert closed["identified"] is True
    assert closed["primary_formula_authority"] == "id_canonical_formula_step60"
    assert closed["delegated_formula_gap"] == 0
    assert "ID-7" in closed["canonical_rules"]
    assert "P(B | X_prime,A)" in closed["formula"]

    carried_q = rows["oracle_step75_non_frontdoor_carried_q"]
    assert carried_q["primary_formula_authority"] == "recursive_id_set_expression_diagnostic_step75"
    assert carried_q["delegated_formula_gap"] == 0
    audited = rows["oracle_step80_chain_dual_bridge_audited_closure"]
    assert audited["passed"] is True
    assert audited["identified"] is True
    assert audited["primary_formula_authority"] == "recursive_id_set_expression_diagnostic_step80_audited_fuzz_closure"
    assert audited["delegated_formula_gap"] == 0
    assert "P(B | X',A)" in audited["formula"]



def test_step76_fuzz_guard_has_no_silent_failures_or_full_id_claims():
    fuzz = run_no_overclaim_fuzz_matrix()

    assert fuzz["matrix_version"] == ID_ORACLE_PARITY_MATRIX_VERSION
    assert fuzz["all_passed"] == 1
    assert fuzz["n_cases"] == 72
    assert fuzz["full_id_claim_allowed"] == 1
    assert fuzz["n_nonidentified_with_failure_certificates"] > 0
    assert fuzz["n_delegated_identified_formula_authority"] == 0
    assert all(row["full_id_claim_allowed"] == 1 for row in fuzz["rows"])
    assert all(row["passed"] is True for row in fuzz["rows"])


def test_step76_status_flags_present_without_full_id_claim():
    flags = id_capability_flags()

    assert flags["id_full_oracle_parity_fuzz_step76_implemented"] == 1
    assert flags["id_full_downstream_confounded_chain_id7_step79_implemented"] == 1
    assert flags["id_full_audited_fuzz_closure_step80_implemented"] == 1
    assert "audited_fuzz_closure_step80" in flags["id_algorithm_status"]
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1
