from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import yaml

PASS = "PASS"
REVIEW = "REVIEW"
HARD_BLOCK = "HARD_BLOCK"
VALID_FIREWALL_ACTIONS = {PASS, REVIEW, HARD_BLOCK}
_DECISION_RANK = {PASS: 0, REVIEW: 1, HARD_BLOCK: 2}


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _clean_key(value: Any) -> str:
    return _clean_str(value).lower().replace("-", "_")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1
    return _clean_str(value).lower() in {"1", "true", "yes", "y", "on", "present", "approved"}


def _normalize_action(value: Any, default: str = REVIEW) -> str:
    text = _clean_str(value, default).upper().replace("-", "_")
    aliases = {
        "ALLOW": PASS,
        "EXECUTE": PASS,
        "PASS_WITH_WARNING": REVIEW,
        "WARN": REVIEW,
        "ASK_USER": REVIEW,
        "ASK_CLARIFICATION": REVIEW,
        "BLOCK": HARD_BLOCK,
        "VETO": HARD_BLOCK,
        "DENY": HARD_BLOCK,
    }
    text = aliases.get(text, text)
    return text if text in VALID_FIREWALL_ACTIONS else default


def _get_path(context: Mapping[str, Any], dotted: str) -> Any:
    value: Any = context
    for part in str(dotted or "").split("."):
        if isinstance(value, Mapping) and part in value:
            value = value[part]
        else:
            return None
    return value


def _match_value(observed: Any, expected: Any) -> bool:
    if isinstance(expected, Mapping):
        if "in" in expected:
            return any(_match_value(observed, item) for item in _as_list(expected.get("in")))
        if "not_in" in expected:
            return not any(_match_value(observed, item) for item in _as_list(expected.get("not_in")))
        if "exists" in expected:
            return bool(observed not in (None, "", [], {})) == _truthy(expected.get("exists"))
        if "equals" in expected:
            return _match_value(observed, expected.get("equals"))
        if "not_equals" in expected:
            return not _match_value(observed, expected.get("not_equals"))
        if "contains" in expected:
            needle = _clean_str(expected.get("contains")).lower()
            return needle in _clean_str(observed).lower()
        if "truthy" in expected:
            return _truthy(observed) == _truthy(expected.get("truthy"))
        if "gte" in expected:
            try:
                return float(observed) >= float(expected.get("gte"))
            except Exception:
                return False
        if "lte" in expected:
            try:
                return float(observed) <= float(expected.get("lte"))
            except Exception:
                return False
        return False

    if isinstance(expected, (list, tuple, set)):
        return any(_match_value(observed, item) for item in expected)

    if isinstance(expected, bool):
        return _truthy(observed) == expected

    return _clean_str(observed).lower() == _clean_str(expected).lower()


def build_firewall_context(
    action_payload: Mapping[str, Any] | None,
    *,
    tool_name: str = "",
    tool_args: Mapping[str, Any] | None = None,
    trusted_runtime_context: Mapping[str, Any] | None = None,
    untrusted_llm_context: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Flatten trusted action/tool facts used by policy-as-code rules.

    Runtime facts from ``trusted_runtime_context`` override legacy payload fields.
    Untrusted LLM context is preserved for audit but never used to override trusted
    security-sensitive fields.
    """

    payload = _as_dict(action_payload)
    params = _as_dict(payload.get("params"))
    legacy_context = _as_dict(payload.get("context"))
    trusted = _as_dict(payload.get("trusted_runtime_context") or payload.get("trusted_context"))
    trusted.update(_as_dict(trusted_runtime_context))
    untrusted = _as_dict(payload.get("untrusted_llm_context") or payload.get("llm_context"))
    untrusted.update(_as_dict(untrusted_llm_context))
    args = _as_dict(tool_args or payload.get("tool_args"))

    context: Dict[str, Any] = {}
    for source in (params, legacy_context, payload, trusted):
        for key, value in source.items():
            if key in {"params", "context", "trusted_runtime_context", "trusted_context", "untrusted_llm_context", "llm_context"}:
                continue
            context[key] = value

    resolved_tool_name = _clean_str(
        tool_name
        or trusted.get("tool_name")
        or payload.get("tool_name")
        or payload.get("action_name")
        or payload.get("candidate_action")
    )
    context["tool_name"] = resolved_tool_name
    context["action_name"] = _clean_str(payload.get("action_name") or payload.get("candidate_action") or resolved_tool_name)
    context["tool_args"] = args
    context["trusted_runtime_context"] = trusted
    context["untrusted_llm_context"] = untrusted

    for key in (
        "approval_present",
        "rollback_available",
        "requires_user_confirmation",
        "recipient_external",
        "share_scope_external",
        "policy_bypass",
        "live_trading",
        "real_money",
        "external_counterparty",
        "irreversible",
    ):
        if key in context:
            context[key] = _truthy(context.get(key))

    reversibility = _clean_key(context.get("reversibility"))
    if "irreversible" not in context and reversibility in {"irreversible", "not_reversible", "none"}:
        context["irreversible"] = True
    context.setdefault("environment", "unknown")
    context.setdefault("risk_level", "unknown")
    context.setdefault("target_resource", "")
    return context


@dataclass(frozen=True)
class FirewallRule:
    id: str
    action: str = REVIEW
    when: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    reason_code: str = ""
    priority: int = 100

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FirewallRule":
        data = dict(payload or {})
        rule_id = _clean_str(data.get("id") or data.get("name"))
        if not rule_id:
            raise ValueError("firewall rule missing id")
        return cls(
            id=rule_id,
            action=_normalize_action(data.get("action"), REVIEW),
            when=_as_dict(data.get("when")),
            description=_clean_str(data.get("description")),
            reason_code=_clean_str(data.get("reason_code") or f"FIREWALL_RULE_{rule_id}".upper().replace("-", "_")),
            priority=int(data.get("priority", 100)),
        )

    def matches(self, context: Mapping[str, Any]) -> bool:
        if not self.when:
            return True
        for key, expected in self.when.items():
            if not _match_value(_get_path(context, key), expected):
                return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentFirewallPolicy:
    version: str = "agent_action_firewall_policy_v1_step98"
    default_action: str = REVIEW
    fail_closed_on_policy_error: bool = True
    required_trusted_fields: List[str] = field(default_factory=list)
    rules: List[FirewallRule] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "AgentFirewallPolicy":
        data = dict(payload or {})
        rules = [FirewallRule.from_dict(item) for item in _as_list(data.get("rules")) if isinstance(item, Mapping)]
        return cls(
            version=_clean_str(data.get("version"), "agent_action_firewall_policy_v1_step98"),
            default_action=_normalize_action(data.get("default_action"), REVIEW),
            fail_closed_on_policy_error=bool(data.get("fail_closed_on_policy_error", True)),
            required_trusted_fields=[_clean_str(v) for v in _as_list(data.get("required_trusted_fields")) if _clean_str(v)],
            rules=sorted(rules, key=lambda rule: rule.priority),
        )

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> "AgentFirewallPolicy":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if not isinstance(raw, Mapping):
            raise ValueError("firewall policy YAML must contain a mapping")
        return cls.from_dict(raw)

    def evaluate(self, context: Mapping[str, Any]) -> Dict[str, Any]:
        try:
            missing = [field for field in self.required_trusted_fields if _get_path(context, field) in (None, "", [], {})]
            matched: List[Dict[str, Any]] = []
            final_action = self.default_action
            if missing:
                final_action = HARD_BLOCK if self.fail_closed_on_policy_error else REVIEW
                matched.append({
                    "id": "missing_required_trusted_fields",
                    "action": final_action,
                    "reason_code": "FIREWALL_MISSING_REQUIRED_TRUSTED_FIELDS",
                    "description": "Required trusted runtime fields are missing.",
                    "missing_fields": missing,
                })
            else:
                for rule in self.rules:
                    if rule.matches(context):
                        matched.append(rule.to_dict())
                        if _DECISION_RANK[rule.action] > _DECISION_RANK[final_action]:
                            final_action = rule.action

            return {
                "policy_version": self.version,
                "firewall_decision": final_action,
                "matched_rules": matched,
                "matched_rule_ids": [str(rule.get("id")) for rule in matched],
                "reason_codes": [str(rule.get("reason_code")) for rule in matched if rule.get("reason_code")],
                "missing_required_trusted_fields": missing if "missing" in locals() else [],
                "fail_closed_on_policy_error": int(self.fail_closed_on_policy_error),
            }
        except Exception as exc:
            decision = HARD_BLOCK if self.fail_closed_on_policy_error else REVIEW
            return {
                "policy_version": self.version,
                "firewall_decision": decision,
                "matched_rules": [],
                "matched_rule_ids": [],
                "reason_codes": ["FIREWALL_POLICY_EVALUATION_ERROR"],
                "missing_required_trusted_fields": [],
                "fail_closed_on_policy_error": int(self.fail_closed_on_policy_error),
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "default_action": self.default_action,
            "fail_closed_on_policy_error": self.fail_closed_on_policy_error,
            "required_trusted_fields": list(self.required_trusted_fields),
            "rules": [rule.to_dict() for rule in self.rules],
        }


def load_firewall_policy(policy: str | Path | Mapping[str, Any] | AgentFirewallPolicy | None = None) -> AgentFirewallPolicy:
    if isinstance(policy, AgentFirewallPolicy):
        return policy
    if isinstance(policy, Mapping):
        return AgentFirewallPolicy.from_dict(policy)
    if policy is None or _clean_str(policy) == "":
        return default_firewall_policy()
    return AgentFirewallPolicy.from_yaml_file(policy)


def default_firewall_policy() -> AgentFirewallPolicy:
    return AgentFirewallPolicy.from_dict({
        "version": "agent_action_firewall_policy_v1_step98_default",
        "default_action": "PASS",
        "fail_closed_on_policy_error": True,
        "required_trusted_fields": ["environment"],
        "rules": [
            {
                "id": "block_destructive_production_without_approval",
                "priority": 10,
                "action": "HARD_BLOCK",
                "reason_code": "FIREWALL_BLOCK_DESTRUCTIVE_PROD_NO_APPROVAL",
                "description": "Block destructive production actions without trusted approval and rollback.",
                "when": {
                    "environment": "production",
                    "action_type": ["mutation", "delete", "destructive"],
                    "approval_present": False,
                    "rollback_available": False,
                },
            },
            {
                "id": "review_external_data_or_message",
                "priority": 20,
                "action": "REVIEW",
                "reason_code": "FIREWALL_REVIEW_EXTERNAL_DATA_FLOW",
                "description": "Route external data sharing or external communication to review.",
                "when": {"recipient_external": True},
            },
            {
                "id": "review_critical_or_high_risk",
                "priority": 30,
                "action": "REVIEW",
                "reason_code": "FIREWALL_REVIEW_HIGH_RISK_ACTION",
                "description": "High or critical risk actions need review unless explicitly blocked by a stricter rule.",
                "when": {"risk_level": ["high", "critical"]},
            },
        ],
    })


def policy_digest(policy: AgentFirewallPolicy | Mapping[str, Any]) -> str:
    import hashlib

    data = policy.to_dict() if isinstance(policy, AgentFirewallPolicy) else dict(policy or {})
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "AgentFirewallPolicy",
    "FirewallRule",
    "HARD_BLOCK",
    "PASS",
    "REVIEW",
    "VALID_FIREWALL_ACTIONS",
    "build_firewall_context",
    "default_firewall_policy",
    "load_firewall_policy",
    "policy_digest",
]
