from __future__ import annotations

"""Prompt templates for Claude + CausalGate scientific research loops.

The prompts intentionally constrain Claude to produce hypothesis candidates,
not confirmed discoveries. CausalGate remains the verifier/veto layer.
"""

from typing import Any, Mapping


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def build_scientific_system_prompt() -> str:
    return (
        "You are the language/planning component in an CausalGate-reviewed scientific research loop. "
        "Your task is to propose testable scientific hypothesis candidates, not confirmed laws. "
        "Never claim proof, confirmation, discovery, or final truth. Use conservative language. "
        "Every candidate must include claim, variables, DAG edges, assumptions, measurable predictions, "
        "falsification tests, data requirements, and claim_level='hypothesis_only'. "
        "CausalGate is the causal/scientific veto and may return REVISE, TEST_MORE, BLOCK, ABSTAIN, or FINAL_CANDIDATE. "
        "Return only one JSON object with a top-level key 'hypothesis'."
    )


def build_scientific_research_prompt(payload: Mapping[str, Any]) -> str:
    goal = _clean(payload.get("goal") or payload.get("research_goal") or payload.get("objective"), "Generate a conservative scientific hypothesis candidate.")
    feedback = _clean(payload.get("feedback") or payload.get("next_instruction") or payload.get("previous_feedback"))
    domain = _clean(payload.get("domain"), "general")
    constraints = payload.get("constraints") or []
    constraints_text = "\n".join(f"- {item}" for item in constraints) if isinstance(constraints, list) else _clean(constraints)

    return (
        "Research goal:\n"
        f"{goal}\n\n"
        f"Domain: {domain}\n\n"
        "Hard constraints:\n"
        "- Output must be a hypothesis candidate only.\n"
        "- Do not say discovered, proved, confirmed, law, theorem, or true unless describing a limitation.\n"
        "- Include at least one measurable prediction with direction and time/observation window.\n"
        "- Include negative control, placebo/future-X leakage check, and sensitivity/hidden-confounding check.\n"
        "- Include data requirements and adjustment_set when confounders are present.\n"
        f"{constraints_text}\n\n"
        "Previous CausalGate feedback / revision instruction:\n"
        f"{feedback or 'None yet.'}\n\n"
        "Return only JSON in this shape:\n"
        "{\n"
        "  \"hypothesis\": {\n"
        "    \"hypothesis_id\": \"short_id\",\n"
        "    \"claim\": \"X may influence Y under explicit assumptions\",\n"
        "    \"claim_level\": \"hypothesis_only\",\n"
        "    \"variables\": {\"treatment\": \"X\", \"outcome\": \"Y\", \"mediators\": [], \"confounders\": []},\n"
        "    \"candidate_equation\": \"optional symbolic candidate\",\n"
        "    \"dag\": {\"nodes\": [\"X\", \"Y\"], \"edges\": [[\"X\", \"Y\"]]},\n"
        "    \"assumptions\": [\"...\"],\n"
        "    \"measurable_predictions\": [\"If X increases, Y should change measurably within ...\"],\n"
        "    \"falsification_tests\": [\"negative control outcome\", \"future-X placebo leakage test\", \"hidden-confounding sensitivity check\"],\n"
        "    \"data_requirements\": [\"...\"],\n"
        "    \"adjustment_set\": [],\n"
        "    \"limitations\": [\"not experimentally confirmed\"]\n"
        "  }\n"
        "}"
    )


__all__ = ["build_scientific_system_prompt", "build_scientific_research_prompt"]
