"""LLM interface layer for CausalGate.

This package is the boundary where GPT-OSS/Llama/API clients propose candidate
actions. It does not make final decisions; it feeds OperationalBrain.
"""

from .action_extractor import extract_candidate_actions
from .base import LLMClient, LLMResponse
from .mock_client import MockLLMClient
from .prompt_adapter import llm_response_to_brain_payload, propose_and_decide

__all__ = [
    "LLMClient",
    "LLMResponse",
    "MockLLMClient",
    "extract_candidate_actions",
    "llm_response_to_brain_payload",
    "propose_and_decide",
]
