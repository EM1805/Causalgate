import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_algorithm import identify_effect, id_algorithm_summary
from scm_parts.id_recursive_expression import recursive_id_set_expression_diagnostic
from scm_parts.id_status import id_capability_flags


def _payload(expr):
    return json.loads(expr.expression_json)


def _walk(node):
    yield node
    for child in node.get("children", []):
        yield from _walk(child)


def test_observed_dag_recursive_expression_builds_ast_at_runtime():
    g = admg_from_edges(["X", "Y", "Z"], [("X", "Y"), ("Z", "Y")], [])
    expr = recursive_id_set_expression_diagnostic(g, ["X"], ["Y"])
    payload = _payload(expr)

    assert expr.expression_identified is True
    assert payload["formula_ast_version"] == "id_ast_v1"
    assert payload["formula_ast_source"] == "internal_recursive_builder_step43"
    assert payload["formula_ast_runtime_used"] == 1
    assert payload["formula_ast"]["node_type"] == "do"
    assert any(n["node_type"] == "probability" for n in _walk(payload["formula_ast"]))


def test_full_district_q_factor_branch_builds_q_ast_at_runtime():
    g = admg_from_edges(["X", "Y", "Z"], [("X", "Y")], [("Y", "Z")])
    expr = recursive_id_set_expression_diagnostic(g, ["X"], ["Y", "Z"])
    payload = _payload(expr)

    assert expr.expression_identified is True
    assert expr.expression_status == "identified_q_factor_full_district"
    assert payload["formula_ast_source"] == "internal_recursive_builder_step43"
    assert payload["formula_ast_runtime_used"] == 1
    assert any(n["node_type"] == "q_factor" for n in _walk(payload["formula_ast"]))


def test_formal_hedge_fail_payload_uses_runtime_hedge_ast():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    row = identify_effect(g, "X", "Y").to_dict()
    payload = json.loads(row["recursive_expression_json"])

    assert row["identifiable"] is False
    assert row["formal_hedge_certified"] == 1
    assert payload["formula_ast_source"] == "internal_recursive_builder_step43"
    assert payload["formula_ast_runtime_used"] == 1
    assert payload["formula_ast"]["node_type"] == "hedge_fail"


def test_summary_exposes_ast_runtime_capability_flag():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [])
    summary = id_algorithm_summary(g, [identify_effect(g, "X", "Y").to_dict()])
    flags = id_capability_flags()

    assert flags["formula_ast_runtime_step43_implemented"] == 1
    assert summary["formula_ast_runtime_step43_implemented"] == 1
    assert "ast_runtime_step43" in summary["id_algorithm_status"]
