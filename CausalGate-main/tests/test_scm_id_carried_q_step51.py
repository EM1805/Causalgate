import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_carried_q import build_carried_q_context, project_terms_to_scope
from scm_parts.id_full import full_id
from scm_parts.id_recursive_expression import recursive_id_set_expression_diagnostic
from scm_parts.id_status import id_capability_flags
from scm_parts.q_factor import identify_q_factor


def test_step51_carried_q_context_projects_source_terms():
    g = admg_from_edges(["X", "Z", "Y"], [("X", "Z"), ("Z", "Y")], [("X", "Y")])
    ctx = build_carried_q_context(
        g,
        ["X", "Y"],
        source_scope=["X", "Z", "Y"],
        source_terms=["P(X)", "P(Z | X)", "P(Y | X,Z)"],
        source_name="Q[X,Z,Y]",
    )

    assert ctx.name == "Q[X,Y]"
    assert ctx.scope == ("X", "Y")
    assert ctx.projected_from_source == 1
    assert ctx.projection_loss == 0
    assert list(ctx.terms) == ["P(X)", "P(Y | X,Z)"]
    assert project_terms_to_scope(ctx.terms, ["Y"]) == ["P(Y | X,Z)"]


def test_step51_recursive_id_payload_exposes_carried_q_context_before_hedge():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    expr = recursive_id_set_expression_diagnostic(g, ["X"], ["Y"])
    payload = json.loads(expr.expression_json)
    trace = json.loads(expr.trace_json)["trace"]
    sub = payload["subexpressions"][0]

    assert expr.expression_status == "blocked_formal_hedge_certificate"
    assert sub["step51_carried_q_context_enabled"] == 1
    assert sub["carried_q_context"]["name"] == "Q[X,Y]"
    assert sub["carried_q_context"]["scope"] == ["X", "Y"]
    assert any(step["step"] == "q_input_general_carried_q_recursion_step51" for step in trace)
    assert any(step["step"] == "q_input_general_recursion_step44" for step in trace)


def test_step51_q_factor_diagnostic_uses_same_carried_q_context():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    qdiag = identify_q_factor(
        g,
        ["Y"],
        containing_district=["X", "Y"],
        outcome_set=["Y"],
        intervention_set=["X"],
    )
    payload = json.loads(qdiag.q_factor_json)

    assert qdiag.q_factor_status == "blocked_general_q_input_recursion_formal_hedge"
    assert payload["step51_carried_q_context_enabled"] == 1
    assert payload["carried_q_context"]["name"] == "Q[X,Y]"


def test_step51_full_id_reports_carried_q_context_without_full_id_claim():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    result = full_id(g, "X", "Y").to_dict()
    ctx = json.loads(result["carried_q_context_json"])
    flags = id_capability_flags()

    assert result["identified"] is False
    assert result["carried_q_context_enabled"] == 1
    assert ctx["name"] == "Q[X,Y]"
    assert flags["id_full_carried_q_context_step51_implemented"] == 1
    assert flags["full_recursive_id_implemented"] == 1
    assert result["full_id_claim_allowed"] == 1
