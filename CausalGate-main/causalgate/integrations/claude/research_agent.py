from __future__ import annotations

"""Claude + CausalGate scientific agent controller.

This controller keeps the roles separate:
- Claude proposes/revises text hypotheses.
- CausalGate evaluates, vetoes, asks for tests, or marks a final candidate.
- The ledger records each CausalGate-reviewed step.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping
from uuid import uuid4

from causalgate.scientific import run_research_step

from .client import ClaudeAPIClient

_TERMINAL = {"FINAL_CANDIDATE", "BLOCK"}


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


@dataclass
class ClaudeCausalGateCycleResult:
    run_id: str
    status: str
    goal: str
    steps_completed: int
    max_steps: int
    final_decision: str
    next_instruction: str
    should_continue: bool
    step_results: List[Dict[str, Any]] = field(default_factory=list)
    dry_run: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ClaudeCausalGateResearchAgent:
    """Bounded Claude-propose / CausalGate-veto research loop."""

    def __init__(
        self,
        claude_client: ClaudeAPIClient | None = None,
        ledger_path: str = "out/scientific/ledger.jsonl",
        enable_identification: bool = True,
    ) -> None:
        self.claude_client = claude_client or ClaudeAPIClient()
        self.ledger_path = ledger_path
        self.enable_identification = enable_identification

    def run(self, payload: Mapping[str, Any]) -> ClaudeCausalGateCycleResult:
        data = _as_dict(payload)
        run_id = _clean(data.get("run_id"), "claude_causalgate_" + uuid4().hex[:12])
        goal = _clean(data.get("goal") or data.get("research_goal") or data.get("objective"), "Generate a conservative scientific hypothesis candidate.")
        max_steps = max(1, min(_as_int(data.get("max_steps"), 3), 15))
        ledger_path = _clean(data.get("ledger_path"), self.ledger_path)
        write_ledger = bool(data.get("write_ledger", True))
        feedback = _clean(data.get("feedback") or data.get("next_instruction"))

        step_results: List[Dict[str, Any]] = []
        final_decision = "ABSTAIN"
        next_instruction = feedback
        status = "not_started"
        should_continue = True

        for idx in range(max_steps):
            step_no = _as_int(data.get("start_step"), 1) + idx
            prompt_payload = dict(data)
            prompt_payload.update({
                "run_id": run_id,
                "goal": goal,
                "feedback": next_instruction,
                "step": step_no,
            })
            hypothesis = self.claude_client.propose_hypothesis(prompt_payload)
            step_payload = {
                "run_id": run_id,
                "step": step_no,
                "goal": goal,
                "feedback": next_instruction,
                "hypothesis": hypothesis,
                "write_ledger": write_ledger,
                "ledger_path": ledger_path,
                "enable_identification": self.enable_identification,
            }
            result = run_research_step(step_payload, ledger_path=ledger_path, enable_identification=self.enable_identification)
            result["proposer"] = {
                "provider": "anthropic/claude",
                "model": self.claude_client.model,
                "dry_run": bool(self.claude_client.dry_run),
            }
            step_results.append(result)

            verdict = _as_dict(result.get("verdict"))
            final_decision = _clean(verdict.get("decision"), "ABSTAIN")
            next_instruction = _clean(result.get("next_instruction") or verdict.get("next_instruction"))
            if final_decision in _TERMINAL:
                status = "final_candidate_ready_for_external_validation" if final_decision == "FINAL_CANDIDATE" else "blocked"
                should_continue = False
                break
        else:
            status = "max_steps_reached"
            should_continue = final_decision not in _TERMINAL

        return ClaudeCausalGateCycleResult(
            run_id=run_id,
            status=status,
            goal=goal,
            steps_completed=len(step_results),
            max_steps=max_steps,
            final_decision=final_decision,
            next_instruction=next_instruction,
            should_continue=should_continue,
            step_results=step_results,
            dry_run=bool(self.claude_client.dry_run),
        )


def run_claude_research_cycle(payload: Mapping[str, Any]) -> Dict[str, Any]:
    data = _as_dict(payload)
    client = ClaudeAPIClient(
        api_key=data.get("api_key"),
        model=_clean(data.get("model"), "claude-sonnet-4-6"),
        dry_run=bool(data.get("dry_run", False)),
    )
    agent = ClaudeCausalGateResearchAgent(
        claude_client=client,
        ledger_path=_clean(data.get("ledger_path"), "out/scientific/ledger.jsonl"),
        enable_identification=bool(data.get("enable_identification", True)),
    )
    return agent.run(data).to_dict()


__all__ = ["ClaudeCausalGateResearchAgent", "ClaudeCausalGateCycleResult", "run_claude_research_cycle"]
