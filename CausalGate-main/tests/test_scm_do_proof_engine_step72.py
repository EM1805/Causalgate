from scm_parts.admg import admg_from_edges
from scm_parts.do_ast import P_do
from scm_parts.do_proof_engine import (
    DO_PROOF_ENGINE_AUTHORITY,
    bounded_do_proof,
    bounded_do_proof_from_expression,
    bounded_do_proof_from_formula,
)


def test_bounded_do_proof_already_observational_query():
    g = admg_from_edges(["x", "y"], [("x", "y")])
    result = bounded_do_proof_from_expression(g, P_do(["y"], observations=["x"]))
    payload = result.to_dict()
    assert result.authority == DO_PROOF_ENGINE_AUTHORITY
    assert payload["status"] == "proof_found_observational_audit_only"
    assert payload["terminal_observational"] == 1
    assert payload["terminal_formula"] == "P(y|x)"
    assert payload["proof"]["authority"] == "audit_only"


def test_bounded_do_proof_can_apply_state_matched_rule2_but_not_overclaim_id():
    g = admg_from_edges(["x", "z", "y"], [("x", "z"), ("z", "y")])
    result = bounded_do_proof_from_formula(g, "P(y|do(x),do(z))", max_depth=2)
    payload = result.to_dict()
    assert payload["authority"] == "audit_only"
    assert payload["status"] in {"bounded_rewrite_progress_audit_only", "proof_found_observational_audit_only"}
    assert payload["proof"]["steps"]
    assert payload["proof"]["steps"][0]["rule"] == "rule2_action_observation_exchange"
    assert payload["terminal_formula"] == "P(y|do(x),z)"
    assert payload["terminal_observational"] == 0


def test_standard_do_query_uses_canonical_empty_backdoor_template_step74():
    g = admg_from_edges(["x", "z", "y"], [("x", "z"), ("z", "y")])
    result = bounded_do_proof(g, "x", "y", max_depth=2)
    assert result.status == "canonical_backdoor_template_proof_audit_only"
    assert result.terminal.to_formula() == "P(y|x)"
    assert result.terminal_observational == 1
    assert "CANONICAL_BACKDOOR_TEMPLATE_DSEP_VERIFIED_AUDIT_ONLY" in result.reason_codes


def test_bounded_do_proof_blocks_directed_cycles():
    g = admg_from_edges(["x", "y"], [("x", "y"), ("y", "x")])
    result = bounded_do_proof(g, "x", "y")
    assert result.status == "blocked_directed_cycle"
    assert result.reason_codes == "DIRECTED_CYCLE_NOT_ADMG_DAG"
