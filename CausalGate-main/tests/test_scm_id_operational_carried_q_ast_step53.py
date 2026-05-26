import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_carried_q import build_carried_q_context
from scm_parts.id_full import ID_FULL_INTERFACE_VERSION, full_id
from scm_parts.id_recursive_expression import _recursive_id_expression, recursive_id_set_expression_diagnostic
from scm_parts.id_status import id_capability_flags
from scm_parts.q_factor import identify_q_factor


def test_step53_carried_q_ast_is_operational_in_q_input_base_case():
    graph = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    ctx = build_carried_q_context(graph, ["X", "Y"], name="Q[X,Y]")

    expr = _recursive_id_expression(
        graph,
        ["Y"],
        [],
        q_input_scope=list(ctx.scope),
        q_input_terms=list(ctx.terms),
        q_input_name=ctx.name,
        q_input_formula_ast=ctx.formula_ast,
    )
    payload = json.loads(expr.expression_json)
    ast = payload["formula_ast"]
    trace = json.loads(expr.trace_json)["trace"]

    assert expr.expression_identified is True
    assert expr.reason_codes == "Q_INPUT_NO_INTERVENTION_BASE_CASE_STEP53"
    assert ast["node_type"] == "sum"
    q_node = ast["children"][0]
    assert q_node["node_type"] == "q_factor"
    assert q_node["metadata"]["operational_carried_q_ast_step53"] == 1
    assert any(step.get("formula_ast_source") == "operational_carried_q_ast_step53" for step in trace)


def test_step53_general_id7_payload_exports_operational_q_ast():
    graph = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    expr = recursive_id_set_expression_diagnostic(graph, ["X"], ["Y"])
    payload = json.loads(expr.expression_json)
    sub = payload["subexpressions"][0]
    trace = json.loads(expr.trace_json)["trace"]

    assert sub["step51_carried_q_context_enabled"] == 1
    assert sub["step53_operational_carried_q_ast_enabled"] == 1
    assert sub["q_input_formula_ast"]["node_type"] == "q_factor"
    assert any(step["step"] == "q_input_general_carried_q_ast_step53" for step in trace)


def test_step53_full_id_reports_operational_carried_q_ast_without_claim():
    graph = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    result = full_id(graph, "X", "Y").to_dict()
    flags = id_capability_flags()

    assert result["interface_version"] == ID_FULL_INTERFACE_VERSION
    assert result["identified"] is False
    assert result["carried_q_context_enabled"] == 1
    assert result["carried_q_operational_ast_enabled"] == 1
    assert flags["id_full_operational_carried_q_ast_step53_implemented"] == 1
    assert flags["full_recursive_id_implemented"] == 1
    assert result["full_id_claim_allowed"] == 1


def test_step53_q_factor_delegates_operational_q_ast_to_recursive_runtime():
    graph = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    qdiag = identify_q_factor(
        graph,
        ["Y"],
        containing_district=["X", "Y"],
        outcome_set=["Y"],
        intervention_set=["X"],
    )
    payload = json.loads(qdiag.q_factor_json)

    assert qdiag.q_factor_status == "blocked_general_q_input_recursion_formal_hedge"
    assert payload["step53_operational_carried_q_ast_enabled"] == 1
    assert payload["q_input_formula_ast"]["node_type"] == "q_factor"
