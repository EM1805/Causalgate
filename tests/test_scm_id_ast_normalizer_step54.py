import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_ast import FormulaAST, P, Product, Sum
from scm_parts.id_ast_normalizer import ID_AST_NORMALIZER_VERSION, normalize_formula_ast
from scm_parts.id_full import full_id
from scm_parts.id_recursive_expression import recursive_id_set_expression_diagnostic
from scm_parts.id_status import id_capability_flags


def test_step54_normalizer_flattens_product_and_marks_metadata():
    ast = Product([P(["B"]), Product([P(["A"]), P(["C"])])])
    norm = normalize_formula_ast(ast)
    payload = norm.to_dict()

    assert payload["node_type"] == "product"
    assert payload["metadata"]["formula_ast_normalized"] == 1
    assert payload["metadata"]["formula_ast_normalizer_version"] == ID_AST_NORMALIZER_VERSION
    assert len(payload["children"]) == 3
    assert all(child["metadata"]["formula_ast_normalized"] == 1 for child in payload["children"])


def test_step54_expression_payload_serializes_normalized_ast_for_observed_dag():
    graph = admg_from_edges(["X", "Z", "Y"], [("X", "Z"), ("Z", "Y")], [])
    expr = recursive_id_set_expression_diagnostic(graph, ["X"], ["Y"])
    payload = json.loads(expr.expression_json)
    ast = payload["formula_ast"]

    assert expr.expression_identified is True
    assert payload["formula_ast_normalized"] == 1
    assert payload["formula_ast_normalizer_version"] == ID_AST_NORMALIZER_VERSION
    assert ast["metadata"]["formula_ast_normalized"] == 1
    assert ast["metadata"]["formula_ast_normalizer_version"] == ID_AST_NORMALIZER_VERSION


def test_step54_full_id_exposes_normalized_ast_without_full_id_claim():
    graph = admg_from_edges(["X", "Z", "Y"], [("X", "Z"), ("Z", "Y")], [])
    result = full_id(graph, "X", "Y").to_dict()
    ast = json.loads(result["formula_ast_json"])
    flags = id_capability_flags()

    assert result["identified"] is True
    assert ast["metadata"]["formula_ast_normalized"] == 1
    assert flags["id_full_formula_ast_normalizer_step54_implemented"] == 1
    assert flags["full_recursive_id_implemented"] == 1
    assert result["full_id_claim_allowed"] == 1


def test_step54_hedge_ast_is_normalized_for_fail_branch():
    graph = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    expr = recursive_id_set_expression_diagnostic(graph, ["X"], ["Y"])
    payload = json.loads(expr.expression_json)
    ast = payload["formula_ast"]

    assert expr.expression_identified is False
    assert ast["node_type"] in {"hedge_fail", "placeholder"}
    assert ast["metadata"]["formula_ast_normalized"] == 1
