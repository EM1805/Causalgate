from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping


COMMUNICATION_ACTIONS = {
    "answer_directly",
    "ask_clarification",
    "abstain",
    "explain_block",
    "veto_sensitive_action",
}

TOOL_LIKE_ACTION_TYPES = {
    "tool_call",
    "state_change",
    "mutation",
    "admin",
    "trade_execution",
    "financial_transfer",
}


def as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def is_communication_action(action_name: str, action_type: str = "") -> bool:
    """Return True for agent responses that must not be sent to ToolGuard."""

    name = clean_str(action_name).lower()
    typ = clean_str(action_type).lower()
    if name in COMMUNICATION_ACTIONS:
        return True
    if typ == "communication" and name not in {
        "send_email",
        "send_email_external",
        "post_message",
        "notify_external_recipient",
    }:
        return True
    return False


@dataclass
class AgentRunResult:
    """Stable public result for one CausalGate agent turn."""

    status: str = "unknown"
    response_type: str = "unknown"
    user_message: str = ""
    selected_action: str = ""
    decision: str = "abstain"
    executed: bool = False
    blocked: bool = False
    needs_user_confirmation: bool = False

    llm_response: Dict[str, Any] = field(default_factory=dict)
    brain_result: Dict[str, Any] = field(default_factory=dict)
    tool_guard_result: Dict[str, Any] = field(default_factory=dict)
    tool_result: Any = None

    # Step 6: proposal-only safe alternative generated after the causal/safety
    # decision. Recommendations must never execute directly; callers must
    # re-submit them as new candidate actions through DecisionGate/ToolGuard.
    recommendation: Dict[str, Any] = field(default_factory=dict)
    recommended_action: Dict[str, Any] = field(default_factory=dict)
    recommendation_summary: str = ""
    recommendation_requires_recheck: bool = True

    # Step 7: structured offline causal outputs read by AgentEvidenceReader.
    # This is advisory evidence for the runtime; it never authorizes direct
    # execution and should not be treated as LLM-supplied truth.
    evidence_bundle: Dict[str, Any] = field(default_factory=dict)
    evidence_tier: str = "none"
    evidence_warnings: List[str] = field(default_factory=list)
    usable_for_autonomous_action: bool = False

    # Step 11: agent-mode and registry-policy hardening. This keeps the
    # abstract action registry (what may be proposed) separate from the tool
    # registry (what may actually execute).
    agent_mode: str = "general_agent"
    registry_policy_result: Dict[str, Any] = field(default_factory=dict)
    action_registry_registered: bool = False
    tool_registry_registered: bool = False

    audit_event: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
