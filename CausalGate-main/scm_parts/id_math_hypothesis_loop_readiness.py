from __future__ import annotations

"""Step 99 readiness report for the Math Hypothesis Dialogue Loop.

The report binds the Step-98 Agent Action Firewall product surface to a new
mathematical hypothesis loop: LLM claim -> math veto -> lemma recommendations ->
revision -> re-check.  It is intentionally a no-overclaim release: the loop may
classify, veto, and recommend proof obligations, but it must not claim to solve
open problems automatically.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Dict, Mapping, Sequence

from causalgate.math_hypothesis import finite_identity_example, riemann_overclaim_example, run_math_hypothesis_loop
from .id_agent_action_firewall_product_readiness import run_agent_action_firewall_product_readiness


MATH_HYPOTHESIS_LOOP_READINESS_VERSION = "math_hypothesis_dialogue_loop_product_readiness_v1_step99"
MATH_HYPOTHESIS_LOOP_SCOPE = "llm_math_claim_veto_recommendation_revision_loop_step99"


@dataclass(frozen=True)
class MathLoopRequirement:
    requirement: str
    passed: bool
    observed: str
    expected: str
    blocker_class: str
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "pass", "passed", "complete", "green"}


def _req(name: str, passed: bool, observed: object, expected: object, blocker_class: str, reason: str) -> MathLoopRequirement:
    return MathLoopRequirement(name, bool(passed), str(observed), str(expected), blocker_class, reason)


def math_hypothesis_loop_readiness_digest(payload: Mapping[str, object]) -> str:
    normalized = dict(payload)
    normalized.pop("report_digest", None)
    raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def run_math_hypothesis_loop_readiness(
    *,
    firewall_report: Mapping[str, object] | None = None,
    include_demo_results: bool = True,
) -> Dict[str, object]:
    firewall = dict(firewall_report or run_agent_action_firewall_product_readiness(include_demo_results=False))
    riemann = run_math_hypothesis_loop({"math_claim": riemann_overclaim_example(), "max_rounds": 2, "auto_revise": True})
    finite = run_math_hypothesis_loop({"math_claim": finite_identity_example(), "max_rounds": 2, "auto_revise": True})

    riemann_turns = riemann.get("turns", []) or []
    first_riemann_decision = riemann_turns[0].get("verdict", {}).get("decision") if riemann_turns else ""
    riemann_revised_claim = (riemann_turns[0].get("revised_claim", {}) if riemann_turns else {}) or {}

    requirements: Sequence[MathLoopRequirement] = (
        _req(
            "step98_firewall_product_ready",
            bool(_truthy(firewall.get("firewall_product_readiness_allowed"))),
            firewall.get("firewall_product_readiness_allowed", 0),
            1,
            "agent_firewall_not_ready",
            "The math dialogue loop is a premium agent-facing module and requires the Step-98 Agent Action Firewall product surface to be green.",
        ),
        _req(
            "riemann_overclaim_vetoed",
            first_riemann_decision == "VETO_OVERCLAIM" and riemann.get("proof_overclaim_blocked") == 1,
            f"decision={first_riemann_decision};blocked={riemann.get('proof_overclaim_blocked')}",
            "decision=VETO_OVERCLAIM;blocked=1",
            "riemann_overclaim_not_vetoed",
            "A famous-open-problem proof claim must be vetoed unless independently verified and reviewed.",
        ),
        _req(
            "riemann_revision_downgrades_claim",
            riemann_revised_claim.get("claim_level") in {"conjecture_candidate", "proof_sketch_only"},
            riemann_revised_claim.get("claim_level", ""),
            "conjecture_candidate|proof_sketch_only",
            "riemann_revision_not_downgraded",
            "The loop must transform alleged RH proof wording into bounded conjecture/proof-sketch wording.",
        ),
        _req(
            "lemma_recommendations_present",
            bool(riemann_turns and riemann_turns[0].get("recommendations", {}).get("proof_obligations")),
            len(riemann_turns[0].get("recommendations", {}).get("proof_obligations", []) if riemann_turns else []),
            ">=1 proof obligation",
            "lemma_recommendations_missing",
            "The math critic must recommend smaller proof obligations after veto.",
        ),
        _req(
            "bounded_finite_identity_accepted_with_limits",
            finite.get("final_decision") == "APPROVE_WITH_LIMITS" and finite.get("final_proof_authority") == "proof_sketch_only",
            f"decision={finite.get('final_decision')};authority={finite.get('final_proof_authority')}",
            "APPROVE_WITH_LIMITS;proof_sketch_only",
            "bounded_identity_not_accepted_with_limits",
            "A safe theorem-like proof sketch should be allowed only with bounded proof-sketch authority unless formally verified.",
        ),
        _req(
            "dialogue_digests_present",
            bool(riemann.get("dialogue_digest") and finite.get("dialogue_digest")),
            f"rh={int(bool(riemann.get('dialogue_digest')))};finite={int(bool(finite.get('dialogue_digest')))}",
            "rh=1;finite=1",
            "dialogue_digest_missing",
            "Every loop result must be digest-bound for audit evidence.",
        ),
    )
    passed = sum(1 for req in requirements if req.passed)
    blockers = [req.blocker_class for req in requirements if not req.passed]
    report: Dict[str, object] = {
        "matrix_version": MATH_HYPOTHESIS_LOOP_READINESS_VERSION,
        "scope": MATH_HYPOTHESIS_LOOP_SCOPE,
        "product_name": "CausalGate Math Hypothesis Dialogue Loop",
        "product_positioning": "formal_math_hypothesis_critic_for_llm_veto_recommendation_revision_cycles",
        "math_hypothesis_loop_readiness_allowed": int(passed == len(requirements)),
        "step98_firewall_product_readiness_allowed": int(_truthy(firewall.get("firewall_product_readiness_allowed"))),
        "riemann_demo_first_decision": first_riemann_decision,
        "riemann_demo_final_decision": riemann.get("final_decision"),
        "riemann_demo_open_problem_detected": riemann.get("open_problem_detected"),
        "riemann_demo_proof_overclaim_blocked": int(riemann.get("proof_overclaim_blocked", 0) or 0),
        "riemann_demo_revised_claim_level": riemann_revised_claim.get("claim_level", ""),
        "finite_identity_demo_final_decision": finite.get("final_decision"),
        "finite_identity_demo_proof_authority": finite.get("final_proof_authority"),
        "n_requirements": len(requirements),
        "n_requirements_passed": passed,
        "n_blockers": len(blockers),
        "blocker_classes": "|".join(blockers),
        "requirements": [req.to_dict() for req in requirements],
    }
    if include_demo_results:
        report["riemann_demo"] = riemann
        report["finite_identity_demo"] = finite
    report["report_digest"] = math_hypothesis_loop_readiness_digest(report)
    return report


def write_math_hypothesis_loop_readiness(path: str = "out/math_hypothesis_loop_readiness_step99.json") -> Dict[str, object]:
    from pathlib import Path

    report = run_math_hypothesis_loop_readiness()
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return report


__all__ = [
    "MATH_HYPOTHESIS_LOOP_READINESS_VERSION",
    "math_hypothesis_loop_readiness_digest",
    "run_math_hypothesis_loop_readiness",
    "write_math_hypothesis_loop_readiness",
]
