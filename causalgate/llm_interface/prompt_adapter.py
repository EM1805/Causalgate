from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from causalgate.operational_brain import OperationalBrain

from .base import LLMResponse
from .mock_client import MockLLMClient


def llm_response_to_brain_payload(response: LLMResponse | Mapping[str, Any]) -> Dict[str, Any]:
    """Convert an LLMResponse into the payload expected by OperationalBrain."""

    if isinstance(response, LLMResponse):
        data = response.to_dict()
    else:
        data = dict(response or {})

    return {
        "user_message": data.get("user_message", ""),
        "candidate_actions": list(data.get("candidate_actions", []) or []),
        "context": dict(data.get("context", {}) or {}),
        "source": data.get("source", "llm_interface"),
        "llm_raw_model_output": dict(data.get("raw_model_output", {}) or {}),
    }


def propose_and_decide(
    user_message: str,
    context: Mapping[str, Any] | None = None,
    *,
    llm_client: Any | None = None,
    brain: OperationalBrain | None = None,
    audit_log_path: str | None = None,
) -> Dict[str, Any]:
    """Run the online chain and optionally append the decision to JSONL.

    Logging is opt-in so tests and embedded callers can stay side-effect free.
    In production, pass ``audit_log_path`` to activate the Learning Loop.
    """

    client = llm_client or MockLLMClient()
    operational_brain = brain or OperationalBrain()
    llm_response = client.propose_actions(user_message, context=context)
    payload = llm_response_to_brain_payload(llm_response)
    result = operational_brain.run(payload).to_dict()
    result["llm_response"] = llm_response.to_dict()

    if audit_log_path:
        from causalgate.learning import append_decision

        result["audit_event"] = append_decision(result, path=audit_log_path)

    return result


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Mock LLM -> CausalGate OperationalBrain decision demo.")
    parser.add_argument("--message", help="User message to analyze.")
    parser.add_argument("--input", help="Optional JSON file with user_message and context.")
    parser.add_argument("--out", default="out/llm_operational_decision.json")
    parser.add_argument("--audit-log", default="", help="Optional JSONL path to append the online decision event.")
    args = parser.parse_args(argv)

    if args.input:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        user_message = str(payload.get("user_message", ""))
        context = dict(payload.get("context", {}) or {})
    else:
        user_message = args.message or ""
        context = {}

    result = propose_and_decide(user_message, context=context, audit_log_path=args.audit_log or None)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    selected = result.get("selected", {})
    print(json.dumps({
        "status": "ok",
        "out": str(out_path),
        "selected_action": selected.get("selected_action"),
        "decision": selected.get("decision"),
        "runtime_decision": selected.get("runtime_decision"),
    }, indent=2))
    return 0


__all__ = ["llm_response_to_brain_payload", "propose_and_decide"]


if __name__ == "__main__":
    raise SystemExit(main())
