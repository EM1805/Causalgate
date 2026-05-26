from __future__ import annotations

from typing import Any, Dict, Mapping


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def build_blocked_response(decision_package: Mapping[str, Any], *, execution_action: str = "block") -> Dict[str, Any]:
    """Build a compact agent-facing response for non-executed tool calls."""

    decision = _clean_str(decision_package.get("decision"), "abstain")
    selected_action = _clean_str(
        decision_package.get("selected_action") or decision_package.get("candidate_action"),
        "candidate_action",
    )
    reason = _clean_str(decision_package.get("reason"), "CausalGate did not authorize tool execution.")
    instruction = _clean_str(decision_package.get("llm_instruction"), "Do not execute the tool.")

    if execution_action == "ask_user" or decision == "ask_clarification":
        message = f"CausalGate requires clarification before executing {selected_action}."
        next_step = "ask_user_or_human_for_confirmation"
    elif decision == "veto":
        message = f"CausalGate vetoed execution of {selected_action}."
        next_step = "offer_safer_alternative_or_stop"
    else:
        message = f"CausalGate blocked execution of {selected_action}."
        next_step = "route_to_review_or_choose_safer_action"

    return {
        "message": message,
        "decision": decision,
        "selected_action": selected_action,
        "execution_action": execution_action,
        "reason": reason,
        "llm_instruction": instruction,
        "next_step": next_step,
        "reason_codes": list(decision_package.get("reason_codes", []) or []),
    }


__all__ = ["build_blocked_response"]
