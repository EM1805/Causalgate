from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from .modes import get_agent_mode_policy, infer_agent_mode, normalize_agent_mode
from .types import as_dict, clean_str, is_communication_action

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

LOW_RISK_TYPES = {"read", "external_read", "financial_read", "memory_read", "risk_control", "communication"}
HIGH_RISK_TYPES = {"mutation", "admin", "ops", "code_execution", "dependency_change", "credential_access", "financial_transfer", "payment_mutation", "trade_execution", "portfolio_mutation", "leveraged_trade_execution", "risk_policy_change", "memory_mutation"}
CRITICAL_RISK_TYPES = {"financial_transfer", "leveraged_trade_execution"}
REGISTRY_AUTHORITY_FIELDS = {"action_type", "domain", "risk_level", "requires_approval", "autonomous_allowed", "allowed_modes", "side_effect_level"}
REGISTRY_DEFAULT_FIELDS = {"description", "reversible", "recommended_alternative"}


@dataclass
class RegistryPolicyResult:
    allowed: bool = True
    status: str = "registry_policy_allowed"
    decision: str = "allow"
    needs_user_confirmation: bool = False
    reason: str = ""
    agent_mode: str = "general_agent"
    action_name: str = ""
    action_registered: bool = False
    tool_registered: bool = False
    action_type: str = ""
    domain: str = ""
    risk_level: str = "unknown"
    requires_approval: bool = False
    autonomous_allowed: bool = True
    allowed_modes: list[str] = field(default_factory=list)
    side_effect_level: str = "unknown"
    warnings: list[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def block(self) -> bool:
        return not self.allowed

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _boolish(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "yes", "1", "on", "required"}:
        return True
    if text in {"false", "no", "0", "off", "none"}:
        return False
    return default


def _listish(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable) and not isinstance(value, Mapping):
        return [str(item) for item in value if str(item).strip()]
    return []


def _parse_scalar(value: str) -> Any:
    text = value.strip()
    if not text:
        return ""
    if text[0:1] in {"'", '"'} and text[-1:] == text[0]:
        return text[1:-1]
    lower = text.lower()
    if lower in {"true", "yes"}:
        return True
    if lower in {"false", "no"}:
        return False
    if lower in {"null", "none"}:
        return None
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def _minimal_action_registry_yaml(text: str) -> Dict[str, Any]:
    """Small stdlib YAML fallback for action_registry.yaml.

    It intentionally supports only the subset used by CausalGate's registry:
    top-level `actions`, action-name mappings, scalar fields, list fields and
    one-level nested maps such as `default_params` and `maps_to`.
    """

    actions: Dict[str, Dict[str, Any]] = {}
    current_action = ""
    current_list_key = ""
    current_map_key = ""

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        stripped = raw_line.strip()
        indent = len(raw_line) - len(raw_line.lstrip(" "))

        if stripped == "actions:":
            continue

        if indent == 2 and stripped.endswith(":") and not stripped.startswith("-"):
            current_action = stripped[:-1].strip()
            actions[current_action] = {}
            current_list_key = ""
            current_map_key = ""
            continue

        if not current_action:
            continue

        if stripped.startswith("- "):
            item = _parse_scalar(stripped[2:])
            if current_list_key:
                actions[current_action].setdefault(current_list_key, []).append(item)
            continue

        if ":" not in stripped:
            continue

        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()

        if raw_value == "":
            if key in {"default_params", "maps_to"}:
                actions[current_action][key] = {}
                current_map_key = key
                current_list_key = ""
            else:
                actions[current_action][key] = []
                current_list_key = key
                current_map_key = ""
            continue

        if indent >= 6 and current_map_key:
            nested = actions[current_action].setdefault(current_map_key, {})
            if isinstance(nested, dict):
                nested[key] = _parse_scalar(raw_value)
            continue

        actions[current_action][key] = _parse_scalar(raw_value)
        current_list_key = key
        current_map_key = ""

    return {"actions": actions}


def _load_yaml_or_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    suffix = path.suffix.lower()
    if suffix == ".json":
        value = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        value = yaml.safe_load(text) if yaml is not None else _minimal_action_registry_yaml(text)
    elif yaml is not None:
        value = yaml.safe_load(text) or {}
    else:
        value = json.loads(text)
    return dict(value or {}) if isinstance(value, Mapping) else {}


def _risk_from_entry(entry: Mapping[str, Any]) -> str:
    explicit = clean_str(entry.get("risk_level")).lower()
    if explicit:
        return explicit
    typ = clean_str(entry.get("action_type")).lower()
    if typ in CRITICAL_RISK_TYPES:
        return "critical"
    if typ in HIGH_RISK_TYPES:
        return "high"
    if typ in LOW_RISK_TYPES:
        return "low"
    maps_to = as_dict(entry.get("maps_to"))
    try:
        mag = float(maps_to.get("magnitude_hint", 0.0) or 0.0)
    except Exception:
        mag = 0.0
    if mag >= 0.9:
        return "critical"
    if mag >= 0.65:
        return "high"
    if mag >= 0.35:
        return "medium"
    return "low" if typ else "unknown"


def _side_effect_from_entry(entry: Mapping[str, Any]) -> str:
    explicit = clean_str(entry.get("side_effect_level")).lower()
    if explicit:
        return explicit
    typ = clean_str(entry.get("action_type")).lower()
    if typ in {"read", "external_read", "financial_read", "memory_read"}:
        return "none"
    if typ in {"communication", "sharing", "external_call"}:
        return "external"
    if typ in {"mutation", "memory_write", "memory_mutation", "payment_mutation"}:
        return "state_change"
    if typ in {"ops", "admin", "code_execution", "dependency_change", "credential_access"}:
        return "system_change"
    if typ in {"financial_transfer", "trade_execution", "portfolio_mutation", "leveraged_trade_execution"}:
        return "money_or_market"
    return "unknown"


def _registry_overlay(entry: Mapping[str, Any], payload: Mapping[str, Any]) -> Dict[str, Any]:
    combined = dict(payload or {})
    if not entry:
        return combined
    for key in REGISTRY_DEFAULT_FIELDS:
        if key in entry and key not in combined:
            combined[key] = entry[key]
    for key in REGISTRY_AUTHORITY_FIELDS:
        if key in entry:
            combined[key] = entry[key]
    combined.setdefault("risk_level", _risk_from_entry(entry))
    combined.setdefault("side_effect_level", _side_effect_from_entry(entry))
    combined.setdefault("allowed_modes", _listish(entry.get("allowed_modes")))
    combined.setdefault("autonomous_allowed", entry.get("autonomous_allowed", True))
    combined["action_registry_registered"] = True
    return combined


class ActionRegistry:
    def __init__(self, path: str | Path = "action_registry.yaml") -> None:
        self.path = Path(path)
        self.raw = _load_yaml_or_json(self.path)
        self.actions: Dict[str, Dict[str, Any]] = {}
        raw_actions = self.raw.get("actions", self.raw)
        if isinstance(raw_actions, Mapping):
            for name, spec in raw_actions.items():
                entry = dict(spec) if isinstance(spec, Mapping) else {"description": str(spec)}
                entry.setdefault("name", str(name))
                self.actions[str(name)] = entry

    def get(self, action_name: str) -> Dict[str, Any]:
        return dict(self.actions.get(clean_str(action_name), {}))

    def contains(self, action_name: str) -> bool:
        return clean_str(action_name) in self.actions

    def to_dict(self) -> Dict[str, Any]:
        return {name: dict(spec) for name, spec in sorted(self.actions.items())}


class AgentRegistryPolicy:
    def __init__(self, *, action_registry_path: str | Path = "action_registry.yaml", default_agent_mode: str = "general_agent") -> None:
        self.action_registry = ActionRegistry(action_registry_path)
        self.default_agent_mode = normalize_agent_mode(default_agent_mode)

    def resolve_mode(self, *, requested_mode: Any = None, candidate: Mapping[str, Any] | None = None, trusted_runtime_context: Mapping[str, Any] | None = None) -> str:
        return infer_agent_mode(requested_mode=requested_mode, candidate=candidate, trusted_runtime_context=trusted_runtime_context, default=self.default_agent_mode)

    def enrich_candidate(self, candidate: Mapping[str, Any], *, agent_mode: str | None = None, trusted_runtime_context: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        out = dict(candidate or {})
        action_name = clean_str(out.get("action_name") or out.get("candidate_action") or out.get("selected_action"))
        out.setdefault("action_name", action_name)
        out.setdefault("candidate_action", action_name)
        entry = self.action_registry.get(action_name)
        preview = _registry_overlay(entry, out) if entry else out
        mode = self.resolve_mode(requested_mode=agent_mode, candidate=preview, trusted_runtime_context=trusted_runtime_context)
        out["agent_mode"] = mode
        if entry:
            out = _registry_overlay(entry, out)
            params = {}
            params.update(as_dict(entry.get("default_params")))
            params.update(as_dict(candidate.get("params") if isinstance(candidate, Mapping) else {}))
            out["params"] = params
        else:
            out.setdefault("risk_level", clean_str(out.get("risk_level"), "unknown"))
            out.setdefault("side_effect_level", clean_str(out.get("side_effect_level"), "unknown"))
            out.setdefault("allowed_modes", [])
            out.setdefault("autonomous_allowed", True)
            out.setdefault("action_registry_registered", False)
        out["registry_policy"] = self.validate_selected_action(out, agent_mode=mode, trusted_runtime_context=trusted_runtime_context, tool_registered=False, execution_requested=False, pre_execution=True).to_dict()
        return out

    def validate_selected_action(self, action_payload: Mapping[str, Any], *, agent_mode: str | None = None, trusted_runtime_context: Mapping[str, Any] | None = None, tool_registered: bool = False, execution_requested: bool = True, pre_execution: bool = False) -> RegistryPolicyResult:
        payload = dict(action_payload or {})
        action_name = clean_str(payload.get("action_name") or payload.get("candidate_action") or payload.get("selected_action"))
        entry = self.action_registry.get(action_name)
        combined = _registry_overlay(entry, payload) if entry else payload
        trusted = {}
        trusted.update(as_dict(trusted_runtime_context))
        trusted.update(as_dict(payload.get("trusted_runtime_context") or payload.get("trusted_context")))
        params = as_dict(combined.get("params"))
        trusted_view = dict(params)
        trusted_view.update(trusted)
        mode = self.resolve_mode(requested_mode=agent_mode or payload.get("agent_mode"), candidate=combined, trusted_runtime_context=trusted)
        policy = get_agent_mode_policy(mode)
        action_type = clean_str(combined.get("action_type")).lower()
        domain = clean_str(combined.get("domain")).lower()
        risk_level = clean_str(combined.get("risk_level") or _risk_from_entry(combined), "unknown").lower()
        side_effect_level = clean_str(combined.get("side_effect_level") or _side_effect_from_entry(combined), "unknown").lower()
        requires_approval = _boolish(combined.get("requires_approval"), default=False)
        autonomous_allowed = _boolish(combined.get("autonomous_allowed"), default=True)
        allowed_modes = _listish(combined.get("allowed_modes"))
        warnings: list[str] = []
        base = RegistryPolicyResult(True, "registry_policy_allowed", "allow", False, "Action passed registry/mode policy.", mode, action_name, bool(entry), bool(tool_registered), action_type, domain, risk_level, requires_approval, autonomous_allowed, allowed_modes, side_effect_level, warnings, {"execution_requested": bool(execution_requested), "pre_execution": bool(pre_execution)})
        if is_communication_action(action_name, action_type):
            base.reason = "Communication action; registry policy does not require ToolRegistry execution."
            return base
        if allowed_modes and mode not in {normalize_agent_mode(m, default=m) for m in allowed_modes}:
            base.allowed = False; base.status = "action_not_allowed_in_agent_mode"; base.decision = "veto"; base.reason = f"Action '{action_name}' is not allowed in agent_mode '{mode}'."; return base
        if domain in set(policy.blocked_domains):
            base.allowed = False; base.status = "domain_blocked_in_agent_mode"; base.decision = "veto"; base.reason = f"Domain '{domain}' is blocked in agent_mode '{mode}'."; return base
        if policy.allowed_domains and domain and domain not in set(policy.allowed_domains):
            warnings.append(f"domain '{domain}' is outside preferred domains for {mode}")
        if action_type in set(policy.blocked_action_types):
            base.allowed = False; base.status = "action_type_blocked_in_agent_mode"; base.decision = "veto"; base.reason = f"Action type '{action_type}' is blocked in agent_mode '{mode}'."; return base
        approval_present = _boolish(trusted_view.get("approval_present"), default=False)
        env = clean_str(trusted_view.get("environment")).lower()
        production = env in {"prod", "production"} or _boolish(trusted_view.get("production"), default=False)
        live_trading = _boolish(trusted_view.get("live_trading"), default=False)
        real_money = _boolish(trusted_view.get("real_money"), default=False)
        financial_action = _boolish(trusted_view.get("financial_action"), default=False)
        transfer_like = action_type in {"financial_transfer", "payment_mutation"} or "transfer" in action_name or "payout" in action_name
        leverage = _boolish(trusted_view.get("leverage_used"), default=False) or _boolish(trusted_view.get("margin_used"), default=False) or action_type == "leveraged_trade_execution"
        risk_limits_present = _boolish(trusted_view.get("risk_limits_present"), default=False)
        notional_known = _boolish(trusted_view.get("notional_amount_known"), default=False)
        if not bool(entry):
            warnings.append("action is not present in action_registry")
            if execution_requested and tool_registered:
                base.allowed = False; base.status = "action_not_registered"; base.decision = "ask_clarification"; base.needs_user_confirmation = True; base.reason = f"Tool '{action_name}' is registered but abstract action is missing from action_registry."; return base
        if policy.production_changes_require_approval and production and action_type in {"ops", "admin", "mutation", "code_execution", "dependency_change"} and not approval_present:
            base.allowed = False; base.status = "production_approval_required"; base.decision = "ask_clarification"; base.needs_user_confirmation = True; base.reason = "Production-changing action requires trusted approval in ops_agent mode."; return base
        if policy.database_mutation_requires_approval and ("database" in action_name or action_type == "database_write") and not approval_present:
            base.allowed = False; base.status = "database_approval_required"; base.decision = "ask_clarification"; base.needs_user_confirmation = True; base.reason = "Database mutation requires trusted approval in ops_agent mode."; return base
        if mode == "finance_trading_agent":
            if leverage and policy.leverage_default == "veto":
                base.allowed = False; base.status = "leverage_veto_default"; base.decision = "veto"; base.reason = "Leverage/margin actions are veto-by-default in finance_trading_agent mode."; return base
            if transfer_like and policy.money_transfer_default == "veto":
                base.allowed = False; base.status = "money_transfer_veto_default"; base.decision = "veto"; base.reason = "Money transfer is veto-by-default in finance_trading_agent mode."; return base
            if live_trading and real_money and policy.live_trading_default == "veto":
                if not (approval_present and risk_limits_present and notional_known):
                    base.allowed = False; base.status = "live_trading_veto_default"; base.decision = "veto"; base.reason = "Live real-money trading requires trusted approval, risk limits and known notional amount."; return base
                warnings.append("live trading allowed only because trusted approval, risk limits and notional amount are present")
            if financial_action and risk_level in {"high", "critical"} and not approval_present:
                base.allowed = False; base.status = "financial_approval_required"; base.decision = "ask_clarification" if risk_level == "high" else "veto"; base.needs_user_confirmation = risk_level != "critical"; base.reason = "High-risk financial action requires trusted approval."; return base
        if not autonomous_allowed and execution_requested:
            base.allowed = False; base.status = "autonomous_execution_not_allowed"; base.decision = "ask_clarification"; base.needs_user_confirmation = True; base.reason = "action_registry marks this action as not autonomous; request confirmation or use a proposal-only recommendation."; return base
        if requires_approval and execution_requested and not approval_present:
            base.allowed = False; base.status = "approval_required"; base.decision = "ask_clarification"; base.needs_user_confirmation = True; base.reason = "Action requires trusted approval before execution."; return base
        if policy.veto_critical_by_default and risk_level == "critical" and execution_requested and not approval_present:
            base.allowed = False; base.status = "critical_risk_veto_default"; base.decision = "veto"; base.reason = "Critical-risk action is veto-by-default without trusted approval."; return base
        if policy.require_approval_for_high_risk and risk_level in {"high", "critical"} and execution_requested and not approval_present:
            base.allowed = False; base.status = "high_risk_approval_required"; base.decision = "ask_clarification" if risk_level == "high" else "veto"; base.needs_user_confirmation = risk_level != "critical"; base.reason = f"{mode} requires trusted approval for {risk_level}-risk actions."; return base
        if policy.require_approval_for_medium_risk and risk_level == "medium" and execution_requested and not approval_present:
            base.allowed = False; base.status = "medium_risk_approval_required"; base.decision = "ask_clarification"; base.needs_user_confirmation = True; base.reason = f"{mode} requires trusted approval for medium-risk actions."; return base
        return base


__all__ = ["ActionRegistry", "AgentRegistryPolicy", "RegistryPolicyResult"]
