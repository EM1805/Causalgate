from scm_parts.id_full_promotion_gate import ID_FULL_PROMOTION_GATE_VERSION, run_id_full_promotion_gate
from scm_parts.id_full_recursive_oracle_expansion import (
    ID_FULL_RECURSIVE_ORACLE_EXPANSION_VERSION,
    full_recursive_oracle_expansion_curated_cases,
    full_recursive_oracle_expansion_fuzz_cases,
    run_full_recursive_oracle_expansion_matrix,
)
from scm_parts.id_status import id_capability_flags


def test_step92_recursive_kernel_oracle_expansion_is_green_and_broader_than_step91():
    matrix = run_full_recursive_oracle_expansion_matrix()

    assert matrix["matrix_version"] == ID_FULL_RECURSIVE_ORACLE_EXPANSION_VERSION
    assert matrix["matrix_version"] == "id_full_recursive_oracle_expansion_v1_step92"
    assert matrix["all_passed"] == 1
    assert matrix["n_cases"] == 106
    assert matrix["n_passed"] == 106
    assert matrix["n_curated_cases"] == 10
    assert matrix["n_fuzz_cases"] == 96
    assert matrix["n_identified"] == 88
    assert matrix["n_nonidentified_certified"] == 18
    assert matrix["n_pending_kernel_blockers"] == 0
    assert matrix["n_identified_missing_formula_ast"] == 0
    assert matrix["n_nonidentified_missing_formal_certificate"] == 0
    assert matrix["n_carried_q_recursion_used"] >= 70
    assert matrix["global_full_id_claim_allowed"] == 1
    assert all(row["passed"] == 1 for row in matrix["rows"])


def test_step92_curated_cases_include_deeper_id7_w_step_and_formal_hedge():
    cases = {case.case_id: case for case in full_recursive_oracle_expansion_curated_cases()}

    assert "oracle92_three_mediator_chain_latent_xy" in cases
    assert "oracle92_w_step_irrelevant_intervention" in cases
    assert "oracle92_simple_formal_hedge" in cases
    assert "oracle92_multi_node_formal_hedge" in cases
    assert cases["oracle92_three_mediator_chain_latent_xy"].expected_identified == 1
    assert cases["oracle92_multi_node_formal_hedge"].expected_identified == 0


def test_step92_fuzz_surface_is_deterministic_and_five_node():
    cases = full_recursive_oracle_expansion_fuzz_cases()

    assert len(cases) == 96
    assert cases[0].case_id == "oracle92_fuzz_001"
    assert cases[-1].case_id == "oracle92_fuzz_096"
    assert all(case.case_kind == "stratified_five_node_admg_fuzz" for case in cases)
    assert all(set(case.graph.nodes) == {"X", "A", "B", "C", "Y"} for case in cases)


def test_step92_promotion_gate_consumes_oracle_expansion_but_is_green_on_global_flags():
    gate = run_id_full_promotion_gate()

    assert gate["matrix_version"] == ID_FULL_PROMOTION_GATE_VERSION
    assert gate["matrix_version"] == "id_full_promotion_gate_v7_step94"
    assert gate["id_full_recursive_oracle_expansion_matrix"] == ID_FULL_RECURSIVE_ORACLE_EXPANSION_VERSION
    assert gate["id_full_recursive_oracle_expansion_passed"] == 1
    assert gate["full_recursive_oracle_expansion"]["n_cases"] == 106
    assert gate["full_recursive_oracle_expansion"]["n_fuzz_cases"] == 96
    assert "id_full_recursive_oracle_expansion_passed" not in gate["missing_required_flags"]
    assert gate["missing_required_flags"] == ""
    assert gate["promotion_allowed"] == 1
    assert gate["full_id_claim_allowed_after_promotion_gate"] == 1


def test_step92_promotion_gate_blocks_if_oracle_expansion_is_not_green():
    failing_expansion = {
        "matrix_version": "id_full_recursive_oracle_expansion_fixture_failed",
        "all_passed": 0,
        "n_cases": 2,
        "n_passed": 1,
    }

    gate = run_id_full_promotion_gate(full_recursive_oracle_expansion=failing_expansion)

    assert gate["promotion_allowed"] == 0
    assert gate["id_full_recursive_oracle_expansion_passed"] == 0
    assert "id_full_recursive_oracle_expansion_passed" in gate["missing_required_flags"]
    assert "full_recursive_oracle_expansion_failed" in gate["blocker_classes"]


def test_step92_status_flags_present_without_global_full_id_claim():
    flags = id_capability_flags()

    assert flags["id_full_recursive_oracle_expansion_step92_implemented"] == 1
    assert flags["id_full_recursive_oracle_expansion_version"] == ID_FULL_RECURSIVE_ORACLE_EXPANSION_VERSION
    assert flags["id_full_promotion_gate_version"] == "id_full_promotion_gate_v7_step94"
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1
