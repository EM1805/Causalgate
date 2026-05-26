from __future__ import annotations

import json
from pathlib import Path

from causalgate.math_hypothesis import (
    evaluate_lean_gate,
    evaluate_math_claim,
    finite_identity_example,
    recommend_next_lemmas,
    riemann_overclaim_example,
    run_math_hypothesis_loop,
)
from causalgate.mcp.schemas import list_tool_schemas
from causalgate.mcp.tools import call_tool
from scm_parts.id_math_hypothesis_loop_readiness import (
    MATH_HYPOTHESIS_LOOP_READINESS_VERSION,
    math_hypothesis_loop_readiness_digest,
    run_math_hypothesis_loop_readiness,
)
from scm_parts.id_status import id_capability_flags


def test_step99_veto_blocks_riemann_proof_overclaim() -> None:
    verdict = evaluate_math_claim(riemann_overclaim_example())

    assert verdict["matrix_version"] == "math_hypothesis_veto_v1_step99"
    assert verdict["decision"] == "VETO_OVERCLAIM"
    assert verdict["open_problem_detected"] == "riemann_hypothesis"
    assert verdict["claim_level_downgraded"] is True
    assert "PROOF_OVERCLAIM_WITHOUT_TRUSTED_FORMAL_ATTESTATION" in verdict["reason_codes"]
    assert verdict["max_allowed_claim_level"] in {"conjecture_candidate", "proof_sketch_only"}


def test_step99_loop_revises_riemann_into_bounded_claim() -> None:
    result = run_math_hypothesis_loop({"math_claim": riemann_overclaim_example(), "max_rounds": 2, "auto_revise": True})

    assert result["matrix_version"] == "math_hypothesis_dialogue_loop_v1_step99"
    assert result["proof_overclaim_blocked"] == 1
    assert result["open_problem_detected"] == "riemann_hypothesis"
    assert result["veto_history"][0] == "VETO_OVERCLAIM"
    first_revision = result["turns"][0]["revised_claim"]
    assert first_revision["claim_level"] in {"conjecture_candidate", "proof_sketch_only"}
    assert "not a proof" in first_revision["claim"]
    assert result["dialogue_digest"]


def test_step99_lemma_recommender_outputs_riemann_proof_obligations() -> None:
    verdict = evaluate_math_claim(riemann_overclaim_example())
    recs = recommend_next_lemmas(riemann_overclaim_example(), verdict)

    obligation_ids = {item["id"] for item in recs["proof_obligations"]}
    assert recs["matrix_version"] == "math_lemma_recommender_v1_step99"
    assert "rh_scope_definition" in obligation_ids
    assert "first_unverified_inference" in obligation_ids
    assert recs["next_llm_instruction"].startswith("Revise the claim")


def test_step99_finite_identity_is_approved_only_with_limits() -> None:
    result = run_math_hypothesis_loop({"math_claim": finite_identity_example(), "max_rounds": 2})

    assert result["final_decision"] == "APPROVE_WITH_LIMITS"
    assert result["final_proof_authority"] == "proof_sketch_only"
    assert result["max_allowed_claim_level"] == "proof_sketch_only"
    assert result["proof_overclaim_blocked"] == 0


def test_step99_lean_gate_requires_trusted_external_attestation() -> None:
    untrusted = evaluate_lean_gate({
        "claim": "For all n, n = n.",
        "claim_level": "formal_proof_claimed",
        "formal_system": "Lean4",
        "formal_statement": "theorem self_eq (n : Nat) : n = n := by rfl",
        "lean_code": "by rfl",
        "proof_checker_result": {"status": "accepted", "trusted": False},
    })
    trusted = evaluate_lean_gate({
        "claim": "For all n, n = n.",
        "claim_level": "formal_proof_claimed",
        "formal_system": "Lean4",
        "formal_statement": "theorem self_eq (n : Nat) : n = n := by rfl",
        "lean_code": "by rfl",
        "proof_checker_result": {"status": "accepted", "trusted": True},
    })

    assert untrusted["proof_status"] != "accepted_by_trusted_external_checker"
    assert "CHECKER_ATTESTATION_NOT_TRUSTED" in untrusted["reason_codes"]
    assert trusted["proof_status"] == "accepted_by_trusted_external_checker"
    assert trusted["proof_digest"] != untrusted["proof_digest"]


def test_step99_readiness_report_is_green_and_digest_bound() -> None:
    report = run_math_hypothesis_loop_readiness(include_demo_results=False)

    assert report["matrix_version"] == MATH_HYPOTHESIS_LOOP_READINESS_VERSION
    assert report["math_hypothesis_loop_readiness_allowed"] == 1
    assert report["step98_firewall_product_readiness_allowed"] == 1
    assert report["riemann_demo_first_decision"] == "VETO_OVERCLAIM"
    assert report["riemann_demo_proof_overclaim_blocked"] == 1
    assert report["finite_identity_demo_final_decision"] == "APPROVE_WITH_LIMITS"
    assert report["n_requirements_passed"] == report["n_requirements"]
    assert report["report_digest"] == math_hypothesis_loop_readiness_digest(report)

    tampered = dict(report)
    tampered["riemann_demo_proof_overclaim_blocked"] = 0
    assert math_hypothesis_loop_readiness_digest(tampered) != report["report_digest"]


def test_step99_mcp_schema_and_tool_expose_math_loop() -> None:
    names = {tool["name"] for tool in list_tool_schemas()}
    assert "causalgate_run_math_hypothesis_loop" in names

    sample = json.loads(Path("examples/inputs/sample_math_hypothesis_riemann_overclaim_step99.json").read_text(encoding="utf-8"))
    result = call_tool("causalgate_run_math_hypothesis_loop", sample)
    assert result["matrix_version"] == "math_hypothesis_dialogue_loop_v1_step99"
    assert result["proof_overclaim_blocked"] == 1


def test_step99_status_flags_are_exposed() -> None:
    flags = id_capability_flags()

    assert flags["math_hypothesis_dialogue_loop_step99_implemented"] == 1
    assert flags["math_hypothesis_dialogue_loop_version"] == "math_hypothesis_dialogue_loop_v1_step99"
    assert flags["math_hypothesis_loop_readiness_version"] == MATH_HYPOTHESIS_LOOP_READINESS_VERSION
