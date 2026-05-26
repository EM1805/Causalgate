from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1
    return _clean_str(value).lower() in {"1", "true", "yes", "y", "on", "passed", "pass", "available", "identified"}


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_risk(value: Any, default: str = "unknown") -> str:
    text = _clean_str(value, default).lower().replace("-", "_")
    aliases = {
        "none": "low",
        "minimal": "low",
        "moderate": "medium",
        "med": "medium",
        "hi": "high",
        "severe": "high",
        "unclear": "unknown",
    }
    return aliases.get(text, text if text else default)


@dataclass(frozen=True)
class CausalEvidence:
    """Evidence package supplied to the agent causal firewall.

    The object intentionally captures the *authority* chain rather than only an
    effect estimate: a high-impact agent action should be backed by an
    identified estimand, an estimate, diagnostics, and explicit assumptions.
    Missing fields are treated conservatively by the authority scorer.
    """

    identified: bool = False
    identification_status: str = "unknown"
    estimand_type: str = "unknown"
    effect_estimated: bool = False
    estimate: float | None = None
    confidence_interval: tuple[float, float] | None = None
    confidence: str = "unknown"
    diagnostics_passed: int = 0
    diagnostics_total: int = 0
    sensitivity_risk: str = "unknown"
    hidden_confounding_risk: str = "unknown"
    sample_size: int | None = None
    scm_available: bool = False
    discovery_graph_available: bool = False
    placebo_passed: bool | None = None
    negative_controls_passed: bool | None = None
    stability_score: float | None = None
    assumptions: list[str] = field(default_factory=list)
    method: str = "unknown"
    source: str = "manual"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "CausalEvidence":
        data = _as_dict(payload)
        if not data:
            return cls()

        identification_status = _clean_str(
            data.get("identification_status")
            or data.get("id_status")
            or data.get("status"),
            "unknown",
        ).lower()
        identified = _truthy(data.get("identified")) or identification_status in {"identified", "passed", "ok", "success"}

        ci_raw = data.get("confidence_interval") or data.get("ci") or data.get("effect_ci")
        confidence_interval: tuple[float, float] | None = None
        if isinstance(ci_raw, (list, tuple)) and len(ci_raw) >= 2:
            lo = _optional_float(ci_raw[0])
            hi = _optional_float(ci_raw[1])
            if lo is not None and hi is not None:
                confidence_interval = (lo, hi)

        estimate = _optional_float(data.get("estimate") if "estimate" in data else data.get("effect_estimate"))
        effect_estimated = _truthy(data.get("effect_estimated")) or estimate is not None

        diagnostics = _as_dict(data.get("diagnostics"))
        diagnostics_passed = _optional_int(data.get("diagnostics_passed"))
        diagnostics_total = _optional_int(data.get("diagnostics_total"))
        if diagnostics:
            diagnostics_passed = diagnostics_passed if diagnostics_passed is not None else _optional_int(diagnostics.get("passed"))
            diagnostics_total = diagnostics_total if diagnostics_total is not None else _optional_int(diagnostics.get("total"))

        assumptions = data.get("assumptions") or data.get("causal_assumptions") or []
        if isinstance(assumptions, str):
            assumptions = [assumptions]

        metadata = _as_dict(data.get("metadata"))
        known_keys = {
            "identified", "identification_status", "id_status", "status", "estimand_type", "estimand", "effect_estimated",
            "estimate", "effect_estimate", "confidence_interval", "ci", "effect_ci", "confidence", "diagnostics",
            "diagnostics_passed", "diagnostics_total", "sensitivity_risk", "hidden_confounding_risk", "sample_size",
            "n", "scm_available", "has_scm", "discovery_graph_available", "has_discovery_graph", "placebo_passed",
            "negative_controls_passed", "stability_score", "assumptions", "causal_assumptions", "method", "source", "metadata",
        }
        extra = {str(k): v for k, v in data.items() if k not in known_keys}
        if extra:
            metadata = {**metadata, "extra": extra}

        return cls(
            identified=identified,
            identification_status=identification_status,
            estimand_type=_clean_str(data.get("estimand_type") or data.get("estimand"), "unknown"),
            effect_estimated=effect_estimated,
            estimate=estimate,
            confidence_interval=confidence_interval,
            confidence=_clean_str(data.get("confidence"), "unknown").lower(),
            diagnostics_passed=max(0, int(diagnostics_passed or 0)),
            diagnostics_total=max(0, int(diagnostics_total or 0)),
            sensitivity_risk=_normalize_risk(data.get("sensitivity_risk"), "unknown"),
            hidden_confounding_risk=_normalize_risk(data.get("hidden_confounding_risk"), "unknown"),
            sample_size=_optional_int(data.get("sample_size") if "sample_size" in data else data.get("n")),
            scm_available=_truthy(data.get("scm_available")) or _truthy(data.get("has_scm")),
            discovery_graph_available=_truthy(data.get("discovery_graph_available")) or _truthy(data.get("has_discovery_graph")),
            placebo_passed=None if data.get("placebo_passed") is None else _truthy(data.get("placebo_passed")),
            negative_controls_passed=None if data.get("negative_controls_passed") is None else _truthy(data.get("negative_controls_passed")),
            stability_score=_optional_float(data.get("stability_score")),
            assumptions=[_clean_str(item) for item in _as_list(assumptions) if _clean_str(item)],
            method=_clean_str(data.get("method"), "unknown"),
            source=_clean_str(data.get("source"), "manual"),
            metadata=metadata,
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "CausalEvidence":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("Causal evidence JSON must contain an object")
        return cls.from_mapping(payload)

    @classmethod
    def coerce(cls, value: "CausalEvidence" | Mapping[str, Any] | str | Path | None) -> "CausalEvidence | None":
        if value is None:
            return None
        if isinstance(value, CausalEvidence):
            return value
        if isinstance(value, Mapping):
            return cls.from_mapping(value)
        return cls.from_file(value)

    @property
    def diagnostics_ratio(self) -> float | None:
        if self.diagnostics_total <= 0:
            return None
        return max(0.0, min(1.0, self.diagnostics_passed / self.diagnostics_total))

    @property
    def has_any_signal(self) -> bool:
        return any(
            [
                self.identified,
                self.effect_estimated,
                self.estimate is not None,
                self.diagnostics_total > 0,
                self.sample_size is not None,
                self.scm_available,
                self.discovery_graph_available,
                bool(self.assumptions),
            ]
        )

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if self.confidence_interval is not None:
            payload["confidence_interval"] = list(self.confidence_interval)
        payload["diagnostics_ratio"] = self.diagnostics_ratio
        payload["has_any_signal"] = self.has_any_signal
        return payload


__all__ = ["CausalEvidence"]
