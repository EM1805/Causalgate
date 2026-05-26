from __future__ import annotations

"""Mathematical proof-overclaim veto for LLM-generated hypotheses."""

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Dict, Mapping

from .claim_schema import MathClaimPackage, normalize_math_claim
from .lean_gate import evaluate_lean_gate


MATH_VETO_VERSION = "math_hypothesis_veto_v1_step99"

_OPEN_PROBLEM_TERMS = {
    "riemann": "riemann_hypothesis",
    "riemann hypothesis": "riemann_hypothesis",
    "riemann hypothes": "riemann_hypothesis",
    "p vs np": "p_vs_np",
    "p=np": "p_vs_np",
    "navier-stokes": "navier_stokes",
    "navier stokes": "navier_stokes",
    "birch": "birch_swinnerton_dyer",
    "hodge": "hodge_conjecture",
    "yang-mills": "yang_mills",
    "yang mills": "yang_mills",
    "collatz": "collatz_conjecture",
}

_PROOF_OVERCLAIM_PATTERNS = tuple(
    re.compile(r"(?<![\w])" + re.escape(term).replace(r"\ ", r"\s+") + r"(?![\w])", re.IGNORECASE)
    for term in sorted(
        {
            "proved",
            "proven",
            "proof complete",
            "i solved",
            "solved",
            "resolved",
            "dimostrato",
            "ho dimostrato",
            "risolto",
            "teorema dimostrato",
            "qed",
        },
        key=len,
        reverse=True,
    )
)


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _detect_open_problem(claim: MathClaimPackage) -> str:
    haystack = " ".join([claim.problem_name, claim.title, claim.claim]).lower()
    for term, canonical in _OPEN_PROBLEM_TERMS.items():
        if term in haystack:
            return canonical
    return ""


def _contains_proof_overclaim(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in _PROOF_OVERCLAIM_PATTERNS)


@dataclass
class MathVetoResult:
    matrix_version: str = MATH_VETO_VERSION
    decision: str = "REVISE"
    proof_authority: str = "proof_sketch_only"
    max_allowed_claim_level: str = "proof_sketch_only"
    claim_level_downgraded: bool = False
    open_problem_detected: str = ""
    proof_overclaim_detected: bool = False
    reason_codes: list[str] = field(default_factory=list)
    missing_items: list[str] = field(default_factory=list)
    required_next_steps: list[str] = field(default_factory=list)
    lean_gate: Dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""
    short_for_llm: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.short_for_llm:
            self.short_for_llm = {
                "decision": self.decision,
                "proof_authority": self.proof_authority,
                "max_allowed_claim_level": self.max_allowed_claim_level,
                "reason_codes": list(self.reason_codes),
                "required_next_steps": list(self.required_next_steps),
                "recommendation": self.recommendation,
                "math_rule": "Do not claim a theorem/proof unless a trusted formal checker attestation is accepted.",
            }

    def to_dict(self) -> Dict[str, Any]:
        if not self.short_for_llm:
            self.__post_init__()
        return asdict(self)


def evaluate_math_claim(payload: Mapping[str, Any] | MathClaimPackage) -> Dict[str, Any]:
    claim = normalize_math_claim(payload)
    missing = claim.missing_core_items()
    lean = evaluate_lean_gate(claim)
    open_problem = _detect_open_problem(claim)
    combined_text = " ".join([claim.title, claim.claim, claim.proof_sketch, claim.claim_level])
    proof_overclaim = _contains_proof_overclaim(combined_text) or claim.claim_level in {"formal_proof_claimed", "formally_verified_theorem"}
    accepted_by_checker = lean.get("proof_status") == "accepted_by_trusted_external_checker"
    reason_codes: list[str] = []
    required: list[str] = []

    if not claim.claim:
        return MathVetoResult(
            decision="VETO_MISSING_CLAIM",
            proof_authority="invalid_payload",
            max_allowed_claim_level="informal_idea",
            claim_level_downgraded=True,
            open_problem_detected=open_problem,
            proof_overclaim_detected=proof_overclaim,
            reason_codes=["MISSING_CLAIM"],
            missing_items=missing,
            required_next_steps=["state_a_precise_mathematical_claim"],
            lean_gate=lean,
            recommendation="Provide a precise mathematical statement before asking for proof critique.",
        ).to_dict()

    if claim.counterexamples:
        return MathVetoResult(
            decision="COUNTEREXAMPLE_FOUND",
            proof_authority="counterexample_candidate",
            max_allowed_claim_level="counterexample_candidate",
            claim_level_downgraded=True,
            open_problem_detected=open_problem,
            proof_overclaim_detected=proof_overclaim,
            reason_codes=["COUNTEREXAMPLE_SUPPLIED"],
            missing_items=missing,
            required_next_steps=["verify_counterexample_independently", "revise_or_reject_original_claim"],
            lean_gate=lean,
            recommendation="Treat the original claim as refuted pending independent verification of the counterexample.",
        ).to_dict()

    if accepted_by_checker and not open_problem:
        return MathVetoResult(
            decision="APPROVE_FORMAL_THEOREM",
            proof_authority="formally_verified_theorem",
            max_allowed_claim_level="formally_verified_theorem",
            open_problem_detected=open_problem,
            proof_overclaim_detected=proof_overclaim,
            reason_codes=["TRUSTED_FORMAL_CHECKER_ACCEPTED"],
            missing_items=[],
            required_next_steps=["preserve_checker_attestation", "cite_formal_system_and_artifact_digest"],
            lean_gate=lean,
            recommendation="The claim may be described as formally verified within the stated formal system and checker attestation.",
        ).to_dict()

    if accepted_by_checker and open_problem:
        # Still conservative for famous open problems: do not let a payload alone
        # market a solution without independent release/review workflow.
        reason_codes.extend(["OPEN_PROBLEM_DETECTED", "EXTERNAL_REVIEW_REQUIRED_FOR_FAMOUS_OPEN_PROBLEM"])
        required.extend(["independent_formal_artifact_review", "public_reproducibility_package", "expert_review_before_solution_claim"])
        return MathVetoResult(
            decision="REVIEW_FORMAL_OPEN_PROBLEM_CLAIM",
            proof_authority="trusted_checker_attestation_requires_external_review",
            max_allowed_claim_level="proof_obligation_candidate",
            claim_level_downgraded=True,
            open_problem_detected=open_problem,
            proof_overclaim_detected=proof_overclaim,
            reason_codes=reason_codes,
            missing_items=missing,
            required_next_steps=required,
            lean_gate=lean,
            recommendation="Do not announce the open problem as solved; route the checker artifact to independent expert/formal review.",
        ).to_dict()

    if proof_overclaim:
        reason_codes.append("PROOF_OVERCLAIM_WITHOUT_TRUSTED_FORMAL_ATTESTATION")
        if open_problem:
            reason_codes.append("OPEN_PROBLEM_DETECTED")
        required.extend(["downgrade_to_proof_sketch_or_conjecture", "extract_small_lemmas", "create_formal_statement", "obtain_trusted_checker_attestation"])
        return MathVetoResult(
            decision="VETO_OVERCLAIM",
            proof_authority="not_proved",
            max_allowed_claim_level="proof_sketch_only" if claim.proof_sketch or claim.proof_steps else "conjecture_candidate",
            claim_level_downgraded=True,
            open_problem_detected=open_problem,
            proof_overclaim_detected=True,
            reason_codes=reason_codes,
            missing_items=missing,
            required_next_steps=required,
            lean_gate=lean,
            recommendation="Rewrite as a conjecture/proof sketch and expose the exact lemma obligations; no proof/solved wording is allowed.",
        ).to_dict()

    if not claim.formal_statement:
        reason_codes.append("NEEDS_FORMAL_STATEMENT")
        required.extend(["write_minimal_formal_statement", "define_all_symbols", "state_domain_and_quantifiers"])
        return MathVetoResult(
            decision="ASK_FORMALIZATION",
            proof_authority="informal_idea",
            max_allowed_claim_level="conjecture_candidate",
            open_problem_detected=open_problem,
            proof_overclaim_detected=False,
            reason_codes=reason_codes,
            missing_items=missing,
            required_next_steps=required,
            lean_gate=lean,
            recommendation="Convert the idea into a formal statement with definitions, domain, and quantifiers before proof search.",
        ).to_dict()

    if claim.numerical_evidence and not (claim.proof_sketch or claim.proof_steps or claim.lemmas):
        reason_codes.append("NUMERICAL_EVIDENCE_IS_NOT_PROOF")
        return MathVetoResult(
            decision="REVISE_NUMERICAL_ONLY",
            proof_authority="numerical_evidence_only",
            max_allowed_claim_level="numerical_evidence_only",
            claim_level_downgraded=claim.claim_level != "numerical_evidence_only",
            open_problem_detected=open_problem,
            proof_overclaim_detected=False,
            reason_codes=reason_codes,
            missing_items=missing,
            required_next_steps=["state_what_the_computation_tests", "search_for_counterexamples", "extract_symbolic_lemma"],
            lean_gate=lean,
            recommendation="Report computation only as evidence; propose a symbolic lemma that would explain it.",
        ).to_dict()

    if claim.formal_statement and not (claim.lemmas or claim.proof_steps):
        reason_codes.append("NEEDS_LEMMA_DECOMPOSITION")
        return MathVetoResult(
            decision="NEEDS_LEMMA",
            proof_authority="proof_obligation_candidate",
            max_allowed_claim_level="proof_obligation_candidate",
            open_problem_detected=open_problem,
            proof_overclaim_detected=False,
            reason_codes=reason_codes,
            missing_items=missing,
            required_next_steps=["split_into_lemmas", "identify_known_theorems", "create_checker_tasks"],
            lean_gate=lean,
            recommendation="Break the formal statement into smaller lemmas that a proof assistant or human can attack.",
        ).to_dict()

    reason_codes.append("SAFE_PROOF_SKETCH_OR_CONJECTURE")
    return MathVetoResult(
        decision="APPROVE_WITH_LIMITS",
        proof_authority="proof_sketch_only",
        max_allowed_claim_level="proof_sketch_only",
        open_problem_detected=open_problem,
        proof_overclaim_detected=False,
        reason_codes=reason_codes,
        missing_items=missing,
        required_next_steps=["formalize_next_lemma", "run_counterexample_search", "avoid_theorem_language"],
        lean_gate=lean,
        recommendation="The claim may be used as a bounded proof sketch or research direction, not as a proof.",
    ).to_dict()


__all__ = ["MATH_VETO_VERSION", "evaluate_math_claim", "MathVetoResult"]
