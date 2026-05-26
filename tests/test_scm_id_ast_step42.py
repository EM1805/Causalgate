import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_algorithm import identify_effect, identify_effect_set, id_algorithm_summary
from scm_parts.id_ast import P, Product, Sum, ast_to_json, payload_to_ast, parse_factor_term
from scm_parts.id_status import id_capability_flags


def _walk(node):
    yield node
    for child in node.get("children", []):
        yield from _walk(child)


def test_id_ast_basic_probability_sum_product_roundtrip():
    ast = Sum(["Z"], Product([parse_factor_term("P(Y | X,Z)"), parse_factor_term("P(Z)")]))
    payload = json.loads(ast_to_json(ast))

    assert payload["ast_version"] == "id_ast_v1"
    assert payload["node_type"] == "sum"
    assert payload["bound_variables"] == ["Z"]
    assert payload["children"][0]["node_type"] == "product"


def test_frontdoor_result_exposes_symbolic_formula_ast_and_recursive_ast():
    g = admg_from_edges(
        ["X", "Z", "Y"],
        [("X", "Z"), ("Z", "Y")],
        [("X", "Y")],
    )
    row = identify_effect(g, "X", "Y", mediators=["Z"]).to_dict()

    assert row["identifiable"] is True
    assert row["symbolic_formula_ast_json"]

    symbolic_ast = json.loads(row["symbolic_formula_ast_json"])
    assert symbolic_ast["ast_version"] == "id_ast_v1"
    assert symbolic_ast["node_type"] == "do"
    assert symbolic_ast["interventions"] == ["X"]

    recursive_payload = json.loads(row["recursive_expression_json"])
    assert recursive_payload["formula_ast_version"] == "id_ast_v1"
    assert recursive_payload["formula_ast"]["ast_version"] == "id_ast_v1"
    assert any(n["node_type"] == "probability" for n in _walk(recursive_payload["formula_ast"]))


def test_set_valued_recursive_result_carries_formula_ast_inside_expression_payload():
    g = admg_from_edges(["X", "Y", "Z"], [("X", "Y"), ("Z", "Y")], [])
    row = identify_effect_set(g, ["X"], ["Y", "Z"]).to_dict()

    assert row["identifiable"] is True
    payload = json.loads(row["recursive_expression_json"])
    assert payload["formula_ast_version"] == "id_ast_v1"
    assert payload["formula_ast"]["ast_version"] == "id_ast_v1"
    assert payload["formula_ast"]["node_type"] in {"do", "sum", "product", "probability"}


def test_nonidentification_hedge_expression_carries_hedge_fail_ast():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    row = identify_effect(g, "X", "Y").to_dict()

    assert row["identifiable"] is False
    assert row["formal_hedge_certified"] == 1
    payload = json.loads(row["recursive_expression_json"])
    assert payload["formula_ast_version"] == "id_ast_v1"
    assert payload["formula_ast"]["node_type"] == "hedge_fail"
    assert payload["formula_ast"]["metadata"]["F"] == ["X", "Y"]
    assert payload["formula_ast"]["metadata"]["F_prime"] == ["Y"]


def test_summary_exposes_formula_ast_capability_flag():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [])
    summary = id_algorithm_summary(g, [identify_effect(g, "X", "Y").to_dict()])
    flags = id_capability_flags()

    assert flags["formula_ast_step42_implemented"] == 1
    assert flags["formula_ast_version"] == "id_ast_v1"
    assert summary["formula_ast_step42_implemented"] == 1
    assert summary["formula_ast_version"] == "id_ast_v1"
