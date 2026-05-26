from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Protocol


@dataclass
class LLMResponse:
    """Normalized output from an LLM or LLM-like planner.

    This is intentionally not a final decision. The LLM proposes candidate
    actions and context; CausalGate's OperationalBrain and DecisionGate decide.
    """

    user_message: str = ""
    candidate_actions: List[Dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    raw_model_output: Dict[str, Any] = field(default_factory=dict)
    source: str = "llm_interface"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LLMClient(Protocol):
    """Minimal interface any GPT-OSS/Llama/API client must implement."""

    def propose_actions(self, user_message: str, context: Mapping[str, Any] | None = None) -> LLMResponse:
        ...


__all__ = ["LLMClient", "LLMResponse"]
