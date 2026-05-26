from __future__ import annotations

"""Conservative veto for scientific hypothesis candidates.

CausalGate reviews empirical/mechanistic hypotheses as testable scientific
candidates and mathematical conjectures as proof/counterexample candidates.
"""

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Dict, List, Mapping

from .hypothesis_contract import ScientificHypothesisPackage, normalize_scientific_hypothesis
from .falsification_policy import FalsificationPolicy
from .revision_protocol import build_revision_protocol
from .claim_levels import claim_level_audit, normalize_claim_level

VALID_HYPOTHESIS_DECISIONS = {"FINAL_CANDIDATE", "REVISE", "TEST_MORE", "BLOCK", "ABSTAIN"}
_OVERCLAIM_TERMS = {"proved", "proven", "confirmed", "certain", "guaranteed", "law confirmed", "new law", "discovered a law", "causes always", "causa sempre", "legge confermata", "ho scoperto", "dimostrato", "teorema dimostrato"}
_OVERCLAIM_PATTERNS = tuple(re.compile(r"(?<![\w])" + re.escape(term).replace(r"\ ", r"\s+") + r"(?![\w])", re.IGNORECASE) for term in sorted(_OVERCLAIM_TERMS, key=len, reverse=True))
_ESTIMATION_EVIDENCE_KEYS = {"data_path", "data_csv", "csv_path", "effect_estimates_path", "effects_path", "estimates_path", "effect_estimate", "estimate", "effect"}


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _contains_overclaim(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in _OVERCLAIM_PATTERNS)


def _is_math_hypothesis(hypothesis: ScientificHypothesisPackage) -> bool:
    domain = _clean_str(hypothesis.domain).lower()
    kind = _clean_str(hypothesis.hypothesis_kind).lower()
    claim = _clean_str(hypothesis.claim).lower()
    return domain == "mathematical" or kind == "mathematical_conjecture" or claim.startswith("candidate mathematical conjecture")


def _has_estimation_evidence(payload: Mapping[str, Any]) -> bool:
    return any(key in payload and payload.get(key) not in (None, "", []) for key in _ESTIMATION_EVIDENCE_KEYS)


def _short_for_llm(result: Mapping[str, Any]) -> Dict[str, Any]:
    estimation = _as_dict(result.get("estimation"))
    return {"decision": result.get("decision", "ABSTAIN"), "claim_level": result.get("claim_level", "hypothesis_only"), "scientific_claim_level": result.get("scientific_claim_level", {}), "max_allowed_claim_level": result.get("max_allowed_claim_level", {}), "causal_status": result.get("causal_status", "unknown"), "falsifiability_status": result.get("falsifiability_status", "unknown"), "evidence_status": result.get("evidence_status", "unknown"), "estimation_status": estimation.get("estimation_status", "not_run"), "causal_estimate_available": bool(estimation.get("causal_estimate_available")), "overclaim_risk": result.get("overclaim_risk", "unknown"), "reason": result.get("reason", ""), "missing_items": list(result.get("missing_items", []) or []), "next_instruction": result.get("next_instruction", ""), "scientific_rule": "Do not present FINAL_CANDIDATE as a confirmed law/proof; obey max_allowed_claim_level."}


@dataclass
class HypothesisVetoResult:
    decision: str = "ABSTAIN"
    hypothesis_id: str = ""
    claim_level: str = "hypothesis_only"
    claim_level_index: int = 2
    claim_level_key: str = "candidate_hypothesis"
    claim_level_label: str = "candidate hypothesis"
    scientific_claim_level: Dict[str, Any] = field(default_factory=dict)
    max_allowed_claim_level: Dict[str, Any] = field(default_factory=dict)
    requested_claim_level: Dict[str, Any] = field(default_factory=dict)
    claim_level_downgraded: bool = False
    causal_status: str = "unknown"
    falsifiability_status: str = "unknown"
    evidence_status: str = "unknown"
    overclaim_risk: str = "unknown"
    reason: str = ""
    reason_codes: List[str] = field(default_factory=list)
    missing_items: List[str] = field(default_factory=list)
    required_tests: List[str] = field(default_factory=list)
    next_instruction: str = ""
    identification: Dict[str, Any] = field(default_factory=dict)
    estimation: Dict[str, Any] = field(default_factory=dict)
    audit_payload: Dict[str, Any] = field(default_factory=dict)
    short_for_llm: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.decision not in VALID_HYPOTHESIS_DECISIONS:
            self.decision = "ABSTAIN"
        if not self.short_for_llm:
            self.short_for_llm = _short_for_llm(asdict(self))

    def to_dict(self) -> Dict[str, Any]:
        if not self.short_for_llm:
            self.short_for_llm = _short_for_llm(asdict(self))
        return asdict(self)


class HypothesisVeto:
    def __init__(self, enable_identification: bool = True) -> None:
        self.enable_identification = enable_identification

    def evaluate(self, payload: Mapping[str, Any] | ScientificHypothesisPackage) -> HypothesisVetoResult:
        raw_payload = payload.to_dict() if isinstance(payload, ScientificHypothesisPackage) else _as_dict(payload)
        hypothesis = payload if isinstance(payload, ScientificHypothesisPackage) else normalize_scientific_hypothesis(payload)
        missing = hypothesis.missing_core_items()
        reason_codes: List[str] = []
        required_tests: List[str] = []
        identification: Dict[str, Any] = {}
        estimation: Dict[str, Any] = {}
        claim_text = " ".join([hypothesis.claim, hypothesis.title, hypothesis.conclusion_strength, hypothesis.claim_level, hypothesis.claim_level_key])
        requested_level = normalize_claim_level(hypothesis.claim_level_key or hypothesis.claim_level)
        overclaims = _contains_overclaim(claim_text) or requested_level.index >= 4
        overclaim_risk = "high" if overclaims else "medium" if requested_level.index >= 3 else "low"

        if not hypothesis.claim:
            falsification_data = FalsificationPolicy().assess(hypothesis).to_dict()
            return self._result(hypothesis, decision="BLOCK", causal_status="invalid_payload", falsifiability_status=falsification_data.get("falsifiability_status", "unknown"), evidence_status=falsification_data.get("evidence_status", "unknown"), overclaim_risk=overclaim_risk, reason="Missing hypothesis claim. CausalGate cannot evaluate an empty scientific claim.", reason_codes=["MISSING_CLAIM"], missing_items=missing, required_tests=[], next_instruction="Provide a precise claim in hypothesis-only language before resubmitting.", identification=identification, estimation=estimation, falsification=falsification_data)

        if _is_math_hypothesis(hypothesis):
            return self._evaluate_math_conjecture(hypothesis, overclaims=overclaims, overclaim_risk=overclaim_risk)

        falsification_assessment = FalsificationPolicy().assess(hypothesis)
        falsification_data = falsification_assessment.to_dict()
        if overclaims:
            reason_codes.append("OVERCLAIM_RISK_HIGH")
            required_tests.append("downgrade_claim_to_hypothesis_only_or_testable_candidate")
        if "treatment_or_cause" in missing or "outcome_or_effect" in missing:
            reason_codes.append("MISSING_CAUSE_OR_EFFECT_VARIABLE")
        if "dag_with_nodes_and_edges" in missing:
            reason_codes.append("MISSING_DAG")
        if "assumptions" in missing:
            reason_codes.append("MISSING_ASSUMPTIONS")
        if "falsification_tests" in missing:
            reason_codes.append("MISSING_FALSIFICATION_TESTS")
            required_tests.extend(["negative_control", "placebo_or_temporal_leakage_test"])
        if "data_requirements" in missing:
            reason_codes.append("MISSING_DATA_REQUIREMENTS")
        for code in falsification_data.get("reason_codes", []) or []:
            if code not in reason_codes:
                reason_codes.append(code)
        for item in falsification_data.get("missing_items", []) or []:
            if item not in missing:
                missing.append(item)
        required_tests.extend(falsification_data.get("required_tests", []) or [])
        if len(hypothesis.falsification_tests) == 1:
            reason_codes.append("TOO_FEW_FALSIFICATION_TESTS")
            required_tests.append("add_second_independent_falsification_test")
        if self.enable_identification and not {"treatment_or_cause", "outcome_or_effect", "dag_with_nodes_and_edges"}.intersection(missing):
            identification = self._try_identification(hypothesis)
            identified = bool(identification.get("identified"))
            tier = _clean_str(identification.get("identification_tier"), "unknown")
            estimation = self._try_estimation(hypothesis, identification, raw_payload)
            if not identified:
                reason_codes.append("EFFECT_NOT_IDENTIFIED_OR_ID_UNAVAILABLE")
                required_tests.append("state_identification_strategy_or_adjustment_set")
                causal_status = "identification_check_unavailable" if tier == "adapter_error" else "not_identified"
            else:
                causal_status = "identified_candidate"
                if estimation.get("estimated") or estimation.get("causal_estimate_available"):
                    reason_codes.append("ESTIMATION_AVAILABLE")
                elif estimation.get("association_estimate_available"):
                    reason_codes.append("DIAGNOSTIC_ASSOCIATION_AVAILABLE")
        else:
            causal_status = "missing_structure"
            estimation = self._try_estimation(hypothesis, identification, raw_payload)
        falsification_hint = _clean_str(falsification_data.get("decision_hint"), "FINAL_CANDIDATE")
        revision_protocol = build_revision_protocol(falsification_data)
        if overclaims:
            decision = "REVISE"
            reason = "The hypothesis is phrased too strongly. It must be downgraded to a testable candidate before evaluation continues."
            next_instruction = "Rewrite the claim as hypothesis_only or testable_candidate; include limits and avoid language like confirmed law or proven cause."
        elif missing:
            if falsification_hint == "TEST_MORE" and not {"claim", "treatment_or_cause", "outcome_or_effect", "dag_with_nodes_and_edges", "assumptions", "data_requirements", "measurable_prediction", "adjustment_set", "observed_confounder_measurements"}.intersection(set(missing)):
                decision = "TEST_MORE"
                reason = "The hypothesis is structurally usable but needs stronger falsification tests before candidate status."
            else:
                decision = "REVISE"
                reason = "The hypothesis is incomplete for causal scientific review."
            next_instruction = falsification_data.get("next_instruction") or ("Add missing items: " + ", ".join(missing) + ".")
        elif "TOO_FEW_FALSIFICATION_TESTS" in reason_codes:
            decision = "TEST_MORE"
            reason = "The hypothesis has structure, but needs at least two independent falsification tests."
            next_instruction = "Add at least one more independent falsification test, preferably a negative control or placebo test."
        elif falsification_hint in {"REVISE", "TEST_MORE"}:
            decision = falsification_hint
            reason = "The Step 5 falsification/evidence gate did not allow final candidate status."
            next_instruction = falsification_data.get("next_instruction") or revision_protocol["revision_checklist"][0]
        elif "EFFECT_NOT_IDENTIFIED_OR_ID_UNAVAILABLE" in reason_codes:
            decision = "TEST_MORE"
            reason = "The causal effect is not yet identified or the identification backend could not verify it."
            next_instruction = "Specify a valid identification strategy, adjustment set, or revised DAG before calling this a final candidate."
        else:
            decision = "FINAL_CANDIDATE"
            causal_status = causal_status if causal_status != "missing_structure" else "testable_candidate"
            reason = "The hypothesis is acceptable only as a testable scientific candidate, not as a confirmed law."
            next_instruction = "Preserve the claim level as testable_candidate and run the listed empirical/simulation tests before any stronger conclusion."
        return self._result(hypothesis, decision=decision, causal_status=causal_status, falsifiability_status=falsification_data.get("falsifiability_status", "unknown"), evidence_status=falsification_data.get("evidence_status", "unknown"), overclaim_risk=overclaim_risk, reason=reason, reason_codes=sorted(set(reason_codes)), missing_items=missing, required_tests=sorted(set(required_tests)), next_instruction=next_instruction, identification=identification, estimation=estimation, falsification=falsification_data)

    def _evaluate_math_conjecture(self, hypothesis: ScientificHypothesisPackage, *, overclaims: bool, overclaim_risk: str) -> HypothesisVetoResult:
        required_tests = ["formal_statement_review", "counterexample_search", "proof_attempt_or_reduction_to_known_results", "independent_formal_or_computational_verification"]
        falsification_data = {"decision_hint": "FINAL_CANDIDATE" if not overclaims else "REVISE", "falsifiability_status": "proof_or_counterexample_testable", "evidence_status": "formal_validation_required", "reason_codes": [] if not overclaims else ["OVERCLAIM_RISK_HIGH"], "missing_items": [], "required_tests": required_tests, "required_evidence": list(hypothesis.data_requirements or ["Formal statement", "Definitions and axioms", "Boundary cases", "Candidate examples and counterexamples"]), "next_instruction": "Treat this as a mathematical conjecture: attempt proof, search for counterexamples, check boundary cases, and seek independent formal/computational verification before stronger claims.", "audit_payload": {"hypothesis_id": hypothesis.hypothesis_id, "math_protocol": True, "causal_review_skipped": True, "requires_treatment_or_time_window": False}}
        if overclaims:
            return self._result(hypothesis, decision="REVISE", causal_status="not_applicable_mathematical_conjecture", falsifiability_status="proof_or_counterexample_testable", evidence_status="formal_validation_required", overclaim_risk=overclaim_risk, reason="The conjecture is phrased too strongly. It must be kept as a candidate conjecture until proof or counterexample review succeeds.", reason_codes=["OVERCLAIM_RISK_HIGH"], missing_items=[], required_tests=required_tests, next_instruction="Downgrade to candidate conjecture language; do not call it proven or solved without formal verification.", identification={"not_applicable": True, "reason": "Mathematical conjecture review does not use empirical causal identification."}, estimation={"estimated": False, "estimation_status": "not_applicable_mathematical_conjecture", "reason_codes": ["ESTIMATION_NOT_APPLICABLE_MATHEMATICAL_CONJECTURE"]}, falsification=falsification_data)
        return self._result(hypothesis, decision="FINAL_CANDIDATE", causal_status="not_applicable_mathematical_conjecture", falsifiability_status="proof_or_counterexample_testable", evidence_status="formal_validation_required", overclaim_risk=overclaim_risk, reason="The mathematical conjecture is structurally acceptable as a proof/counterexample candidate, not as an empirical causal claim.", reason_codes=["MATHEMATICAL_CONJECTURE_REVIEW"], missing_items=[], required_tests=required_tests, next_instruction="Attempt proof, search for counterexamples, check edge cases, and require independent formal or computational verification before any stronger conclusion.", identification={"not_applicable": True, "reason": "Mathematical conjecture review does not use empirical causal identification."}, estimation={"estimated": False, "estimation_status": "not_applicable_mathematical_conjecture", "reason_codes": ["ESTIMATION_NOT_APPLICABLE_MATHEMATICAL_CONJECTURE"]}, falsification=falsification_data)

    def _try_identification(self, hypothesis: ScientificHypothesisPackage) -> Dict[str, Any]:
        try:
            from causalgate.causal_core.identification.engine import identify_effect
            return _as_dict(identify_effect(hypothesis.to_identification_query()))
        except Exception as exc:  # pragma: no cover
            return {"identified": False, "identification_tier": "adapter_error", "reason": f"Identification backend unavailable or failed: {exc}", "reason_codes": ["IDENTIFICATION_BACKEND_ERROR"]}

    def _build_estimation_payload(self, hypothesis: ScientificHypothesisPackage, identification: Mapping[str, Any], raw_payload: Mapping[str, Any]) -> Dict[str, Any]:
        raw = _as_dict(raw_payload)
        wrapped = _as_dict(raw.get("hypothesis"))
        metadata = _as_dict(raw.get("metadata"))
        metadata.update(_as_dict(wrapped.get("metadata")))
        query: Dict[str, Any] = {}
        query.update(_as_dict(raw.get("estimation_query")))
        query.update(_as_dict(wrapped.get("estimation_query")))
        query.update(_as_dict(metadata.get("estimation_query")))
        for source in (raw, wrapped, metadata):
            for key in _ESTIMATION_EVIDENCE_KEYS | {"ci_low", "ci_high", "support_n", "treated_n", "control_n", "estimator_hint", "estimator", "estimator_used", "recommended_estimator", "robustness_status", "negative_control_status", "placebo_status", "sensitivity_status", "expected_direction", "bootstrap_b", "lag"}:
                if key in source and key not in query:
                    query[key] = source[key]
        if not _has_estimation_evidence(query):
            return {}
        query.setdefault("treatment", hypothesis.treatment)
        query.setdefault("outcome", hypothesis.outcome)
        if hypothesis.adjustment_set and "adjustment_set" not in query:
            query["adjustment_set"] = list(hypothesis.adjustment_set)
        query.setdefault("source", "causalgate.scientific.hypothesis_veto")
        query.setdefault("query_id", hypothesis.hypothesis_id)
        if identification:
            query.setdefault("identification_result", dict(identification))
            if identification.get("identified"):
                query.setdefault("identified", True)
                query.setdefault("allowed_for_estimation", True)
                query.setdefault("estimation_enabled", True)
                query.setdefault("authority_level", "identified_estimable")
                query.setdefault("identification_status", identification.get("identification_tier") or identification.get("identification_strategy") or "identified")
                query.setdefault("identification_strategy", identification.get("identification_strategy", ""))
            else:
                query.setdefault("identified", False)
        return query

    def _try_estimation(self, hypothesis: ScientificHypothesisPackage, identification: Mapping[str, Any], raw_payload: Mapping[str, Any]) -> Dict[str, Any]:
        query = self._build_estimation_payload(hypothesis, identification, raw_payload)
        if not query:
            return {"estimated": False, "estimation_status": "not_run_no_estimation_evidence", "causal_estimate_available": False, "association_estimate_available": False, "allowed_for_decision": False, "reason": "No data path, effect-estimate file, or explicit effect estimate was supplied.", "reason_codes": ["ESTIMATION_NOT_RUN_NO_EVIDENCE"]}
        id_authorized = bool(query.get("identified") and query.get("allowed_for_estimation"))
        explicitly_authorized = _clean_str(query.get("allowed_for_estimation")).lower() in {"1", "true", "yes", "on"}
        if not id_authorized and not explicitly_authorized:
            return {"estimated": False, "estimation_status": "blocked_no_identification_authority", "causal_estimate_available": False, "association_estimate_available": False, "allowed_for_decision": False, "treatment": hypothesis.treatment, "outcome": hypothesis.outcome, "reason": "Estimation evidence was supplied, but SCM-ID did not authorize causal estimation for this hypothesis.", "reason_codes": ["NO_ID_CONTRACT_AUTHORITY_FOR_CAUSAL_ESTIMATION"]}
        try:
            from causalgate.causal_core.estimation import estimate_effect
            return _as_dict(estimate_effect(query))
        except Exception as exc:  # pragma: no cover
            return {"estimated": False, "estimation_status": "adapter_runtime_error", "causal_estimate_available": False, "allowed_for_decision": False, "reason": f"Estimation adapter failed safely: {type(exc).__name__}: {exc}", "reason_codes": ["ESTIMATION_ADAPTER_ERROR"]}

    def _result(self, hypothesis: ScientificHypothesisPackage, *, decision: str, causal_status: str, falsifiability_status: str, evidence_status: str, overclaim_risk: str, reason: str, reason_codes: List[str], missing_items: List[str], required_tests: List[str], next_instruction: str, identification: Dict[str, Any], estimation: Dict[str, Any], falsification: Dict[str, Any]) -> HypothesisVetoResult:
        audit_payload = {"run_id": hypothesis.run_id, "step": hypothesis.step, "hypothesis_id": hypothesis.hypothesis_id, "source": hypothesis.source, "claim": hypothesis.claim, "claim_level": hypothesis.claim_level, "claim_level_index": hypothesis.claim_level_index, "claim_level_key": hypothesis.claim_level_key, "treatment": hypothesis.treatment, "outcome": hypothesis.outcome, "decision": decision, "reason_codes": list(reason_codes), "missing_items": list(missing_items), "falsifiability_status": falsifiability_status, "evidence_status": evidence_status}
        is_math = _is_math_hypothesis(hypothesis)
        if is_math:
            level_audit = {"requested": {"index": 2, "key": "mathematical_conjecture", "label": "mathematical conjecture", "allowed_assertion": "May be treated as a candidate conjecture requiring proof or counterexample.", "minimum_requirements": ["formal_statement", "definitions_or_axioms", "counterexample_search"]}, "max_allowed": {"index": 2, "key": "proof_or_counterexample_candidate", "label": "proof/counterexample candidate", "allowed_assertion": "May be reviewed through proof, counterexample search, edge cases, and independent verification.", "minimum_requirements": ["formal_statement", "definitions_or_axioms", "counterexample_search", "verification_protocol"]}, "final": {"index": 2, "key": "proof_or_counterexample_candidate", "label": "proof/counterexample candidate", "allowed_assertion": "May be reviewed through proof, counterexample search, edge cases, and independent verification.", "minimum_requirements": ["formal_statement", "definitions_or_axioms", "counterexample_search", "verification_protocol"]}, "downgraded": False, "reason": "mathematical_conjecture_uses_formal_review_ceiling"}
            final_level = level_audit["final"]
            max_allowed = level_audit["max_allowed"]
            legacy_final = "conjecture_candidate"
        else:
            level_audit = claim_level_audit(hypothesis.claim_level_key or hypothesis.claim_level, decision=decision, missing_items=missing_items, identification=identification, falsification=falsification)
            final_level = level_audit["final"]
            max_allowed = level_audit["max_allowed"]
            if level_audit.get("downgraded") and "CLAIM_LEVEL_DOWNGRADED_TO_EVIDENCE_CEILING" not in reason_codes:
                reason_codes = list(reason_codes) + ["CLAIM_LEVEL_DOWNGRADED_TO_EVIDENCE_CEILING"]
                audit_payload["reason_codes"] = list(reason_codes)
            legacy_final = {"blocked": "blocked", "speculative_idea": "observation_only", "candidate_hypothesis": "hypothesis_only", "testable_hypothesis": "testable_candidate", "statistically_supported": "supported_candidate", "causally_identified": "identified_candidate", "experimentally_validated": "experimentally_validated", "independently_replicated": "validated_external"}.get(final_level["key"], "hypothesis_only")
            if decision == "FINAL_CANDIDATE" and final_level["index"] < 3:
                final_level = normalize_claim_level("testable_hypothesis").to_dict()
                legacy_final = "testable_candidate"
        audit_payload = {**audit_payload, "identification": dict(identification), "estimation": dict(estimation), "falsification": dict(falsification), "claim_level_audit": level_audit}
        return HypothesisVetoResult(decision=decision, hypothesis_id=hypothesis.hypothesis_id, claim_level=legacy_final, claim_level_index=int(final_level["index"]), claim_level_key=str(final_level["key"]), claim_level_label=str(final_level["label"]), scientific_claim_level=dict(final_level), max_allowed_claim_level=dict(max_allowed), requested_claim_level=dict(level_audit["requested"]), claim_level_downgraded=bool(level_audit["downgraded"]), causal_status=causal_status, falsifiability_status=falsifiability_status, evidence_status=evidence_status, overclaim_risk=overclaim_risk, reason=reason, reason_codes=list(reason_codes), missing_items=list(missing_items), required_tests=list(required_tests), next_instruction=next_instruction, identification=dict(identification), estimation=dict(estimation), audit_payload=audit_payload)


def evaluate_hypothesis(payload: Mapping[str, Any], enable_identification: bool = True) -> Dict[str, Any]:
    return HypothesisVeto(enable_identification=enable_identification).evaluate(payload).to_dict()


__all__ = ["HypothesisVeto", "HypothesisVetoResult", "evaluate_hypothesis", "VALID_HYPOTHESIS_DECISIONS"]
