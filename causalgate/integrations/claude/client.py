from __future__ import annotations

"""Small stdlib Claude Messages API client for CausalGate.

The adapter is optional and dependency-free.  In production you can replace it
with the official Anthropic SDK, but this module gives CausalGate a stable testable
boundary for building Claude requests, parsing JSON candidates, and running in a
cost-free dry-run mode.
"""

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from .prompts import build_scientific_research_prompt, build_scientific_system_prompt

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


class ClaudeAPIError(RuntimeError):
    """Raised when the Claude API request fails or returns invalid content."""


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def extract_first_json_object(text: str) -> Dict[str, Any]:
    """Extract the first JSON object from Claude text output.

    Handles fenced JSON and plain text with surrounding prose. Raises
    ``ClaudeAPIError`` when no valid object can be decoded.
    """

    if not isinstance(text, str) or not text.strip():
        raise ClaudeAPIError("Claude response is empty; expected a JSON object.")

    fenced = _JSON_FENCE_RE.search(text)
    candidates: List[str] = [fenced.group(1)] if fenced else []

    # Fallback: scan balanced top-level braces.
    start_positions = [i for i, ch in enumerate(text) if ch == "{"]
    for start in start_positions:
        depth = 0
        in_str = False
        escape = False
        for idx in range(start, len(text)):
            ch = text[idx]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start : idx + 1])
                    break

    for candidate in candidates:
        try:
            decoded = json.loads(candidate)
            if isinstance(decoded, Mapping):
                return dict(decoded)
        except Exception:
            continue
    raise ClaudeAPIError("Could not extract a valid JSON object from Claude output.")


@dataclass
class ClaudeAPIClient:
    """Minimal Claude Messages API client.

    ``dry_run=True`` returns a deterministic conservative hypothesis and never
    contacts the network.  This is the default mode for tests and local package
    validation when ``ANTHROPIC_API_KEY`` is not configured.
    """

    api_key: Optional[str] = None
    model: str = "claude-sonnet-4-6"
    api_url: str = "https://api.anthropic.com/v1/messages"
    anthropic_version: str = "2023-06-01"
    timeout_seconds: int = 60
    default_max_tokens: int = 1600
    default_temperature: float = 0.2
    dry_run: bool = False
    extra_headers: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            self.dry_run = True

    def build_messages_payload(self, prompt_payload: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": int(prompt_payload.get("max_tokens", self.default_max_tokens) or self.default_max_tokens),
            "temperature": float(prompt_payload.get("temperature", self.default_temperature) or self.default_temperature),
            "system": build_scientific_system_prompt(),
            "messages": [
                {
                    "role": "user",
                    "content": build_scientific_research_prompt(prompt_payload),
                }
            ],
        }

    def create_message(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        if self.dry_run:
            return self._dry_run_response(payload)

        body = json.dumps(self.build_messages_payload(payload)).encode("utf-8")
        headers = {
            "content-type": "application/json",
            "x-api-key": self.api_key or "",
            "anthropic-version": self.anthropic_version,
        }
        headers.update(self.extra_headers)
        req = urllib.request.Request(self.api_url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ClaudeAPIError(f"Claude API HTTP {exc.code}: {detail}") from exc
        except Exception as exc:
            raise ClaudeAPIError(f"Claude API request failed: {exc}") from exc

        try:
            decoded = json.loads(raw)
        except Exception as exc:
            raise ClaudeAPIError(f"Claude API returned non-JSON response: {raw[:500]}") from exc
        if isinstance(decoded, Mapping) and decoded.get("error"):
            raise ClaudeAPIError(f"Claude API error: {decoded.get('error')}")
        return dict(decoded)

    def propose_hypothesis(self, prompt_payload: Mapping[str, Any]) -> Dict[str, Any]:
        response = self.create_message(prompt_payload)
        return self.extract_hypothesis_from_response(response)

    def extract_hypothesis_from_response(self, response: Mapping[str, Any]) -> Dict[str, Any]:
        data = _as_dict(response)
        if isinstance(data.get("hypothesis"), Mapping):
            return dict(data.get("hypothesis"))

        content = data.get("content")
        texts: List[str] = []
        if isinstance(content, list):
            for block in content:
                if isinstance(block, Mapping) and block.get("type") == "text":
                    texts.append(_clean(block.get("text")))
        elif isinstance(content, str):
            texts.append(content)

        if not texts and isinstance(data.get("text"), str):
            texts.append(data.get("text"))
        if not texts:
            raise ClaudeAPIError("Claude response has no text content and no direct hypothesis object.")

        decoded = extract_first_json_object("\n".join(texts))
        hypothesis = decoded.get("hypothesis") if isinstance(decoded.get("hypothesis"), Mapping) else decoded
        return dict(hypothesis)

    def _dry_run_response(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        goal = _clean(payload.get("goal") or payload.get("research_goal") or payload.get("objective"), "scientific hypothesis candidate")
        feedback = _clean(payload.get("feedback") or payload.get("next_instruction"))
        treatment = _clean(payload.get("treatment"), "X")
        outcome = _clean(payload.get("outcome"), "Y")
        confounder = _clean(payload.get("confounder"), "Z")
        hypothesis = {
            "hypothesis_id": "claude_dry_run_candidate_001",
            "claim": f"{treatment} may influence {outcome} under explicit assumptions related to: {goal}",
            "claim_level": "hypothesis_only",
            "variables": {
                "treatment": treatment,
                "outcome": outcome,
                "mediators": [],
                "confounders": [confounder],
            },
            "candidate_equation": f"{outcome} = a*{treatment} + b*{confounder} + error",
            "dag": {
                "nodes": [treatment, outcome, confounder],
                "edges": [[confounder, treatment], [confounder, outcome], [treatment, outcome]],
            },
            "assumptions": [
                f"{confounder} is observed and measured before {treatment} and {outcome}.",
                f"{treatment} is temporally prior to {outcome}.",
                "No unsupported conclusion is made without external validation.",
            ],
            "measurable_predictions": [
                f"If {treatment} increases, {outcome} should change in a pre-specified direction within the observed follow-up window after adjusting for {confounder}."
            ],
            "falsification_tests": [
                "negative control outcome",
                "future-X placebo leakage test",
                "hidden-confounding sensitivity check",
            ],
            "data_requirements": [
                f"observations for {treatment}, {outcome}, and {confounder}",
                f"temporal ordering with {treatment} measured before {outcome}",
                "sufficient support for treated/control comparison",
            ],
            "adjustment_set": [confounder],
            "limitations": [
                "not experimentally confirmed",
                "requires external data, replication, and domain review",
                f"generated from dry_run mode; feedback context: {feedback or 'none'}",
            ],
        }
        return {"content": [{"type": "text", "text": json.dumps({"hypothesis": hypothesis}, ensure_ascii=False)}], "dry_run": True}


__all__ = ["ClaudeAPIClient", "ClaudeAPIError", "extract_first_json_object"]
