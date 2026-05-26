from __future__ import annotations

"""Append-only scientific ledger for CausalGate research loops.

The ledger is intentionally simple and stdlib-only: JSONL events, deterministic
event fields, and no background writes.  It is meant to preserve the reasoning
boundary between an LLM researcher and CausalGate's conservative veto.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


@dataclass
class ScientificLedgerEvent:
    """One append-only event from a scientific hypothesis loop."""

    run_id: str = ""
    step: int = 0
    event_type: str = "hypothesis_evaluated"
    hypothesis_id: str = ""
    hypothesis: Dict[str, Any] = field(default_factory=dict)
    verdict: Dict[str, Any] = field(default_factory=dict)
    feedback_in: str = ""
    next_instruction: str = ""
    status: str = "recorded"
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_utc_now)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ScientificLedgerEvent":
        data = _as_dict(payload)
        verdict = _as_dict(data.get("verdict") or data.get("causalgate_verdict"))
        hyp = _as_dict(data.get("hypothesis"))
        run_id = _clean_str(data.get("run_id") or hyp.get("run_id") or verdict.get("run_id"))
        step_raw = data.get("step", hyp.get("step", verdict.get("step", 0)))
        try:
            step = int(step_raw)
        except Exception:
            step = 0
        return cls(
            run_id=run_id,
            step=step,
            event_type=_clean_str(data.get("event_type"), "hypothesis_evaluated"),
            hypothesis_id=_clean_str(data.get("hypothesis_id") or hyp.get("hypothesis_id") or verdict.get("hypothesis_id")),
            hypothesis=hyp,
            verdict=verdict,
            feedback_in=_clean_str(data.get("feedback_in") or data.get("feedback")),
            next_instruction=_clean_str(data.get("next_instruction") or verdict.get("next_instruction")),
            status=_clean_str(data.get("status"), "recorded"),
            metadata=_as_dict(data.get("metadata")),
            timestamp=_clean_str(data.get("timestamp"), _utc_now()),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ScientificLedger:
    """JSONL-backed append-only ledger for hypothesis cycles."""

    def __init__(self, path: str | Path = "out/scientific/ledger.jsonl") -> None:
        self.path = Path(path)

    def append(self, event: Mapping[str, Any] | ScientificLedgerEvent) -> Dict[str, Any]:
        ledger_event = event if isinstance(event, ScientificLedgerEvent) else ScientificLedgerEvent.from_payload(event)
        payload = ledger_event.to_dict()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return payload

    def read(self, run_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            limit = int(limit)
        except Exception:
            limit = 50
        limit = max(1, min(limit, 500))
        rows: List[Dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if not text:
                    continue
                try:
                    item = json.loads(text)
                except Exception:
                    continue
                if run_id and item.get("run_id") != run_id:
                    continue
                rows.append(item)
        return rows[-limit:]

    def summary(self, run_id: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        rows = self.read(run_id=run_id, limit=limit)
        decisions: Dict[str, int] = {}
        last_decision = ""
        for row in rows:
            verdict = _as_dict(row.get("verdict"))
            decision = _clean_str(verdict.get("decision"), "UNKNOWN")
            decisions[decision] = decisions.get(decision, 0) + 1
            last_decision = decision
        return {
            "ledger_path": str(self.path),
            "run_id": run_id or "",
            "events": len(rows),
            "decisions": decisions,
            "last_decision": last_decision,
            "last_event": rows[-1] if rows else {},
        }


def append_scientific_ledger_event(payload: Mapping[str, Any], path: str | Path = "out/scientific/ledger.jsonl") -> Dict[str, Any]:
    return ScientificLedger(path).append(payload)


def read_scientific_ledger(path: str | Path = "out/scientific/ledger.jsonl", run_id: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    ledger = ScientificLedger(path)
    return {"events": ledger.read(run_id=run_id, limit=limit), "summary": ledger.summary(run_id=run_id, limit=limit)}


__all__ = [
    "ScientificLedger",
    "ScientificLedgerEvent",
    "append_scientific_ledger_event",
    "read_scientific_ledger",
]
