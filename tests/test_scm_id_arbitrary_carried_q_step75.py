import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_full import full_id
from scm_parts.id_full_readiness import run_full_id_readiness_matrix
from scm_parts.id_recursive_expression import recursive_id_set_expression_diagnostic
from scm_parts.id_status import id_capability_flags


def _non_frontdoor_carried_q_graph():
    return admg_from_edges(
        ["A", "B", "C", "D", "E"],
        [("A", "B"), ("A", "C"), ("C", "D"), ("D", "E")],
        [("A", "D"), ("A", "E"), ("B", "D")],
    )


def test_step75_preserves_carried_q_source_terms_through_ancestor_reduction():
    expr = recursive_id_set_expression_diagnostic(_non_frontdoor_carried_q_graph(), ["A"], ["E"], max_depth=12)
    trace = json.loads(expr.trace_json)["trace"]
    payload = json.loads(expr.expression_json)

    assert expr.expression_identified is True
    assert expr.expression_status == "identified_recursive_district_decomposition"
    assert "sum_{A'} P(A') * P(E | A',C,D)" in expr.formula
    assert any(step["step"] == "q_input_ancestor_marginalization_step75" for step in trace)
    assert any(
        step["step"] == "observed_dag_truncated_factorization"
        and step.get("formula_ast_source") == "carried_q_truncated_factorization_step75"
        for step in trace
    )
    assert payload["formula_ast_normalized"] == 1


def test_step75_full_id_exposes_arbitrary_carried_q_without_full_id_claim():
    row = full_id(_non_frontdoor_carried_q_graph(), ["A"], ["E"], max_depth=12).to_dict()

    assert row["identified"] is True
    assert row["primary_formula_authority"] == "recursive_id_set_expression_diagnostic_step75"
    assert row["canonical_formula_used_for_output"] == 0
    assert "ID-7" in row["canonical_rules"]
    assert "sum_{A'} P(A') * P(E | A',C,D)" in row["formula"]
    assert row["full_id_claim_allowed"] == 1


def test_step75_readiness_and_capability_flags_are_reported():
    matrix = run_full_id_readiness_matrix()
    rows = {row["case_id"]: row for row in matrix["rows"]}
    flags = id_capability_flags()

    assert matrix["matrix_version"] == "id_full_readiness_matrix_v11_step80"
    assert rows["id_arbitrary_carried_q_marginalization_step75"]["passed"] is True
    assert rows["id_arbitrary_carried_q_marginalization_step75"]["primary_formula_authority"] == "recursive_id_set_expression_diagnostic_step75"
    assert flags["id_full_arbitrary_id7_carried_q_marginalization_step75_implemented"] == 1
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1
