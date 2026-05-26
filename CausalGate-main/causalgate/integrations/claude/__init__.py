"""Claude API adapter for CausalGate scientific research loops."""

from .client import ClaudeAPIClient, ClaudeAPIError, extract_first_json_object
from .prompts import build_scientific_research_prompt, build_scientific_system_prompt
from .research_agent import ClaudeCausalGateResearchAgent, run_claude_research_cycle

__all__ = [
    "ClaudeAPIClient",
    "ClaudeAPIError",
    "extract_first_json_object",
    "build_scientific_research_prompt",
    "build_scientific_system_prompt",
    "ClaudeCausalGateResearchAgent",
    "run_claude_research_cycle",
]
