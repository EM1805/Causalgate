from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _clean_lower(value: Any, default: str = "") -> str:
    text = _clean_str(value, default).lower()
    return text if text else default


def _norm_token(value: Any) -> str:
    return _clean_lower(value).replace("-", "_").replace(" ", "_")


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _first(payload: Mapping[str, Any], keys: Sequence[str], default: Any = "") -> Any:
    for key in keys:
        if key in payload and payload.get(key) not in (None, ""):
            return payload.get(key)
    return default


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
        return [dict(item) for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        for key in ("rows", "items", "edges", "insights", "candidates", "data"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [dict(item) for item in nested if isinstance(item, Mapping)]
        return [dict(value)]
    return []


@dataclass
class DiscoveryEvidenceBundle:
    """Normalized Discovery hypotheses for one agent action.

    Discovery rows are intentionally treated as hypothesis-only evidence. They
    can improve recommendations and routing into Estimation/SCM-ID, but they
    must not authorize an autonomous side effect by themselves.
    """

    query: Dict[str, Any] = field(default_factory=dict)
    matched_discovery_hypotheses: List[Dict[str, Any]] = field(default_factory=list)
    source_files: Dict[str, str] = field(default_factory=dict)
    evidence_status: str = "hypothesis_only"
    allowed_use: str = "recommendation_only"
    usable_for_autonomous_action: bool = False
    generated_by: str = "causalgate.agent.discovery_adapter"
    notes: List[str] = field(default_factory=lambda: [
        "Discovery outputs are treated as candidate causal hypotheses only.",
        "Discovery evidence cannot authorize autonomous execution without downstream validation.",
    ])

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DiscoveryEvidenceAdapter:
    """Read Discovery outputs and normalize them for AgentEvidenceReader.

    Supported files are structured CSV/JSON/JSONL outputs commonly produced by
    the Discovery layer. The adapter never executes tools and never upgrades a
    decision to allow; it only emits weak, proposal-only evidence.
    """

    DISCOVERY_DEFAULTS = (
        # Modern layered CausalGate Discovery artifacts first. These are the
        # canonical outputs produced by the current offline pipeline.
        "discovery/pcmci_links.csv",
        "discovery/pcmci_scm_bridge.csv",
        "ranking/insights_level2.csv",
        "discovery/discovery_scoring.csv",
        "discovery/gate_audit.csv",
        "discovery/discovery_candidates.csv",
        "discovery/causal_candidates.csv",
        "discovery/pcmci_edges.csv",
        "discovery/pcmci_discovery.csv",
        "discovery/discovery_edges.jsonl",
        "discovery/discovery_candidates.jsonl",
        "discovery/edges.json",
        "discovery/insights_level2.json",
        # Compatibility / legacy root artifacts. Kept after layered outputs so
        # the runtime prefers the current Discovery contract when both exist.
        "edges.csv",
        "insights_level2.csv",
        "discovery_candidates.csv",
        "causal_candidates.csv",
        "pcmci_edges.csv",
        "pcmci_discovery.csv",
        "discovery_edges.jsonl",
        "discovery_candidates.jsonl",
        "edges.json",
        "insights_level2.json",
    )

    def __init__(
        self,
        *,
        output_dir: str | Path = "out",
        discovery_paths: Sequence[str | Path] | None = None,
        max_rows_per_source: int = 5,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.max_rows_per_source = max(1, int(max_rows_per_source or 5))
        self.paths = self._resolve_paths(discovery_paths)

    def _resolve_paths(self, explicit: Sequence[str | Path] | None) -> List[Path]:
        paths: List[Path] = []
        if explicit:
            for item in explicit:
                path = Path(item)
                paths.append(path if path.is_absolute() else path)
            return paths
        for rel in self.DISCOVERY_DEFAULTS:
            candidate = self.output_dir / rel
            if candidate.exists():
                paths.append(candidate)
        return paths

    def read(self, action_payload: Mapping[str, Any]) -> DiscoveryEvidenceBundle:
        query = self._query_terms(action_payload)
        source_files = {self._source_key(path): str(path) for path in self.paths if path.exists()}
        matched: List[Dict[str, Any]] = []
        for path in self.paths:
            for row in self._load_rows(path):
                score = self._row_match_score(row, query)
                if score <= 0:
                    continue
                normalized = self._normalize_row(row, path=path, match_score=score)
                matched.append(normalized)
        matched.sort(key=lambda item: item.get("_agent_discovery_match_score", 0), reverse=True)
        return DiscoveryEvidenceBundle(
            query=query,
            matched_discovery_hypotheses=matched[: self.max_rows_per_source],
            source_files=source_files,
        )

    def _load_rows(self, path: Path) -> List[Dict[str, Any]]:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return _read_csv_rows(path)
        if suffix == ".jsonl":
            return _read_jsonl_rows(path)
        if suffix == ".json":
            return _read_json_rows(path)
        return []

    def _source_key(self, path: Path) -> str:
        """Stable source key that preserves layered directories.

        Using only ``path.name`` would collapse files such as
        ``ranking/insights_level2.csv`` and root ``insights_level2.csv`` into the
        same key. The relative key keeps runtime evidence auditable.
        """
        try:
            return path.relative_to(self.output_dir).as_posix()
        except ValueError:
            return path.name

    def _source_layer(self, path: Path) -> str:
        try:
            rel = path.relative_to(self.output_dir).as_posix()
        except ValueError:
            rel = path.as_posix()
        if rel.startswith("discovery/"):
            return "discovery_layered"
        if rel.startswith("ranking/"):
            return "ranking_layered"
        return "legacy_root"

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
        domain = _clean_str(trusted.get("domain") or context.get("domain") or params.get("domain"))
        tokens = _dedupe(
            _norm_token(x)
            for x in [action_name, treatment, outcome, effect_id, domain]
            if _clean_str(x)
        )
        return {
            "action_name": action_name,
            "treatment": treatment,
            "outcome": outcome,
            "effect_id": effect_id,
            "domain": domain,
            "tokens": tokens,
        }

    def _row_match_score(self, row: Mapping[str, Any], query: Mapping[str, Any]) -> int:
        tokens = set(query.get("tokens") or [])
        if not tokens:
            return 0
        score = 0
        token_fields = {
            "action_name": ["action_name", "candidate_action", "selected_action", "tool_name", "action"],
            "treatment": ["treatment", "treatment_col", "source", "cause", "parent", "from", "action_col", "intervention"],
            "outcome": ["outcome", "outcome_col", "target", "effect", "child", "to", "protected_outcome", "intended_outcome"],
            "effect_id": ["effect_id", "insight_id", "edge_id", "candidate_id", "id"],
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
                    score += 5 if query_key in {"effect_id"} else 4
                elif value in tokens or q in value or value in q:
                    score += 2
        if score <= 0:
            hay = " ".join(
                _norm_token(row.get(k))
                for k in row.keys()
                if any(word in k.lower() for word in ("action", "treatment", "source", "cause", "target", "outcome", "effect", "edge", "id"))
            )
            if any(t and t in hay for t in tokens):
                score += 1
        return score

    def _normalize_row(self, row: Mapping[str, Any], *, path: Path, match_score: int) -> Dict[str, Any]:
        source = _clean_str(_first(row, ["source", "cause", "treatment", "treatment_col", "parent", "from", "action_col", "action_name"]))
        target = _clean_str(_first(row, ["target", "effect", "outcome", "outcome_col", "child", "to", "intended_outcome"]))
        lag = _first(row, ["lag", "lag_days", "best_lag", "time_lag"], "")
        strength = _safe_float(_first(row, ["discovery_strength", "strength", "score", "causal_score", "confidence", "p_sign"], None), None)
        stability = _first(row, ["stability", "stability_score", "stable", "sign_stability"], "")
        method = _clean_str(_first(row, ["method", "discovery_method", "engine", "source_engine"], path.stem))
        status = _clean_str(_first(row, ["status", "claim_status", "edge_status"], "hypothesis_only"))
        normalized = dict(row)
        normalized.update({
            "source": source,
            "target": target,
            "lag": lag,
            "discovery_strength": strength if strength is not None else _first(row, ["discovery_strength", "strength", "score", "causal_score", "confidence", "p_sign"], ""),
            "stability": stability,
            "method": method,
            "evidence_status": "hypothesis_only",
            "allowed_use": "recommendation_only",
            "usable_for_autonomous_action": False,
            "requires_downstream_validation": True,
            "recommended_next_validation": "estimation_or_scm_id",
            "_agent_discovery_source_file": str(path),
            "_agent_discovery_source_key": self._source_key(path),
            "_agent_discovery_source_layer": self._source_layer(path),
            "_agent_discovery_match_score": match_score,
            "_agent_discovery_original_status": status,
        })
        return normalized


__all__ = ["DiscoveryEvidenceAdapter", "DiscoveryEvidenceBundle"]
