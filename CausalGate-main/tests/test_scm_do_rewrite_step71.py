from scm_parts.admg import admg_from_edges
from scm_parts.do_ast import P_do
from scm_parts.do_rewrite import (
    DO_REWRITE_AUTHORITY,
    candidate_rewrites,
    proof_shell_from_rewrites,
    rule2_rewrite,
)


def test_do_rewrite_converts_rule_diagnostic_to_ast_step():
    g = admg_from_edges(["x", "z", "y"], [("x", "z"), ("z", "y")])
    audit = rule2_rewrite(g, y="y", x="x", z="z")
    assert audit.authority == DO_REWRITE_AUTHORITY
    assert audit.step.rule == "rule2_action_observation_exchange"
    assert audit.step.before.to_formula() == "P(y|do(x,z))"
    assert audit.step.after.to_formula() == "P(y|do(x),z)"
    assert audit.to_dict()["step"]["before"]["node_type"] == "do_probability"


def test_candidate_rewrites_and_proof_shell_remain_audit_only():
    g = admg_from_edges(["x", "z", "y"], [("x", "z"), ("z", "y")])
    query = P_do(["y"], interventions=["x", "z"])
    audits = candidate_rewrites(g, y="y", x="x", candidate_z=["z"])
    proof = proof_shell_from_rewrites(query, audits)
    assert proof.authority == "audit_only"
    assert proof.status == "rewrite_shell_audit_only"
    assert proof.metadata["candidate_count"] == 3
    assert proof.terminal_expression.to_formula().startswith("P(")
