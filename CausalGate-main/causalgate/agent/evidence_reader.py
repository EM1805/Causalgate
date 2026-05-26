from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .discovery_adapter import DiscoveryEvidenceAdapter


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, Mapping)):
        return list(value)
    return [value]


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _clean_lower(value: Any, default: str = "") -> str:
    text = _clean_str(value, default).lower()
    return text or default


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _first(payload: Mapping[str, Any], keys: Sequence[str], default: Any = "") -> Any:
    for key in keys:
        if key in payload and payload.get(key) not in (None, ""):
            return payload.get(key)
    return default


def _norm_token(value: Any) -> str:
    return _clean_lower(value).replace("-", "_").replace(" ", "_")


def _dedupe(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        text = _clean_str(item)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _read_csv_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _read_jsonl_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping):
                rows.append(dict(value))
    return rows


def _read_json_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(value, list):
        return [dict(v) for v in value if isinstance(v, Mapping)]
    if isinstance(value, Mapping):
        for key in ("rows", "items", "cards", "records", "data"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [dict(v) for v in nested if isinstance(v, Mapping)]
        return [dict(value)]
    return []


@dataclass
class AgentEvidenceBundle:
    """Structured causal evidence visible to the agent runtime, not the LLM planner.

    The bundle is advisory evidence. It can strengthen/qualify a DecisionGate
    evaluation through structured fields such as estimation_query, but it never
    authorizes direct tool execution and never bypasses ToolGuard.
    """

    query: Dict[str, Any] = field(default_factory=dict)
    matched_authority_cards: List[Dict[str, Any]] = field(default_factory=list)
    matched_effect_estimates: List[Dict[str, Any]] = field(default_factory=list)
    matched_sensitivity_rows: List[Dict[str, Any]] = field(default_factory=list)
    matched_contracts: List[Dict[str, Any]] = field(default_factory=list)
    matched_gate_audit_rows: List[Dict[str, Any]] = field(default_factory=list)
    matched_report_rows: List[Dict[str, Any]] = field(default_factory=list)
    matched_discovery_hypotheses: List[Dict[str, Any]] = field(default_factory=list)
    best_estimation_query: Dict[str, Any] = field(default_factory=dict)
    evidence_score: float = 0.0
    evidence_tier: str = "none"
    evidence_warnings: List[str] = field(default_factory=list)
    evidence_present: List[str] = field(default_factory=list)
    evidence_missing: List[str] = field(default_factory=list)
    usable_for_autonomous_action: bool = False
    decision_hints: Dict[str, Any] = field(default_factory=dict)
    source_files: Dict[str, str] = field(default_factory=dict)
    generated_by: str = "causalgate.agent.evidence_reader"
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AgentEvidenceReader:
    """Read CausalGate offline causal outputs for an online agent turn.

    Supported files are intentionally structured only: CSV, JSON and JSONL.
    Markdown reports are not parsed as decision evidence. Human-readable
    reports can still be shown to users separately, but agent decisions should
    depend on structured rows that are easy to audit.
    """

    AUTHORITY_DEFAULTS = (
        "veto/causal_authority_cards.jsonl",
        "causal_authority_cards.jsonl",
        "causal_authority_cards.json",
    )
    CONTRACT_DEFAULTS = ("causal_contract.csv", "causal_contract.json", "contracts/causal_contract.csv")
    EFFECT_DEFAULTS = ("effect_estimates.csv", "effects.csv", "estimation/effect_estimates.csv")
    SENSITIVITY_DEFAULTS = ("sensitivity_analysis.csv", "sensitivity.csv", "estimation/sensitivity_analysis.csv")
    GATE_AUDIT_DEFAULTS = ("gate_audit.csv", "veto/gate_audit.csv")
    REPORT_DEFAULTS = ("causal_report.csv",)

    def __init__(
        self,
        *,
        output_dir: str | Path = "out",
        authority_cards_path: str | Path | None = None,
        causal_contract_path: str | Path | None = None,
        effect_estimates_path: str | Path | None = None,
        sensitivity_analysis_path: str | Path | None = None,
        gate_audit_path: str | Path | None = None,
        causal_report_csv_path: str | Path | None = None,
        discovery_adapter: DiscoveryEvidenceAdapter | None = None,
        enable_discovery_adapter: bool = True,
        max_rows_per_source: int = 5,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.max_rows_per_source = max(1, int(max_rows_per_source or 5))
        self.paths = {
            "authority_cards": self._resolve_first(authority_cards_path, self.AUTHORITY_DEFAULTS),
            "causal_contract": self._resolve_first(causal_contract_path, self.CONTRACT_DEFAULTS),
            "effect_estimates": self._resolve_first(effect_estimates_path, self.EFFECT_DEFAULTS),
            "sensitivity_analysis": self._resolve_first(sensitivity_analysis_path, self.SENSITIVITY_DEFAULTS),
            "gate_audit": self._resolve_first(gate_audit_path, self.GATE_AUDIT_DEFAULTS),
            "causal_report_csv": self._resolve_first(causal_report_csv_path, self.REPORT_DEFAULTS),
        }
        self.discovery_adapter = discovery_adapter or (
            DiscoveryEvidenceAdapter(output_dir=self.output_dir, max_rows_per_source=self.max_rows_per_source)
            if enable_discovery_adapter
            else None
        )

    def _resolve_first(self, explicit: str | Path | None, defaults: Sequence[str]) -> Path:
        if explicit:
            path = Path(explicit)
            return path if path.is_absolute() else path
        for rel in defaults:
            candidate = self.output_dir / rel
            if candidate.exists():
                return candidate
        return self.output_dir / defaults[0]

    def read(self, action_payload: Mapping[str, Any]) -> AgentEvidenceBundle:
        query = self._query_terms(action_payload)
        source_files = {key: str(path) for key, path in self.paths.items() if path.exists()}

        authority_rows = self._match_rows(self._load_rows(self.paths["authority_cards"]), query)
        effect_rows = self._match_rows(self._load_rows(self.paths["effect_estimates"]), query)
        sensitivity_rows = self._match_rows(self._load_rows(self.paths["sensitivity_analysis"]), query)
        contract_rows = self._match_rows(self._load_rows(self.paths["causal_contract"]), query)
        audit_rows = self._match_rows(self._load_rows(self.paths["gate_audit"]), query)
        report_rows = self._match_rows(self._load_rows(self.paths["causal_report_csv"]), query)
        discovery_rows: List[Dict[str, Any]] = []
        if self.discovery_adapter is not None:
            try:
                discovery_bundle = self.discovery_adapter.read(action_payload)
                discovery_rows = list(discovery_bundle.matched_discovery_hypotheses or [])
                for key, value in (discovery_bundle.source_files or {}).items():
                    if value:
                        source_files.setdefault(f"discovery:{key}", value)
            except Exception:
                discovery_rows = []

        bundle = AgentEvidenceBundle(
            query=query,
            matched_authority_cards=authority_rows[: self.max_rows_per_source],
            matched_effect_estimates=effect_rows[: self.max_rows_per_source],
            matched_sensitivity_rows=sensitivity_rows[: self.max_rows_per_source],
            matched_contracts=contract_rows[: self.max_rows_per_source],
            matched_gate_audit_rows=audit_rows[: self.max_rows_per_source],
            matched_report_rows=report_rows[: self.max_rows_per_source],
            matched_discovery_hypotheses=discovery_rows[: self.max_rows_per_source],
            source_files=source_files,
            notes=[
                "EvidenceReader reads structured offline CausalGate outputs only.",
                "Evidence informs DecisionGate/ToolGuard but never authorizes direct execution.",
            ],
        )
        self._score(bundle)
        bundle.best_estimation_query = self._best_estimation_query(bundle)
        return bundle

    def _load_rows(self, path: Path) -> List[Dict[str, Any]]:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return _read_csv_rows(path)
        if suffix == ".jsonl":
            return _read_jsonl_rows(path)
        if suffix == ".json":
            return _read_json_rows(path)
        return []

    def _query_terms(self, action_payload: Mapping[str, Any]) -> Dict[str, Any]:
        payload = _as_dict(action_payload)
        params = _as_dict(payload.get("params"))
        context = _as_dict(payload.get("context"))
        trusted = _as_dict(payload.get("trusted_runtime_context") or payload.get("trusted_context"))
        causal_query = _as_dict(payload.get("causal_query") or context.get("causal_query") or params.get("causal_query"))
        estimation_query = _as_dict(payload.get("estimation_query") or context.get("estimation_query") or params.get("estimation_query"))

        action_name = _clean_str(
            payload.get("action_name")
            or payload.get("candidate_action")
            or payload.get("selected_action")
            or params.get("action_name")
        )
        treatment = _clean_str(
            payload.get("treatment")
            or causal_query.get("treatment")
            or estimation_query.get("treatment")
            or context.get("treatment")
            or params.get("treatment")
            or action_name
        )
        outcome = _clean_str(
            payload.get("outcome")
            or causal_query.get("outcome")
            or estimation_query.get("outcome")
            or context.get("outcome")
            or params.get("outcome")
            or payload.get("intended_outcome")
            or trusted.get("outcome")
        )
        effect_id = _clean_str(payload.get("effect_id") or causal_query.get("effect_id") or estimation_query.get("effect_id"))
        request_id = _clean_str(payload.get("request_id") or trusted.get("request_id"))
        domain = _clean_str(trusted.get("domain") or context.get("domain") or params.get("domain"))

        tokens = _dedupe(
            _norm_token(x)
            for x in [action_name, treatment, outcome, effect_id, request_id, domain]
            if _clean_str(x)
        )
        return {
            "action_name": action_name,
            "treatment": treatment,
            "outcome": outcome,
            "effect_id": effect_id,
            "request_id": request_id,
            "domain": domain,
            "tokens": tokens,
        }

    def _row_match_score(self, row: Mapping[str, Any], query: Mapping[str, Any]) -> int:
        tokens = set(query.get("tokens") or [])
        if not tokens:
            return 0
        score = 0
        token_fields = {
            "action_name": ["action_name", "candidate_action", "selected_action", "original_action", "tool_name"],
            "treatment": ["treatment", "treatment_col", "source", "cause", "action_col", "intervention", "from"],
            "outcome": ["outcome", "outcome_col", "target", "effect", "protected_outcome", "intended_outcome", "to"],
            "effect_id": ["effect_id", "plan_id", "insight_id", "contract_id", "card_id", "id"],
            "request_id": ["request_id", "run_id", "audit_id"],
            "domain": ["domain", "risk_domain", "inferred_domain"],
        }
        for query_key, fields in token_fields.items():
            q = _norm_token(query.get(query_key))
            if not q:
                continue
            for field in fields:
                value = _norm_token(row.get(field))
                if not value:
                    continue
                if value == q:
                    score += 6 if query_key in {"effect_id", "request_id"} else 4
                elif value in tokens or q in value or value in q:
                    score += 2

        # Compact fallback: match tokens anywhere in short identifying fields.
        if score <= 0:
            hay = " ".join(
                _norm_token(row.get(k))
                for k in row.keys()
                if any(word in k.lower() for word in ("action", "treatment", "source", "cause", "target", "outcome", "effect", "id"))
            )
            if any(t and t in hay for t in tokens):
                score += 1
        return score

    def _match_rows(self, rows: List[Dict[str, Any]], query: Mapping[str, Any]) -> List[Dict[str, Any]]:
        scored: List[tuple[int, Dict[str, Any]]] = []
        for row in rows:
            score = self._row_match_score(row, query)
            if score > 0:
                copied = dict(row)
                copied["_agent_evidence_match_score"] = score
                scored.append((score, copied))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [row for _, row in scored]

    def _score(self, bundle: AgentEvidenceBundle) -> None:
        score = 0.0
        warnings: List[str] = []
        present: List[str] = []
        missing: List[str] = []
        usable = False
        hints: Dict[str, Any] = {}

        if bundle.matched_authority_cards:
            present.append("authority_card")
            score += 25
            for card in bundle.matched_authority_cards:
                strength = _clean_lower(_first(card, ["evidence_strength", "authority_tier", "evidence_tier", "confidence"], ""))
                decision_authority = _clean_lower(_first(card, ["decision_authority", "authority_status", "status"], ""))
                if strength in {"strong", "high", "invariant"}:
                    score += 20
                elif strength in {"medium", "moderate"}:
                    score += 12
                elif strength in {"weak", "low"}:
                    score += 4
                if _safe_bool(_first(card, ["veto_ready", "usable_for_veto", "decision_ready"], False)):
                    score += 15
                    present.append("veto_ready_authority")
                if decision_authority in {"deny", "blocked", "veto", "forbidden"}:
                    hints["decision_ceiling"] = "veto"
                    warnings.append("Authority card indicates the action may be veto/forbidden.")
                if decision_authority in {"allow", "allowed", "approved"}:
                    usable = True

        if bundle.matched_effect_estimates:
            present.append("effect_estimate")
            score += 20
            row = bundle.matched_effect_estimates[0]
            eff = _safe_float(_first(row, ["effect_estimate", "estimate", "ate", "att"], None))
            ci_low = _safe_float(_first(row, ["ci_low", "lower", "confidence_low"], None))
            ci_high = _safe_float(_first(row, ["ci_high", "upper", "confidence_high"], None))
            support_n = _safe_float(_first(row, ["support_n", "n", "sample_size"], None), 0.0) or 0.0
            if eff is not None:
                score += 10
            if ci_low is not None and ci_high is not None:
                if ci_low <= 0 <= ci_high:
                    warnings.append("Effect estimate confidence interval crosses zero.")
                    hints.setdefault("decision_ceiling", "warn")
                    score -= 8
                else:
                    score += 8
            else:
                warnings.append("Effect estimate is missing a complete confidence interval.")
            if support_n and support_n < 20:
                warnings.append("Effect estimate has low support_n.")
                score -= 4
            robustness = _clean_lower(_first(row, ["robustness_status", "robustness"], ""))
            placebo = _clean_lower(_first(row, ["placebo_status"], ""))
            negative_control = _clean_lower(_first(row, ["negative_control_status"], ""))
            if robustness in {"pass", "passed", "robust", "ok"}:
                score += 6
            if placebo in {"fail", "failed"} or negative_control in {"fail", "failed"}:
                warnings.append("Placebo or negative-control diagnostic failed.")
                hints.setdefault("decision_ceiling", "abstain")
                score -= 15

        if bundle.matched_sensitivity_rows:
            present.append("sensitivity_analysis")
            score += 8
            for row in bundle.matched_sensitivity_rows[:2]:
                status = _clean_lower(_first(row, ["sensitivity_status", "sensitivity_quant_status", "status", "fragility"], ""))
                risk = _clean_lower(_first(row, ["sensitivity_risk", "risk", "fragility_risk"], ""))
                if status in {"pass", "passed", "robust", "low"} or risk in {"low", "robust"}:
                    score += 8
                if status in {"fail", "failed", "fragile", "high"} or risk in {"high", "fragile"}:
                    warnings.append("Sensitivity analysis indicates fragile or high-risk evidence.")
                    hints.setdefault("decision_ceiling", "warn")
                    score -= 12

        if bundle.matched_contracts:
            present.append("causal_contract")
            score += 10
            for row in bundle.matched_contracts:
                allowed_use = _clean_lower(_first(row, ["allowed_use", "use", "execution_scope"], ""))
                forbidden_use = _clean_lower(_first(row, ["forbidden_use", "forbidden", "disallowed_use"], ""))
                requires_review = _safe_bool(_first(row, ["requires_review", "human_review_required"], False))
                if "autonomous_execution" in forbidden_use or "autonomous" in forbidden_use:
                    usable = False
                    hints["autonomous_execution"] = "forbidden_by_contract"
                    hints.setdefault("decision_ceiling", "ask_clarification")
                    warnings.append("Causal contract forbids autonomous execution for this evidence.")
                if "recommendation_only" in allowed_use or allowed_use == "recommendation_only":
                    usable = False
                    if hints.get("autonomous_execution") != "forbidden_by_contract":
                        hints["autonomous_execution"] = "recommendation_only"
                    hints.setdefault("decision_ceiling", "warn")
                    warnings.append("Causal contract allows recommendation only, not direct execution.")
                if requires_review:
                    usable = False
                    hints["requires_review"] = True
                    hints.setdefault("decision_ceiling", "ask_clarification")
                    warnings.append("Causal contract requires human review.")
                if allowed_use in {"autonomous_execution", "guarded_execution", "execution"} and not requires_review:
                    usable = True

        if bundle.matched_discovery_hypotheses:
            present.append("discovery_hypothesis")
            # Discovery improves coverage, but remains weak hypothesis-only evidence.
            score += min(20, 15 + 2 * len(bundle.matched_discovery_hypotheses))

        if bundle.matched_gate_audit_rows:
            present.append("prior_gate_audit")
            score += 3
        if bundle.matched_report_rows:
            present.append("causal_report_row")
            score += 2

        validated_present = any(item in present for item in ("authority_card", "effect_estimate", "causal_contract", "sensitivity_analysis"))
        if bundle.matched_discovery_hypotheses and not validated_present:
            warnings.append("Discovery-only evidence is hypothesis-only and cannot authorize autonomous execution.")
            hints["autonomous_execution"] = "discovery_hypothesis_only"
            hints["allowed_use"] = "recommendation_only"
            hints.setdefault("decision_ceiling", "ask_clarification")
            missing.append("downstream_validation_for_discovery")

        if not bundle.source_files:
            missing.append("causal_output_files")
        if not present:
            missing.append("matched_structured_evidence")
        if "effect_estimate" not in present:
            missing.append("effect_estimate")
        if "causal_contract" not in present:
            missing.append("causal_contract")
        if bundle.matched_discovery_hypotheses and not validated_present:
            missing.append("authority_card_or_estimation_for_discovery")

        score = max(0.0, min(100.0, score))
        if score >= 70 and not warnings:
            tier = "strong"
        elif score >= 45:
            tier = "medium"
        elif score >= 15:
            tier = "weak"
        else:
            tier = "none"

        # Conservative default: only structured high/strong evidence plus no
        # contract warning may be used for autonomous action, and ToolGuard is
        # still mandatory.
        if tier not in {"medium", "strong"}:
            usable = False
        if warnings:
            usable = False
        hints.setdefault("tool_guard_required", True)
        hints.setdefault("decision_gate_required", True)

        bundle.evidence_score = round(score, 3)
        bundle.evidence_tier = tier
        bundle.evidence_warnings = _dedupe(warnings)
        bundle.evidence_present = _dedupe(present)
        bundle.evidence_missing = _dedupe(missing)
        bundle.usable_for_autonomous_action = bool(usable)
        bundle.decision_hints = hints

    def _best_estimation_query(self, bundle: AgentEvidenceBundle) -> Dict[str, Any]:
        if not bundle.matched_effect_estimates:
            return {}
        row = bundle.matched_effect_estimates[0]
        treatment = _clean_str(_first(row, ["treatment", "treatment_col", "source", "cause", "action_col"])) or _clean_str(bundle.query.get("treatment"))
        outcome = _clean_str(_first(row, ["outcome", "outcome_col", "target", "effect"])) or _clean_str(bundle.query.get("outcome"))
        query = {
            "treatment": treatment,
            "outcome": outcome,
            "effect_estimate": _safe_float(_first(row, ["effect_estimate", "estimate", "ate", "att"], None)),
            "ci_low": _safe_float(_first(row, ["ci_low", "lower", "confidence_low"], None)),
            "ci_high": _safe_float(_first(row, ["ci_high", "upper", "confidence_high"], None)),
            "support_n": _first(row, ["support_n", "n", "sample_size"], ""),
            "treated_n": _first(row, ["treated_n"], ""),
            "control_n": _first(row, ["control_n"], ""),
            "estimator_used": _first(row, ["estimator_used", "estimator"], "agent_evidence_reader"),
            "robustness_status": _first(row, ["robustness_status", "robustness"], "not_evaluated"),
            "negative_control_status": _first(row, ["negative_control_status"], "not_evaluated"),
            "placebo_status": _first(row, ["placebo_status"], "not_evaluated"),
            "sensitivity_status": _first(row, ["sensitivity_status", "sensitivity_quant_status"], "not_evaluated"),
            "effect_claim_status": _first(row, ["effect_claim_status", "estimation_status"], "loaded_effect_estimate"),
            "source": "agent_evidence_reader.best_effect_estimate",
        }
        return {k: v for k, v in query.items() if v not in (None, "")}

    def enrich_candidate(self, candidate_payload: Mapping[str, Any]) -> Dict[str, Any]:
        """Attach evidence bundle to a candidate before DecisionGate evaluation."""

        candidate = dict(candidate_payload or {})
        bundle = self.read(candidate).to_dict()
        params = _as_dict(candidate.get("params"))
        context = _as_dict(candidate.get("context"))
        params["agent_evidence_bundle"] = bundle
        context["agent_evidence_bundle"] = {
            "evidence_tier": bundle.get("evidence_tier"),
            "evidence_score": bundle.get("evidence_score"),
            "evidence_warnings": list(bundle.get("evidence_warnings") or []),
            "usable_for_autonomous_action": bool(bundle.get("usable_for_autonomous_action")),
        }
        if bundle.get("best_estimation_query") and not candidate.get("estimation_query"):
            candidate["estimation_query"] = dict(bundle.get("best_estimation_query") or {})
        candidate["params"] = params
        candidate["context"] = context
        return candidate


__all__ = ["AgentEvidenceBundle", "AgentEvidenceReader"]
