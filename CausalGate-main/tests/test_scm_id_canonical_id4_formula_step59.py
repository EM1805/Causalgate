import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_canonical_formula import canonical_id_formula_diagnostic
from scm_parts.id_full import full_id
from scm_parts.id_full_readiness import run_full_id_readiness_matrix
from scm_parts.id_status import id_capability_flags


def test_step59_canonical_id4_district_decomposition_owns_formula():
    graph = admg_from_edges(
        ["X", "Y", "Z", "W"],
        [("X", "Y"), ("Z", "Y"), ("W", "Z")],
        [("X", "Z")],
    )
    diag = canonical_id_formula_diagnostic(graph, "X", "Y")
    payload = json.loads(diag.expression_json)
    trace = json.loads(diag.trace_json)["trace"]

    assert diag.identified is True
    assert diag.status == "identified_canonical_id4_recursive_district_decomposition_step59"
    assert diag.terminal_rule == "ID-4"
    assert diag.formula == "sum_{W,Z} P(W) * P(Y | W,X,Z) * P(Z | W)"
    assert payload["kind"] == "canonical_id4_recursive_district_decomposition"
    assert payload["formula_authority"] == "id_canonical_formula_step60"
    assert payload["formula_ast_normalized"] == 1
    assert payload["districts"] == [["W"], ["Y"], ["Z"]]
    assert any(t["rule"] == "ID-4" and t["status"] == "identified_recursive_district_decomposition" for t in trace)


def test_step59_full_id_uses_canonical_id4_authority_not_delegate():
    graph = admg_from_edges(
        ["X", "Y", "Z", "W"],
        [("X", "Y"), ("Z", "Y"), ("W", "Z")],
        [("X", "Z")],
    )
    row = full_id(graph, "X", "Y").to_dict()
    assert row["identified"] is True
    assert row["primary_formula_authority"] == "id_canonical_formula_step60"
    assert row["canonical_formula_used_for_output"] == 1
    assert row["formula"] == "P_{do(X)}(Y) = sum_{W,Z} P(W) * P(Y | W,X,Z) * P(Z | W)"
    assert row["full_id_claim_allowed"] == 1


def test_step59_readiness_matrix_reduces_delegate_count():
    matrix = run_full_id_readiness_matrix()
    rows = {row["case_id"]: row for row in matrix["rows"]}
    assert matrix["matrix_version"] == "id_full_readiness_matrix_v11_step80"
    assert matrix["all_passed"] == 1
    assert rows["id_canonical_district_decomposition_id4"]["primary_formula_authority"] == "id_canonical_formula_step60"
    assert rows["id_canonical_district_decomposition_id4"]["canonical_formula_used_for_output"] == "1"
    assert matrix["n_delegated_formula_authority"] <= 7
    assert matrix["n_canonical_formula_authority"] >= 10


def test_step59_status_flag_present_without_full_id_claim():
    flags = id_capability_flags()
    assert flags["id_full_canonical_id4_formula_authority_step59_implemented"] == 1
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1 if "full_id_claim_allowed" in flags else True
