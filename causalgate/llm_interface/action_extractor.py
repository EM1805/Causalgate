from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Sequence


AMBIGUITY_PATTERNS: Sequence[str] = (
    r"\bnon funziona\b",
    r"\bnon va\b",
    r"\berrore\b",
    r"\bbug\b",
    r"\bcrash\b",
    r"\bsistemalo\b",
    r"\bfix(?:alo| it)?\b",
    r"\baiutami\b",
    r"\bhelp\b",
)

TOOL_PATTERNS: Sequence[str] = (
    r"\busa\b.*\btool\b",
    r"\btool\b",
    r"\bapi\b",
    r"\besegui\b",
    r"\brun\b",
    r"\btesta\b",
    r"\bcontrolla\b",
    r"\bdebug\b",
)

SEARCH_PATTERNS: Sequence[str] = (
    r"\bcerca\b",
    r"\bsearch\b",
    r"\bweb\b",
    r"\binternet\b",
    r"\blatest\b",
    r"\bultimo\b",
    r"\baggiornato\b",
    r"\bprezzo\b",
    r"\bnotizie\b",
)

DELETE_PATTERNS: Sequence[str] = (
    r"\bcancella\b",
    r"\belimina\b",
    r"\bdelete\b",
    r"\bremove\b",
    r"\bdrop\b",
    r"\btruncate\b",
    r"\boverwrite\b",
)

SEND_EXTERNAL_PATTERNS: Sequence[str] = (
    r"\binvia\b.*\b(email|mail)\b",
    r"\bsend\b.*\b(email|mail)\b",
    r"\bexternal\b",
    r"\besterno\b",
    r"\bfuori\b",
)

PERMISSION_PATTERNS: Sequence[str] = (
    r"\bpermess",
    r"\bpermission",
    r"\baccess\b",
    r"\badmin\b",
    r"\bshare\b",
    r"\bcondivid",
)

PRODUCTION_PATTERNS: Sequence[str] = (
    r"\bproduction\b",
    r"\bprod\b",
    r"\bproduzione\b",
)

SENSITIVE_PATTERNS: Sequence[str] = (
    r"\bsegreto\b",
    r"\bsecret\b",
    r"\bcredential\b",
    r"\btoken\b",
    r"\bpassword\b",
    r"\bdati sensibili\b",
    r"\bsensitive\b",
    r"\bcustomer\b",
    r"\butente\b",
)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _matches_any(text: str, patterns: Sequence[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _clean_context(context: Mapping[str, Any] | None) -> Dict[str, Any]:
    return dict(context or {}) if isinstance(context, Mapping) else {}


def _infer_environment(message: str, context: Mapping[str, Any]) -> str:
    explicit = str(context.get("environment", "") or "").strip().lower()
    if explicit:
        return explicit
    if _matches_any(message, PRODUCTION_PATTERNS):
        return "production"
    return "development"


def _infer_ambiguity(message: str, context: Mapping[str, Any]) -> str:
    explicit = str(context.get("ambiguity", "") or "").strip().lower()
    if explicit:
        return explicit
    words = [w for w in re.split(r"\s+", message.strip()) if w]
    if len(words) <= 5:
        return "high"
    if _matches_any(message, AMBIGUITY_PATTERNS) and not re.search(r"(traceback|stack|line \d+|expected|actual|file)", message, flags=re.I):
        return "high"
    return "medium" if "?" in message else "low"


def _infer_risk(message: str, context: Mapping[str, Any]) -> str:
    explicit = str(context.get("risk_level", "") or "").strip().lower()
    if explicit:
        return explicit
    if _matches_any(message, DELETE_PATTERNS) or _matches_any(message, SENSITIVE_PATTERNS):
        return "high"
    if _matches_any(message, SEND_EXTERNAL_PATTERNS) or _matches_any(message, PERMISSION_PATTERNS):
        return "medium"
    return "low"


def _candidate(
    action_name: str,
    *,
    action_type: str = "communication",
    target_resource: str = "conversation",
    risk_level: str = "low",
    reversibility: str = "reversible",
    requires_tool: bool = False,
    requires_user_confirmation: bool = False,
    context: Mapping[str, Any] | None = None,
    params: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "action_name": action_name,
        "candidate_action": action_name,
        "action_type": action_type,
        "target_resource": target_resource,
        "risk_level": risk_level,
        "reversibility": reversibility,
        "requires_tool": requires_tool,
        "requires_user_confirmation": requires_user_confirmation,
        "context": dict(context or {}),
        "params": dict(params or {}),
    }


def extract_candidate_actions(user_message: str, context: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """Heuristic action extraction for the mock LLM layer.

    The extractor is deliberately conservative and deterministic. It is not the
    final policy engine; it only prepares candidate actions for OperationalBrain.
    """

    message = _text(user_message)
    base_context = _clean_context(context)
    environment = _infer_environment(message, base_context)
    ambiguity = _infer_ambiguity(message, base_context)
    risk_level = _infer_risk(message, base_context)

    normalized_context: Dict[str, Any] = dict(base_context)
    normalized_context.setdefault("environment", environment)
    normalized_context.setdefault("ambiguity", ambiguity)
    normalized_context.setdefault("risk_level", risk_level)

    if environment == "production":
        normalized_context.setdefault("approval_present", False)
    if risk_level in {"high", "critical"}:
        normalized_context.setdefault("resource_sensitivity", "high")

    actions: List[Dict[str, Any]] = []

    if _matches_any(message, DELETE_PATTERNS):
        destructive_context = dict(normalized_context)
        destructive_context.setdefault("rollback_available", False)
        actions.append(_candidate(
            "delete_resource",
            action_type="mutation",
            target_resource="resource",
            risk_level="high",
            reversibility="irreversible",
            requires_user_confirmation=True,
            context=destructive_context,
            params={"resource_sensitivity": destructive_context.get("resource_sensitivity", "high")},
        ))

    if _matches_any(message, SEND_EXTERNAL_PATTERNS):
        external_context = dict(normalized_context)
        external_context.setdefault("recipient_external", True)
        if _matches_any(message, SENSITIVE_PATTERNS):
            external_context.setdefault("sensitive_resource", True)
        actions.append(_candidate(
            "send_email_external",
            action_type="communication",
            target_resource="external_recipient",
            risk_level="medium" if risk_level != "high" else "high",
            reversibility="irreversible",
            requires_user_confirmation=True,
            context=external_context,
        ))

    if _matches_any(message, PERMISSION_PATTERNS):
        permission_context = dict(normalized_context)
        permission_context.setdefault("approval_present", False if environment == "production" else True)
        actions.append(_candidate(
            "change_permissions",
            action_type="admin",
            target_resource="access_control",
            risk_level="medium" if risk_level == "low" else risk_level,
            reversibility="reversible",
            requires_user_confirmation=True,
            context=permission_context,
        ))

    if _matches_any(message, SEARCH_PATTERNS):
        actions.append(_candidate(
            "search_information",
            action_type="tool_call",
            target_resource="web_or_knowledge_source",
            risk_level="low",
            reversibility="reversible",
            requires_tool=True,
            context=dict(normalized_context),
        ))

    if _matches_any(message, TOOL_PATTERNS):
        actions.append(_candidate(
            "use_tool",
            action_type="tool_call",
            target_resource="tool",
            risk_level="medium" if risk_level == "low" else risk_level,
            reversibility="reversible",
            requires_tool=True,
            context=dict(normalized_context),
        ))

    # Conservative fallback: when ambiguity or risk is non-trivial, clarification
    # should be available as a candidate before direct answering.
    if ambiguity in {"high", "very_high", "critical", "unknown"} or risk_level in {"medium", "high", "critical"}:
        actions.append(_candidate(
            "ask_clarification",
            action_type="communication",
            target_resource="conversation",
            risk_level="low",
            reversibility="reversible",
            context=dict(normalized_context),
        ))

    actions.append(_candidate(
        "answer_directly",
        action_type="communication",
        target_resource="conversation",
        risk_level="low" if risk_level == "low" else "medium",
        reversibility="reversible",
        context=dict(normalized_context),
    ))

    # Deterministic de-duplication by action_name while keeping first occurrence.
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for action in actions:
        name = str(action.get("action_name", "")).strip()
        if name and name not in seen:
            deduped.append(action)
            seen.add(name)

    return {
        "user_message": message,
        "candidate_actions": deduped,
        "context": normalized_context,
    }


__all__ = ["extract_candidate_actions"]
