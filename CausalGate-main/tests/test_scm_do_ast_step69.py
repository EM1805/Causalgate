import json

from scm_parts.do_ast import (
    DO_AST_VERSION,
    DoProof,
    DoRewriteStep,
    P_do,
    expression_from_dict,
    expression_latex,
    parse_do_expression,
    proof_from_dict,
)
from scm_parts.admg import admg_from_edges
from scm_parts.do_calculus import rule1_insertion_deletion_observation


def test_do_ast_roundtrip_probability_expression():
    expr = P_do(["y"], interventions=["x"], observations=["z", "z", "w"], label="query")
    payload = expr.to_dict()
    assert payload["ast_version"] == DO_AST_VERSION
    assert payload["node_type"] == "do_probability"
    assert payload["outcomes"] == ["y"]
    assert payload["interventions"] == ["x"]
    assert payload["observations"] == ["z", "w"]
    assert payload["is_observational"] is False
    assert payload["formula"] == "P(y|do(x),z,w)"

    restored = expression_from_dict(payload)
    assert restored == expr
    assert expression_latex(restored) == "P(y \\mid do(x),z,w)"


def test_do_ast_parser_separates_do_and_observations():
    expr = parse_do_expression("P(y|do(x),do(z),w)")
    assert expr.outcomes == ("y",)
    assert expr.interventions == ("x", "z")
    assert expr.observations == ("w",)
    assert expr.metadata["parse_status"] == "ok"


def test_do_ast_rewrite_and_proof_shell_preserve_audit_only_authority():
    before = P_do(["y"], interventions=["x", "z"], observations=["w"], label="before")
    after = before.exchange_intervention_for_observation(["z"], label="after")
    step = DoRewriteStep(
        rule="rule2_action_observation_exchange",
        before=before,
        after=after,
        applicable=True,
        premise="Y independent of Z given X,W in G_bar_X_under_Z",
        graph_variant="G_bar_X_under_Z",
        reason_codes="RULE2_DSEP_Y_Z_G_BAR_X_UNDER_Z",
    )
    proof = DoProof(query=before, steps=(step,))
    payload = proof.to_dict()
    assert payload["authority"] == "audit_only"
    assert payload["terminal"]["formula"] == "P(y|do(x),z,w)"
    assert proof_from_dict(payload).terminal_expression.to_formula() == "P(y|do(x),z,w)"


def test_do_calculus_rule_trace_now_carries_do_ast_json():
    g = admg_from_edges(["x", "z", "y"], [("x", "z"), ("z", "y")])
    diag = rule1_insertion_deletion_observation(g, y="y", x="x", z="z")
    before_ast = json.loads(diag.expression_before_ast_json)
    after_ast = json.loads(diag.expression_after_ast_json)
    assert before_ast["ast_version"] == DO_AST_VERSION
    assert before_ast["formula"] == diag.expression_before
    assert after_ast["formula"] == diag.expression_after
    assert before_ast["metadata"]["authority"] == "audit_only"
