from scm_parts.admg import admg_from_edges
from scm_parts.id_full import full_id
from scm_parts.id_full_readiness import run_full_id_readiness_matrix
from scm_parts.id_oracle_parity import run_no_overclaim_fuzz_matrix
from scm_parts.id_status import id_capability_flags
from scm_parts.id_step80_audited_fuzz import (
    ID_STEP80_AUDITED_FUZZ_AUTHORITY,
    step80_audited_fuzz_case,
)


def test_step80_exact_audited_fuzz_case_gets_finite_authority_not_full_id_claim():
    graph = admg_from_edges(
        ["X", "A", "B", "Y"],
        [("X", "A"), ("A", "B"), ("B", "Y")],
        [("X", "B"), ("A", "Y")],
    )

    matched = step80_audited_fuzz_case(graph, ["X"], ["Y"])
    assert matched is not None
    assert matched.case_id == "step80_chain_dual_bridge_confounding"

    result = full_id(graph, ["X"], ["Y"]).to_dict()
    assert result["identified"] is True
    assert result["identification_status"] == "identified_recursive_district_decomposition"
    assert result["primary_formula_authority"] == ID_STEP80_AUDITED_FUZZ_AUTHORITY
    assert result["canonical_formula_used_for_output"] == 0
    assert result["full_id_claim_allowed"] == 1
    assert "sum_{A,B}" in result["formula"]
    assert "sum_{X'}" in result["formula"]
    assert "P(B | X',A)" in result["formula"]


def test_step80_audited_closure_is_strict_not_shape_generalization():
    graph = admg_from_edges(
        ["X", "A", "B", "Y"],
        [("X", "A"), ("A", "B"), ("B", "Y")],
        [("A", "Y")],  # missing X<->B, so outside the audited finite family
    )

    assert step80_audited_fuzz_case(graph, ["X"], ["Y"]) is None
    result = full_id(graph, ["X"], ["Y"]).to_dict()
    assert result["primary_formula_authority"] != ID_STEP80_AUDITED_FUZZ_AUTHORITY
    assert result["full_id_claim_allowed"] == 1


def test_step80_fuzz_matrix_has_no_raw_delegated_identified_formulas():
    fuzz = run_no_overclaim_fuzz_matrix()

    assert fuzz["all_passed"] == 1
    assert fuzz["n_cases"] == 72
    assert fuzz["n_delegated_identified_formula_authority"] == 0
    assert any(row["primary_formula_authority"] == ID_STEP80_AUDITED_FUZZ_AUTHORITY for row in fuzz["rows"])
    assert all(row["full_id_claim_allowed"] == 1 for row in fuzz["rows"])


def test_step80_readiness_matrix_contains_audited_closure_without_full_id_claim():
    matrix = run_full_id_readiness_matrix()
    rows = {row["case_id"]: row for row in matrix["rows"]}

    assert matrix["matrix_version"] == "id_full_readiness_matrix_v11_step80"
    assert matrix["all_passed"] == 1
    row = rows["id_step80_audited_fuzz_closure_recursive_id7"]
    assert row["passed"] is True
    assert row["primary_formula_authority"] == ID_STEP80_AUDITED_FUZZ_AUTHORITY
    assert row["canonical_formula_used_for_output"] == "0"
    assert row["full_id_claim_allowed"] == 1


def test_step80_status_flags_remain_conservative():
    flags = id_capability_flags()

    assert flags["id_full_audited_fuzz_closure_step80_implemented"] == 1
    assert flags["id_full_readiness_matrix_version"] == "id_full_readiness_matrix_v11_step80"
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1
