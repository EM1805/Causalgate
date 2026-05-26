from __future__ import annotations

"""Bounded LLM ↔ math-critic loop for hypothesis development.

The loop is deterministic by default.  A caller may provide an LLM adapter, but
CausalGate's math critic remains authoritative: the adapter can propose revisions,
while the veto gate controls allowed claim strength.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Mapping
from uuid import uuid4

from .claim_schema import MathClaimPackage, normalize_math_claim
from .lemma_recommender import recommend_next_lemmas
from .math_veto import evaluate_math_claim


MATH_HYPOTHESIS_LOOP_VERSION = "math_hypothesis_dialogue_loop_v1_step99"
MathLLMAdapter = Callable[[Mapping[str, Any]], Mapping[str, Any] | None]


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _intish(value: Any, default: int = 3, minimum: int = 1, maximum: int = 12) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _dialogue_id() -> str:
    return "math_dialogue_" + uuid4().hex[:12]


def _terminal(verdict: Mapping[str, Any]) -> bool:
    return _clean_str(verdict.get("decision")) in {
        "APPROVE_WITH_LIMITS",
        "APPROVE_FORMAL_THEOREM",
        "COUNTEREXAMPLE_FOUND",
        "REVIEW_FORMAL_OPEN_PROBLEM_CLAIM",
        "VETO_MISSING_CLAIM",
    }


def _extract_revision(adapter_result: Mapping[str, Any] | None) -> Dict[str, Any]:
    result = _as_dict(adapter_result)
    for key in ("revised_claim", "math_claim", "claim", "hypothesis"):
        if isinstance(result.get(key), Mapping):
            return dict(result[key])
    return result if result.get("claim") else {}


def _apply_deterministic_revision(claim: MathClaimPackage, verdict: Mapping[str, Any], recs: Mapping[str, Any]) -> Dict[str, Any]:
    revised = claim.to_dict()
    metadata = _as_dict(revised.get("metadata"))
    codes = set(str(x) for x in verdict.get("reason_codes", []) or [])
    open_problem = _clean_str(verdict.get("open_problem_detected"))
    decision = _clean_str(verdict.get("decision"))

    if decision in {"VETO_OVERCLAIM", "REVIEW_FORMAL_OPEN_PROBLEM_CLAIM"}:
        revised["claim_level"] = "proof_sketch_only" if revised.get("proof_sketch") or revised.get("proof_steps") else "conjecture_candidate"
        prefix = "Bounded conjecture/proof-sketch candidate"
        if open_problem == "riemann_hypothesis":
            revised["claim"] = (
                f"{prefix}: the submitted idea may suggest a route toward a weaker RH-related lemma, "
                "but it is not a proof of the Riemann Hypothesis."
            )
            revised["problem_name"] = revised.get("problem_name") or "Riemann Hypothesis"
        else:
            revised["claim"] = f"{prefix}: {revised.get('claim', '').replace('proved', 'suggests').replace('solved', 'explores')}"
    if "NEEDS_FORMAL_STATEMENT" in codes and not _clean_str(revised.get("formal_statement")):
        revised["formal_statement"] = "TODO_formal_statement: specify domain, quantifiers, definitions, and target proposition."
    if not revised.get("definitions"):
        revised["definitions"] = ["Define all symbols, domains, and quantifiers before proof search."]
    if not revised.get("lemmas"):
        obligations = recs.get("proof_obligations", []) or []
        revised["lemmas"] = [str(item.get("description", item)) for item in obligations[:3] if item]
    if "NUMERICAL_EVIDENCE_IS_NOT_PROOF" in codes:
        revised["claim_level"] = "numerical_evidence_only"
    metadata["revised_by"] = "causalgate.math_hypothesis.hypothesis_loop"
    metadata["last_math_veto_decision"] = decision
    metadata["last_math_reason_codes"] = list(codes)
    metadata["last_math_recommendation"] = verdict.get("recommendation", "")
    revised["metadata"] = metadata
    return revised


@dataclass
class MathDialogueTurn:
    turn_index: int
    claim: Dict[str, Any]
    verdict: Dict[str, Any]
    recommendations: Dict[str, Any]
    llm_revision_requested: bool = False
    revised_claim: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def run_math_hypothesis_loop(
    payload: Mapping[str, Any] | MathClaimPackage,
    *,
    llm_adapter: MathLLMAdapter | None = None,
    max_rounds: int | None = None,
    auto_revise: bool | None = None,
) -> Dict[str, Any]:
    data = payload.to_dict() if isinstance(payload, MathClaimPackage) else _as_dict(payload)
    dialogue_id = _clean_str(data.get("dialogue_id"), _dialogue_id())
    rounds = _intish(max_rounds if max_rounds is not None else data.get("max_rounds", 3), default=3, minimum=1, maximum=12)
    do_auto_revise = bool(data.get("auto_revise", True) if auto_revise is None else auto_revise)
    raw_claim = data.get("math_claim") if isinstance(data.get("math_claim"), Mapping) else data.get("hypothesis") if isinstance(data.get("hypothesis"), Mapping) else data
    claim = normalize_math_claim(raw_claim)
    turns: List[Dict[str, Any]] = []
    veto_history: List[str] = []
    final_verdict: Dict[str, Any] = {}

    for idx in range(rounds):
        verdict = evaluate_math_claim(claim)
        recs = recommend_next_lemmas(claim.to_dict(), verdict)
        final_verdict = verdict
        veto_history.append(_clean_str(verdict.get("decision"), "UNKNOWN"))
        revised_claim: Dict[str, Any] = {}
        should_request_revision = not _terminal(verdict) and idx < rounds - 1
        if should_request_revision:
            if llm_adapter is not None:
                try:
                    revised_claim = _extract_revision(llm_adapter({
                        "dialogue_id": dialogue_id,
                        "turn_index": idx,
                        "claim": claim.to_dict(),
                        "verdict": verdict,
                        "recommendations": recs,
                    }))
                except Exception as exc:  # pragma: no cover - defensive adapter boundary
                    revised_claim = {**claim.to_dict(), "metadata": {**claim.metadata, "llm_adapter_error": f"{type(exc).__name__}: {exc}"}}
            if not revised_claim and do_auto_revise:
                revised_claim = _apply_deterministic_revision(claim, verdict, recs)
        turns.append(MathDialogueTurn(
            turn_index=idx,
            claim=claim.to_dict(),
            verdict=verdict,
            recommendations=recs,
            llm_revision_requested=should_request_revision,
            revised_claim=revised_claim,
        ).to_dict())
        if not should_request_revision or not revised_claim:
            break
        claim = normalize_math_claim(revised_claim)

    final_claim = turns[-1].get("revised_claim") or turns[-1].get("claim") if turns else claim.to_dict()
    allowed_final_level = _clean_str(final_verdict.get("max_allowed_claim_level"), "proof_sketch_only")
    loop_status = "completed"
    if final_verdict.get("decision") == "VETO_OVERCLAIM":
        loop_status = "stopped_on_overclaim"
    elif len(turns) >= rounds and not _terminal(final_verdict):
        loop_status = "max_rounds_reached"

    result: Dict[str, Any] = {
        "matrix_version": MATH_HYPOTHESIS_LOOP_VERSION,
        "dialogue_id": dialogue_id,
        "product_name": "CausalGate Math Hypothesis Dialogue Loop",
        "loop_status": loop_status,
        "turns_completed": len(turns),
        "max_rounds": rounds,
        "final_decision": final_verdict.get("decision", "UNKNOWN"),
        "final_proof_authority": final_verdict.get("proof_authority", "unknown"),
        "max_allowed_claim_level": allowed_final_level,
        "proof_overclaim_blocked": int(any(turn.get("verdict", {}).get("decision") == "VETO_OVERCLAIM" for turn in turns)),
        "open_problem_detected": final_verdict.get("open_problem_detected", ""),
        "veto_history": veto_history,
        "final_claim": final_claim,
        "turns": turns,
    }
    result["dialogue_digest"] = _digest({k: v for k, v in result.items() if k != "dialogue_digest"})
    return result


__all__ = ["MATH_HYPOTHESIS_LOOP_VERSION", "run_math_hypothesis_loop"]
