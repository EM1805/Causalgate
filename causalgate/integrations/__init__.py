"""Optional external integrations for CausalGate."""

from .gemini_dialogue_adapter import (
    GeminiDialogueAdapter,
    GeminiDialogueAdapterConfig,
    build_gemini_dialogue_prompt,
    make_gemini_dialogue_adapter_from_env,
    run_gemini_llm_dialogue,
)

__all__ = [
    "GeminiDialogueAdapter",
    "GeminiDialogueAdapterConfig",
    "build_gemini_dialogue_prompt",
    "make_gemini_dialogue_adapter_from_env",
    "run_gemini_llm_dialogue",
]
