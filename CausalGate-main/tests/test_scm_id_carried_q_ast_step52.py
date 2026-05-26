import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_carried_q import CARRIED_Q_CONTEXT_VERSION, build_carried_q_context
from scm_parts.id_full import full_id
from scm_parts.id_recursive_expression import recursive_id_set_expression_diagnostic
from scm_parts.id_status import id_capability_flags
from scm_parts.q_factor import identify_q_factor


def test_step52_carried_q_context_exposes_formula_ast():
    g = admg_from_edges(["X", "Z", "Y"], [("X", "Z"), ("Z", "Y")], [("X", "Y")])
    ctx = build_carried_q_context(
        g,
        ["X", "Y"],
        source_scope=["X", "Z", "Y"],
        source_terms=["P(X)", "P(Z | X)", "P(Y | X,Z)"],
        source_name="Q[X,Z,Y]",
    )

    assert ctx.context_version == CARRIED_Q_CONTEXT_VERSION
    assert ctx.formula == "Q[X,Y] = P(X) * P(Y | X,Z)"
    assert ctx.formula_ast["node_type"] == "q_factor"
    assert ctx.formula_ast["variables"] == ["X", "Y"]
    assert ctx.formula_ast["metadata"]["source_name"] == "Q[X,Z,Y]"
    assert ctx.formula_ast["metadata"]["projected_from_source"] == 1
    assert ctx.formula_ast["children"][0]["node_type"] in {"product", "probability"}


def test_step52_recursive_payload_carries_context_ast_on_id7_branch():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    expr = recursive_id_set_expression_diagnostic(g, ["X"], ["Y"])
    payload = json.loads(expr.expression_json)
    sub = payload["subexpressions"][0]
    ctx = sub["carried_q_context"]

    assert ctx["context_version"] == CARRIED_Q_CONTEXT_VERSION
    assert ctx["formula"] == "Q[X,Y] = P(X) * P(Y | X)"
    assert ctx["formula_ast"]["node_type"] == "q_factor"
    assert ctx["formula_ast"]["metadata"]["context_version"] == CARRIED_Q_CONTEXT_VERSION
    assert sub["step51_carried_q_context_enabled"] == 1


def test_step52_full_id_exposes_carried_q_formula_ast_without_claim():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    result = full_id(g, "X", "Y").to_dict()
    ctx = json.loads(result["carried_q_context_json"])
    ctx_ast = json.loads(result["carried_q_formula_ast_json"])
    flags = id_capability_flags()

    assert result["identified"] is False
    assert result["carried_q_context_enabled"] == 1
    assert ctx["formula_ast"]["node_type"] == "q_factor"
    assert ctx_ast["node_type"] == "q_factor"
    assert flags["id_full_carried_q_context_step51_implemented"] == 1
    assert flags["id_full_carried_q_ast_step52_implemented"] == 1
    assert flags["full_recursive_id_implemented"] == 1
    assert result["full_id_claim_allowed"] == 1


def test_step52_q_factor_payload_inherits_carried_q_ast():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    qdiag = identify_q_factor(
        g,
        ["Y"],
        containing_district=["X", "Y"],
        outcome_set=["Y"],
        intervention_set=["X"],
    )
    payload = json.loads(qdiag.q_factor_json)
    ctx = payload["carried_q_context"]

    assert qdiag.q_factor_status == "blocked_general_q_input_recursion_formal_hedge"
    assert ctx["formula_ast"]["node_type"] == "q_factor"
    assert ctx["formula_ast"]["metadata"]["context_version"] == CARRIED_Q_CONTEXT_VERSION
