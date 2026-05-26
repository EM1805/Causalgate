from scm_parts.admg import admg_from_edges
from scm_parts.do_ast import DoProof, DoRewriteStep, P_do
from scm_parts.do_proof_engine import bounded_do_proof_from_formula
from scm_parts.do_proof_verifier import DO_PROOF_VERIFIER_VERSION, verify_do_proof


def test_step75_verifier_accepts_valid_bounded_trace_and_engine_exports_result():
    g = admg_from_edges(["x", "z", "y"], [("x", "z"), ("z", "y")])
    result = bounded_do_proof_from_formula(g, "P(y|do(x),do(z))", max_depth=2)
    payload = result.to_dict()
    verification = payload["proof_verification"]
    assert verification["verifier_version"] == DO_PROOF_VERIFIER_VERSION
    assert verification["valid"] == 1
    assert payload["proof_trace_valid"] == 1
    assert verification["authority"] == "audit_only"
    assert verification["terminal_formula"] == result.terminal.to_formula()


def test_step75_verifier_rejects_broken_step_chain():
    q = P_do(["y"], interventions=["x"])
    wrong_before = P_do(["y"], interventions=["z"])
    after = P_do(["y"], observations=["z"])
    step = DoRewriteStep(
        rule="rule2_action_observation_exchange",
        before=wrong_before,
        after=after,
        applicable=True,
        reason_codes="manual_broken_trace",
    )
    proof = DoProof(query=q, steps=(step,), status="bounded_rewrite_progress_audit_only")
    v = verify_do_proof(proof)
    assert v.valid == 0
    assert v.verification_status == "proof_trace_invalid_audit_only"
    assert "BROKEN_STEP_CHAIN" in v.reason_codes
    assert v.failed_step_index == 0


def test_step75_verifier_rejects_observational_status_with_do_terminal():
    q = P_do(["y"], interventions=["x"])
    proof = DoProof(query=q, status="proof_found_observational_audit_only", terminal=q)
    v = verify_do_proof(proof)
    assert v.valid == 0
    assert "OBSERVATIONAL_STATUS_WITH_DO_TERMINAL" in v.reason_codes


def test_step75_verifier_optionally_checks_graph_nodes():
    g = admg_from_edges(["x", "y"], [("x", "y")])
    q = P_do(["y"], interventions=["missing"])
    proof = DoProof(query=q, status="search_exhausted_audit_only", terminal=q)
    v = verify_do_proof(proof, admg=g)
    assert v.valid == 0
    assert "PROOF_REFERENCES_MISSING_GRAPH_NODE" in v.reason_codes
