from scm_parts.admg import admg_from_edges
from scm_parts.id_full import full_id
from scm_parts.id_full_promotion_gate import run_id_full_promotion_gate
from scm_parts.id_full_recursive_authority_coverage import run_full_recursive_authority_coverage_matrix
from scm_parts.id_full_recursive_trace_authority import (
    FULL_RECURSIVE_TRACE_FORMULA_AUTHORITY,
    ID_FULL_RECURSIVE_TRACE_AUTHORITY_VERSION,
    recursive_trace_authority_for_result,
)
from scm_parts.id_status import id_capability_flags


def test_step86_trace_authority_certifies_supported_identified_full_id_result():
    graph = admg_from_edges(["X", "Z", "Y"], [("X", "Z"), ("Z", "Y")], [("X", "Y")])
    result = full_id(graph, ["X"], ["Y"]).to_dict()
    cert = recursive_trace_authority_for_result(result).to_dict()

    assert cert["trace_authority_version"] == ID_FULL_RECURSIVE_TRACE_AUTHORITY_VERSION
    assert cert["certified"] == 1
    assert cert["authority"] == FULL_RECURSIVE_TRACE_FORMULA_AUTHORITY
    assert cert["status"] == "full_recursive_trace_certified_step86"
    assert "ID-7" in cert["rules"]
    assert cert["full_id_claim_allowed"] == 1
    assert result["full_id_claim_allowed"] == 1


def test_step86_coverage_promotes_all_public_identified_rows_to_trace_authority():
    matrix = run_full_recursive_authority_coverage_matrix()

    assert matrix["matrix_version"] == "id_full_recursive_authority_coverage_v2_step86"
    assert matrix["n_identified_formula_rows_audited"] == 78
    assert matrix["n_full_recursive_formula_authority"] == 78
    assert matrix["n_recursive_trace_certified_formula_authority"] == 78
    assert matrix["n_finite_or_template_formula_authority"] == 0
    assert matrix["n_primary_finite_or_template_formula_authority"] == 78
    assert matrix["pearl_formula_authority_coverage_complete"] == 1
    assert matrix["full_id_claim_allowed"] == 1
    assert all(row["promotion_complete"] == 1 for row in matrix["rows"])


def test_step86_promotion_gate_passes_after_step94_global_full_id_flags():
    gate = run_id_full_promotion_gate()

    assert gate["matrix_version"] == "id_full_promotion_gate_v7_step94"
    assert gate["promotion_allowed"] == 1
    assert gate["full_recursive_formula_authority_present"] == 1
    assert gate["no_finite_or_template_only_formula_authority_for_promotion"] == 1
    assert gate["pearl_formula_authority_coverage_complete"] == 1
    assert gate["missing_required_flags"] == ""
    assert gate["full_id_claim_allowed_after_promotion_gate"] == 1


def test_step86_status_flags_are_explicit_and_global_claim_stays_red():
    flags = id_capability_flags()

    assert flags["id_full_recursive_trace_authority_step86_implemented"] == 1
    assert flags["id_full_recursive_authority_coverage_version"] == "id_full_recursive_authority_coverage_v2_step86"
    assert flags["id_full_promotion_gate_version"] == "id_full_promotion_gate_v7_step94"
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1
