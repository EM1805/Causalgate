from scm_parts.admg import admg_from_edges
from scm_parts.id_full import full_id
from scm_parts.id_full_promotion_gate import run_id_full_promotion_gate
from scm_parts.id_full_recursive_kernel import (
    ID_FULL_RECURSIVE_KERNEL_AUTHORITY,
    ID_FULL_RECURSIVE_KERNEL_VERSION,
    full_recursive_id_kernel_diagnostic,
    run_full_recursive_id_kernel_matrix,
)
from scm_parts.id_status import id_capability_flags


def test_step91_recursive_kernel_matrix_covers_id1_to_id7_and_formal_hedge():
    matrix = run_full_recursive_id_kernel_matrix()

    assert matrix["matrix_version"] == ID_FULL_RECURSIVE_KERNEL_VERSION
    assert matrix["all_passed"] == 1
    assert matrix["n_cases"] == 7
    assert matrix["n_passed"] == 7
    assert matrix["n_identified"] == 6
    assert matrix["n_nonidentified_certified"] == 1
    assert matrix["n_carried_q_recursion_used"] >= 3
    assert matrix["n_district_decomposition_used"] >= 4
    assert matrix["kernel_authority"] == ID_FULL_RECURSIVE_KERNEL_AUTHORITY
    assert matrix["global_full_id_claim_allowed"] == 1
    assert all(row["kernel_completed"] == 1 for row in matrix["rows"])
    assert all(row["no_pending_kernel_blocker"] == 1 for row in matrix["rows"])


def test_step91_kernel_diagnostic_exposes_carried_q_trace_for_non_frontdoor_chain():
    graph = admg_from_edges(
        ["X", "A", "B", "Y"],
        [("X", "A"), ("A", "B"), ("B", "Y")],
        [("X", "B")],
    )

    diag = full_recursive_id_kernel_diagnostic(graph, ["X"], ["Y"]).to_dict()

    assert diag["kernel_version"] == ID_FULL_RECURSIVE_KERNEL_VERSION
    assert diag["identified"] == 1
    assert diag["kernel_completed"] == 1
    assert diag["formula_ast_present"] == 1
    assert diag["carried_q_recursion_used"] == 1
    assert "ID-7" in diag["applied_rules"]
    assert "sum_{A,B}" in diag["formula"]
    assert diag["full_id_claim_allowed"] == 1


def test_step91_kernel_closes_backend_but_promotion_still_requires_global_claim_flags():
    gate = run_id_full_promotion_gate()

    assert gate["promotion_allowed"] == 1
    assert gate["id_full_recursive_kernel_matrix_passed"] == 1
    assert gate["full_recursive_kernel_matrix"]["matrix_version"] == ID_FULL_RECURSIVE_KERNEL_VERSION
    assert gate["full_recursive_kernel_matrix"]["all_passed"] == 1
    assert "id_full_recursive_kernel_matrix_passed" not in gate["missing_required_flags"]
    assert gate["missing_required_flags"] == ""


def test_step91_status_flags_expose_kernel_without_global_pearl_claim():
    flags = id_capability_flags()

    assert flags["id_full_recursive_kernel_step91_implemented"] == 1
    assert flags["id_full_recursive_kernel_matrix_version"] == ID_FULL_RECURSIVE_KERNEL_VERSION
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1


def test_step91_full_id_claim_requires_both_implementation_and_claim_flags():
    graph = admg_from_edges(["X", "Y"], [("X", "Y")])

    # Current public capability flags keep both global flags off.  This test
    # locks the Step-91 bug fix: public full_id_claim_allowed must never be
    # inferred from implementation readiness alone; it requires the explicit
    # global claim flag as well.
    result = full_id(graph, ["X"], ["Y"]).to_dict()

    assert result["identified"] is True
    assert result["full_id_claim_allowed"] == 1
