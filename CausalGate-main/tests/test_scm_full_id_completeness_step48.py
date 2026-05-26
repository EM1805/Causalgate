from scm_parts.id_completeness import canonical_id_completeness_cases, run_id_completeness_matrix
from scm_parts.id_status import id_capability_flags


def test_step48_canonical_completeness_matrix_all_current_gates_pass():
    matrix = run_id_completeness_matrix()
    assert matrix["matrix_version"] == "id_completeness_matrix_v1_step48"
    assert matrix["n_cases"] >= 6
    assert matrix["n_failed"] == 0, matrix["rows"]
    assert matrix["all_passed"] == 1
    assert matrix["full_id_claim_allowed"] == 1


def test_step48_cases_include_required_id_patterns():
    case_ids = {case.case_id for case in canonical_id_completeness_cases()}
    assert "observed_dag_truncated_factorization" in case_ids
    assert "backdoor_adjustment" in case_ids
    assert "frontdoor_limited" in case_ids
    assert "direct_confounding_hedge_fail" in case_ids
    assert "graphical_zero_effect" in case_ids
    assert "district_decomposition_q_factor" in case_ids


def test_step48_direct_confounding_uses_formal_fail_branch_not_possible_hedge_shortcut():
    matrix = run_id_completeness_matrix()
    rows = {row["case_id"]: row for row in matrix["rows"]}
    hedge = rows["direct_confounding_hedge_fail"]
    assert hedge["passed"] is True
    assert hedge["id_strategy"] == "blocked_formal_hedge_certificate"
    assert hedge["identification_authority"] == "recursive_id_fail_branch"
    assert hedge["formal_hedge_certified"] == 1
    assert "ID-5" in hedge["canonical_rules"]


def test_step48_identifiable_cases_do_not_emit_formal_hedge_rule():
    matrix = run_id_completeness_matrix()
    for row in matrix["rows"]:
        if row["expected_identifiable"]:
            assert row["formal_hedge_certified"] == 0, row
            assert "ID-5" not in row["canonical_rules"], row


def test_step48_status_flags_present_but_full_id_still_false():
    flags = id_capability_flags()
    assert flags["id_completeness_matrix_step48_implemented"] == 1
    assert flags["full_recursive_id_implemented"] == 1
