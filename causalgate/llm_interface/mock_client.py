from __future__ import annotations

from typing import Any, Mapping

from .action_extractor import extract_candidate_actions
from .base import LLMResponse


class MockLLMClient:
    """Deterministic GPT-OSS stand-in for local tests and offline demos.

    It simulates the role of an LLM planner: propose candidate actions, but do
    not decide. The final decision still belongs to OperationalBrain/Gate.
    """

    name = "mock_llm_client"

    def propose_actions(self, user_message: str, context: Mapping[str, Any] | None = None) -> LLMResponse:
        extracted = extract_candidate_actions(user_message, context=context)
        return LLMResponse(
            user_message=extracted["user_message"],
            candidate_actions=list(extracted["candidate_actions"]),
            context=dict(extracted["context"]),
            raw_model_output={
                "client": self.name,
                "note": "Deterministic heuristic mock; replace with GPT-OSS/Llama client later.",
            },
            source=self.name,
        )


__all__ = ["MockLLMClient"]
