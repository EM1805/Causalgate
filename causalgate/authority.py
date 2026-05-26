from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Mapping

from causalgate.evidence import CausalEvidence
from causalgate.agent_firewall.policy import HARD_BLOCK, PASS, REVIEW


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _risk_key(value: Any) -> str:
    text = _clean(value, "unknown").lower().replace("-", "_")
    return {"severe": "critical", "hi": "high", "med": "medium", "moderate": "medium"}.get(text, text)


@dataclass(frozen=True)
class CausalAuthorityResult:
    """Decision-grade authority assessment for one proposed agent action."""

    authority_score: int
    authority_level: str
    authority_decision: str
    threshold_profile: str
    reasons: list[str] = field(default_factory=list)
    required_next_steps: list[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _diagnostics_points(evidence: CausalEvidence, reasons: list[str], required: list[str]) -> int:
    ratio = evidence.diagnostics_ratio
    if ratio is None:
        reasons.append("No diagnostics summary supplied.")
        required.append("Run diagnostics: placebo, negative controls, bootstrap/stability and sensitivity checks.")
        return 0
    if ratio >= 0.8:
        reasons.append(f"Diagnostics are strong: {evidence.diagnostics_passed}/{evidence.diagnostics_total} passed.")
        return 15
    if ratio >= 0.5:
        reasons.append(f"Diagnostics are partial: {evidence.diagnostics_passed}/{evidence.diagnostics_total} passed.")
        required.append("Complete failing or missing diagnostics before production execution.")
        return 9
    reasons.append(f"Diagnostics are weak: only {evidence.diagnostics_passed}/{evidence.diagnostics_total} passed.")
    required.append("Do not rely on this action until diagnostics are improved.")
    return 3


def score_causal_authority(
    evidence: CausalEvidence | Mapping[str, Any] | None,
    *,
    risk_level: str = "unknown",
    require_evidence: bool = True,
) -> CausalAuthorityResult:
    """Score whether an agent has enough causal authority for an action.

    Score bands are intentionally conservative:

    * 0-39: weak authority -> HARD_BLOCK
    * 40-69: partial authority -> REVIEW
    * 70-100: sufficient authority -> PASS for low/medium risk; high/critical
      risk still requires stronger evidence.
    """

    ev = evidence if isinstance(evidence, CausalEvidence) else CausalEvidence.from_mapping(evidence)
    reasons: list[str] = []
    required: list[str] = []
    score = 0

    if not ev.has_any_signal and require_evidence:
        reasons.append("No causal evidence package was supplied.")
        required.append("Supply identification, estimation and diagnostics evidence before the agent acts.")
    elif not ev.has_any_signal:
        reasons.append("No causal evidence package was supplied; authority gate is informational only.")

    if ev.identified:
        score += 25
        reasons.append("Causal estimand is identified.")
    else:
        reasons.append("Causal estimand is not identified or identification status is unknown.")
        required.append("Run SCM identification and provide the identified estimand or a failure certificate.")

    if ev.effect_estimated and ev.estimate is not None:
        score += 20
        reasons.append("Effect estimate is available.")
    elif ev.effect_estimated:
        score += 12
        reasons.append("Effect estimation was reported, but no numeric estimate was supplied.")
        required.append("Attach the numeric estimate and uncertainty interval.")
    else:
        reasons.append("No effect estimate is available.")
        required.append("Estimate the total/direct effect before using this action causally.")

    score += _diagnostics_points(ev, reasons, required)

    if ev.scm_available:
        score += 8
        reasons.append("SCM or candidate graph is available.")
    else:
        required.append("Attach an SCM/candidate graph or state why one is unavailable.")

    if ev.discovery_graph_available:
        score += 4
        reasons.append("Discovery graph is available as hypothesis support.")

    confidence = ev.confidence.lower()
    if confidence in {"high", "strong"}:
        score += 10
        reasons.append("Confidence is high.")
    elif confidence in {"medium", "moderate"}:
        score += 6
        reasons.append("Confidence is medium.")
    elif confidence in {"low", "weak"}:
        score += 2
        reasons.append("Confidence is low.")
        required.append("Improve confidence before autonomous production action.")
    else:
        required.append("Provide confidence level or uncertainty summary.")

    if ev.confidence_interval is not None:
        score += 5
        reasons.append("Uncertainty interval is supplied.")
    else:
        required.append("Attach a confidence/credible interval for the estimate.")

    sensitivity = ev.sensitivity_risk.lower()
    hidden = ev.hidden_confounding_risk.lower()
    if sensitivity == "low":
        score += 6
        reasons.append("Sensitivity risk is low.")
    elif sensitivity in {"medium", "unknown"}:
        score += 2 if sensitivity == "medium" else 0
        required.append("Run or attach sensitivity analysis.")
    else:
        reasons.append("Sensitivity risk is high.")
        required.append("Resolve high sensitivity risk before execution.")

    if hidden == "low":
        score += 5
        reasons.append("Hidden confounding risk is low.")
    elif hidden in {"medium", "unknown"}:
        score += 2 if hidden == "medium" else 0
        required.append("Address hidden confounding risk, for example with negative controls or additional covariates.")
    else:
        reasons.append("Hidden confounding risk is high.")
        required.append("Do not allow autonomous execution with high hidden-confounding risk.")

    if ev.sample_size is not None:
        if ev.sample_size >= 500:
            score += 4
            reasons.append(f"Sample size is adequate for a first-pass gate: n={ev.sample_size}.")
        elif ev.sample_size >= 100:
            score += 2
            reasons.append(f"Sample size is limited: n={ev.sample_size}.")
            required.append("Treat estimate as preliminary or add data.")
        else:
            reasons.append(f"Sample size is very small: n={ev.sample_size}.")
            required.append("Increase sample size before relying on this action.")

    if ev.placebo_passed is True:
        score += 2
        reasons.append("Placebo check passed.")
    elif ev.placebo_passed is False:
        reasons.append("Placebo check failed.")
        required.append("Investigate placebo failure before execution.")

    if ev.negative_controls_passed is True:
        score += 1
        reasons.append("Negative-control check passed.")
    elif ev.negative_controls_passed is False:
        reasons.append("Negative-control check failed.")
        required.append("Investigate negative-control failure before execution.")

    if ev.stability_score is not None:
        if ev.stability_score >= 0.8:
            score += 5
            reasons.append("Bootstrap/stability score is strong.")
        elif ev.stability_score >= 0.5:
            score += 2
            reasons.append("Bootstrap/stability score is partial.")
            required.append("Improve graph/effect stability before high-impact execution.")
        else:
            reasons.append("Bootstrap/stability score is weak.")
            required.append("Do not rely on unstable causal evidence.")

    risk = _risk_key(risk_level)
    score = max(0, min(100, int(round(score))))

    if score < 40:
        level = "weak"
        decision = HARD_BLOCK
    elif score < 70:
        level = "partial"
        decision = REVIEW
    else:
        level = "sufficient"
        decision = PASS

    # High-impact actions need stronger causal authority than informational actions.
    profile = "standard"
    if risk in {"high", "critical"}:
        profile = "high_impact"
        if score < 55:
            decision = HARD_BLOCK
            level = "weak" if score < 40 else "partial_but_too_weak_for_high_impact"
            required.append("High-impact actions require at least partial-to-strong causal authority.")
        elif score < 80:
            decision = REVIEW
            level = "partial_for_high_impact"
            required.append("High-impact actions require human review unless authority score is at least 80.")
    elif risk == "medium" and score < 70:
        profile = "medium_impact"
        decision = REVIEW if score >= 40 else HARD_BLOCK

    # Deduplicate while preserving order.
    dedup_required: list[str] = []
    for item in required:
        if item and item not in dedup_required:
            dedup_required.append(item)

    return CausalAuthorityResult(
        authority_score=score,
        authority_level=level,
        authority_decision=decision,
        threshold_profile=profile,
        reasons=reasons,
        required_next_steps=dedup_required,
        evidence=ev.to_dict(),
    )


__all__ = ["CausalAuthorityResult", "score_causal_authority"]
