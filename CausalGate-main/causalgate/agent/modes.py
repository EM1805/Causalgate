from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, Mapping


AGENT_MODE_NAMES = {
    "general_agent",
    "code_agent",
    "ops_agent",
    "finance_trading_agent",
}


@dataclass(frozen=True)
class AgentModePolicy:
    """Runtime policy profile for one CausalGate agent mode.

    Modes are not separate agents. They are conservative policy profiles used by
    the same CausalGateAgent to constrain which abstract actions may be executed.
    """

    name: str
    description: str
    default_risk_tolerance: str = "medium"
    allowed_domains: tuple[str, ...] = ()
    blocked_domains: tuple[str, ...] = ()
    allowed_action_types: tuple[str, ...] = ()
    blocked_action_types: tuple[str, ...] = ()
    allow_read_only: bool = True
    allow_tool_execution: bool = True
    allow_autonomous_low_risk: bool = True
    require_approval_for_medium_risk: bool = False
    require_approval_for_high_risk: bool = True
    veto_critical_by_default: bool = True
    production_changes_require_approval: bool = False
    database_mutation_requires_approval: bool = False
    live_trading_default: str = "not_applicable"
    money_transfer_default: str = "not_applicable"
    leverage_default: str = "not_applicable"
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, tuple):
                data[key] = list(value)
        return data


AGENT_MODES: Dict[str, AgentModePolicy] = {
    "general_agent": AgentModePolicy(
        name="general_agent",
        description="General low/medium-risk assistant profile for planning, reading, summarizing and safe utilities.",
        default_risk_tolerance="medium",
        allowed_domains=("general", "agent_safety", "agent_tools", "agent_memory"),
        blocked_domains=("trading",),
        blocked_action_types=("financial_transfer", "trade_execution", "leveraged_trade_execution"),
        require_approval_for_high_risk=True,
        veto_critical_by_default=True,
        notes=("Use this for normal assistant tasks; do not route production, code mutation, or live-money execution here.",),
    ),
    "code_agent": AgentModePolicy(
        name="code_agent",
        description="Code/repository profile for read, edit, test and patch workflows.",
        default_risk_tolerance="low_medium",
        allowed_domains=("general", "agent_safety", "agent_tools", "agent_memory", "code", "development"),
        blocked_domains=("trading", "finance"),
        allowed_action_types=("read", "mutation", "code_execution", "dependency_change", "external_read", "memory_read", "memory_write", "communication"),
        require_approval_for_medium_risk=False,
        require_approval_for_high_risk=True,
        veto_critical_by_default=True,
        notes=("Dangerous shell, deletion, secrets, remote push and security config changes should require approval or veto.",),
    ),
    "ops_agent": AgentModePolicy(
        name="ops_agent",
        description="Operations/cloud/production profile for deploy, database, incident and infrastructure actions.",
        default_risk_tolerance="low",
        allowed_domains=("general", "agent_safety", "agent_tools", "ops", "infrastructure", "agent_memory"),
        blocked_domains=("trading", "finance"),
        production_changes_require_approval=True,
        database_mutation_requires_approval=True,
        require_approval_for_medium_risk=True,
        require_approval_for_high_risk=True,
        veto_critical_by_default=True,
        notes=("Production deploys, destructive resources, DB mutation and secret rotation require trusted approval.",),
    ),
    "finance_trading_agent": AgentModePolicy(
        name="finance_trading_agent",
        description="Finance/trading profile. Read-only analysis and paper trading may pass; live money is veto-by-default.",
        default_risk_tolerance="very_low",
        allowed_domains=("general", "finance", "trading", "agent_safety", "agent_tools"),
        allowed_action_types=("financial_read", "external_read", "trade_execution", "trade_order_management", "risk_control", "portfolio_mutation", "financial_transfer", "payment_mutation", "credential_access", "communication"),
        allow_autonomous_low_risk=True,
        require_approval_for_medium_risk=True,
        require_approval_for_high_risk=True,
        veto_critical_by_default=True,
        live_trading_default="veto",
        money_transfer_default="veto",
        leverage_default="veto",
        notes=("Live trading, transfers, leverage and margin must never execute by default; route to paper trade/recommendation unless trusted approvals and limits exist.",),
    ),
}


def normalize_agent_mode(value: Any, default: str = "general_agent") -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "general": "general_agent",
        "default": "general_agent",
        "code": "code_agent",
        "dev": "code_agent",
        "developer": "code_agent",
        "ops": "ops_agent",
        "operations": "ops_agent",
        "prod": "ops_agent",
        "production": "ops_agent",
        "finance": "finance_trading_agent",
        "trading": "finance_trading_agent",
        "finance_agent": "finance_trading_agent",
        "trading_agent": "finance_trading_agent",
    }
    text = aliases.get(text, text)
    return text if text in AGENT_MODES else default


def get_agent_mode_policy(mode: Any, default: str = "general_agent") -> AgentModePolicy:
    return AGENT_MODES[normalize_agent_mode(mode, default=default)]


def infer_agent_mode(
    *,
    requested_mode: Any = None,
    candidate: Mapping[str, Any] | None = None,
    trusted_runtime_context: Mapping[str, Any] | None = None,
    default: str = "general_agent",
) -> str:
    """Infer a safe default mode when callers do not explicitly provide one."""

    if requested_mode:
        return normalize_agent_mode(requested_mode, default=default)

    trusted = dict(trusted_runtime_context or {})
    if trusted.get("agent_mode"):
        return normalize_agent_mode(trusted.get("agent_mode"), default=default)
    if trusted.get("live_trading") or trusted.get("real_money") or trusted.get("financial_action") or trusted.get("trading_action"):
        return "finance_trading_agent"
    if str(trusted.get("environment", "")).lower() in {"prod", "production"}:
        return "ops_agent"

    cand = dict(candidate or {})
    action_name = str(cand.get("action_name") or cand.get("candidate_action") or cand.get("selected_action") or "").lower()
    action_type = str(cand.get("action_type") or "").lower()
    domain = str(cand.get("domain") or "").lower()

    if domain in {"finance", "trading"} or action_type in {"financial_transfer", "trade_execution", "portfolio_mutation", "leveraged_trade_execution"}:
        return "finance_trading_agent"
    if any(token in action_name for token in ("order", "trade", "brokerage", "portfolio", "fund", "payment", "invoice", "payout")):
        return "finance_trading_agent"
    if domain in {"ops", "infrastructure"} or any(token in action_name for token in ("deploy", "database", "resource", "secret", "service", "production")):
        return "ops_agent"
    if any(token in action_name for token in ("file", "code", "shell", "test", "lint", "package")):
        return "code_agent"
    return normalize_agent_mode(default, default="general_agent")


def list_agent_modes() -> Dict[str, Dict[str, Any]]:
    return {name: policy.to_dict() for name, policy in AGENT_MODES.items()}


__all__ = [
    "AGENT_MODES",
    "AGENT_MODE_NAMES",
    "AgentModePolicy",
    "get_agent_mode_policy",
    "infer_agent_mode",
    "list_agent_modes",
    "normalize_agent_mode",
]
