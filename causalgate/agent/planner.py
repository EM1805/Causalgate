from __future__ import annotations

import re
from pathlib import Path
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Protocol, Sequence

from causalgate.contracts import SENSITIVE_RUNTIME_KEYS
from causalgate.llm_interface import LLMResponse, MockLLMClient

from .modes import infer_agent_mode
from .registry_policy import AgentRegistryPolicy
from .types import clean_str


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _lower(value: Any) -> str:
    return _text(value).strip().lower()


def _matches_any(text: str, patterns: Sequence[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _first_match(text: str, patterns: Sequence[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return ""



def _resolve_existing_path(path: str) -> str:
    """Resolve registry paths for both project-root and installed-package runs."""
    candidate = Path(path)
    if candidate.exists():
        return str(candidate)
    if candidate.is_absolute():
        return str(candidate)
    here = Path(__file__).resolve()
    for parent in [Path.cwd(), *here.parents]:
        alt = parent / path
        if alt.exists():
            return str(alt)
    return path

def _listish(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, Mapping)):
        return [str(item) for item in value if str(item).strip()]
    return []


# Intent patterns are intentionally broad but conservative.  The planner is not
# an authority: it proposes structured candidates only; DecisionGate,
# RegistryPolicy and ToolGuard still decide whether anything can execute.
CODE_READ_PATTERNS = (r"\b(read|open|inspect|view)\b.*\b(file|code|repo|repository)\b", r"\bcontrolla\b.*\b(file|codice|repo)\b", r"\bleggi\b.*\b(file|codice)\b")
CODE_WRITE_PATTERNS = (r"\b(write|edit|patch|modify|update|fix)\b.*\b(file|code|repo|repository)\b", r"\b(sistema|migliora|aggiorna|modifica|riscrivi)\b.*\b(codice|file|pacchetto|planner)\b")
CODE_TEST_PATTERNS = (r"\b(run|execute)\b.*\b(test|tests|pytest)\b", r"\b(testa|lancia i test|esegui i test)\b")
SHELL_PATTERNS = (r"\b(run shell|shell command|terminal|bash|cmd|powershell)\b", r"\besegui\b.*\b(comando|shell|terminale)\b")
PACKAGE_PATTERNS = (r"\b(install|upgrade|remove)\b.*\b(package|dependency|pip|npm)\b", r"\b(installa|aggiorna)\b.*\b(pacchetto|dipendenza)\b")

OPS_DEPLOY_PATTERNS = (r"\bdeploy\b", r"\brilascia\b", r"\bmetti in produzione\b")
OPS_CONFIG_PATTERNS = (r"\b(config|configuration|env var|feature flag)\b", r"\bconfigurazione\b")
OPS_DB_PATTERNS = (r"\b(database|db|sql|table|schema|migration)\b", r"\btabella\b")
OPS_SECRET_PATTERNS = (r"\b(secret|token|credential|password|api key)\b", r"\bsegreto\b", r"\bcredenzial")

FINANCE_READ_PATTERNS = (r"\b(balance|account balance|portfolio|market data|price|quote)\b", r"\b(saldo|portafoglio|prezzo|quotazione|dati finanziari)\b")
FINANCE_TRANSFER_PATTERNS = (r"\b(transfer|withdraw|payout|bank transfer)\b", r"\b(trasferisci|preleva|bonifico|paga|pagamento)\b")
FINANCE_PAYMENT_PATTERNS = (r"\b(invoice|refund|charge customer|payment)\b", r"\b(fattura|rimborso|addebita|pagamento)\b")
TRADING_ORDER_PATTERNS = (r"\b(buy|sell|market order|limit order|order)\b", r"\b(compra|vendi|ordine|trading|trade)\b")
TRADING_CANCEL_PATTERNS = (r"\b(cancel|modify)\b.*\border\b", r"\b(cancella|modifica)\b.*\bordine\b")
TRADING_CLOSE_PATTERNS = (r"\bclose position\b", r"\bchiudi\b.*\bposizione\b")
TRADING_LEVERAGE_PATTERNS = (r"\b(leverage|margin)\b", r"\b(leva|margine)\b")
TRADING_STOP_PATTERNS = (r"\bstop loss\b", r"\bstop-loss\b")
PAPER_TRADE_PATTERNS = (r"\bpaper trade\b", r"\bpaper trading\b", r"\bsimul[ao]\b.*\b(trade|ordine)\b")

WEB_PATTERNS = (r"\b(search|browse|web|internet|latest|news)\b", r"\b(cerca|naviga|internet|notizie|aggiornato|ultimo)\b")
EMAIL_PATTERNS = (r"\b(send|email|mail)\b", r"\b(invia|manda)\b.*\b(email|mail)\b")
SHARE_PATTERNS = (r"\bshare\b.*\b(file|link)\b", r"\bcondivid")
MEMORY_WRITE_PATTERNS = (r"\bremember|save to memory|store this\b", r"\bricorda\b", r"\bsalva\b.*\bmemoria\b")
MEMORY_READ_PATTERNS = (r"\brecall|retrieve memory|what do you remember\b", r"\bcosa ricordi\b", r"\brecupera\b.*\bmemoria\b")
MEMORY_ERASE_PATTERNS = (r"\bforget|erase memory|delete memory\b", r"\bdimentica\b", r"\bcancella\b.*\bmemoria\b")
DELETE_PATTERNS = (r"\b(delete|remove|drop|truncate|overwrite)\b", r"\b(cancella|elimina|rimuovi|sovrascrivi)\b")
CLARIFY_PATTERNS = (r"\b(non funziona|non va|errore|bug|crash|aiutami|help)\b",)

ACTION_TYPE_DEFAULTS = {
    "answer_directly": "communication",
    "ask_clarification": "communication",
    "abstain": "communication",
    "explain_block": "communication",
    "browse_web": "external_read",
    "read_file": "read",
    "read_file_safe": "read",
    "write_file": "mutation",
    "write_draft_file": "mutation",
    "delete_file": "mutation",
    "run_shell_command": "code_execution",
    "run_tests_sandbox": "code_execution",
    "execute_code": "code_execution",
    "install_package": "dependency_change",
    "deploy_code": "ops",
    "deploy_config_change": "ops",
    "modify_database": "admin",
    "access_secret": "credential_access",
    "call_api": "external_read",
    "retrieve_memory": "memory_read",
    "write_memory": "memory_write",
    "erase_memory": "memory_mutation",
    "view_account_balance": "financial_read",
    "access_financial_data": "financial_read",
    "paper_trade_limit_order": "trade_execution",
    "paper_trade_order": "trade_execution",
    "place_market_order": "trade_execution",
    "place_limit_order": "trade_execution",
    "cancel_order": "trade_order_management",
    "modify_order": "trade_order_management",
    "close_position": "portfolio_mutation",
    "open_margin_position": "leveraged_trade_execution",
    "set_stop_loss": "risk_control",
    "initiate_bank_transfer": "financial_transfer",
    "withdraw_funds": "financial_transfer",
    "approve_invoice_payment": "payment_mutation",
    "charge_customer": "payment_mutation",
    "refund_payment": "payment_mutation",
    "issue_payout": "payment_mutation",
    "send_email_external": "communication",
    "send_email_internal": "communication",
    "share_file_external": "sharing",
    "delete_resource": "mutation",
    "change_permissions": "admin",
}

DOMAIN_DEFAULTS = {
    "read_file": "code",
    "read_file_safe": "code",
    "write_file": "code",
    "write_draft_file": "code",
    "delete_file": "code",
    "run_shell_command": "development",
    "run_tests_sandbox": "development",
    "execute_code": "development",
    "install_package": "development",
    "deploy_code": "ops",
    "deploy_config_change": "ops",
    "modify_database": "infrastructure",
    "access_secret": "infrastructure",
    "call_api": "agent_tools",
    "browse_web": "agent_tools",
    "retrieve_memory": "agent_memory",
    "write_memory": "agent_memory",
    "erase_memory": "agent_memory",
    "view_account_balance": "finance",
    "access_financial_data": "finance",
    "initiate_bank_transfer": "finance",
    "withdraw_funds": "finance",
    "approve_invoice_payment": "finance",
    "charge_customer": "finance",
    "refund_payment": "finance",
    "issue_payout": "finance",
    "place_market_order": "trading",
    "place_limit_order": "trading",
    "paper_trade_limit_order": "trading",
    "paper_trade_order": "trading",
    "cancel_order": "trading",
    "modify_order": "trading",
    "close_position": "trading",
    "open_margin_position": "trading",
    "set_stop_loss": "trading",
    "send_email_external": "general",
    "send_email_internal": "general",
    "share_file_external": "general",
    "delete_resource": "ops",
    "change_permissions": "agent_tools",
}

RISK_DEFAULTS = {
    "answer_directly": "low",
    "ask_clarification": "low",
    "abstain": "low",
    "browse_web": "low",
    "read_file": "low",
    "read_file_safe": "low",
    "retrieve_memory": "low",
    "view_account_balance": "low",
    "access_financial_data": "low",
    "set_stop_loss": "medium",
    "paper_trade_limit_order": "low",
    "paper_trade_order": "low",
    "write_memory": "medium",
    "send_email_internal": "low",
    "send_email_external": "medium",
    "share_file_external": "medium",
    "call_api": "medium",
    "write_file": "medium",
    "write_draft_file": "medium",
    "run_tests_sandbox": "medium",
    "change_permissions": "medium",
    "install_package": "high",
    "execute_code": "high",
    "run_shell_command": "high",
    "deploy_config_change": "high",
    "deploy_code": "high",
    "modify_database": "high",
    "access_secret": "critical",
    "delete_file": "critical",
    "delete_resource": "critical",
    "place_market_order": "high",
    "place_limit_order": "high",
    "cancel_order": "medium",
    "modify_order": "high",
    "close_position": "high",
    "open_margin_position": "critical",
    "initiate_bank_transfer": "critical",
    "withdraw_funds": "critical",
    "approve_invoice_payment": "high",
    "charge_customer": "high",
    "refund_payment": "high",
    "issue_payout": "critical",
    "erase_memory": "medium",
}

IRREVERSIBLE_ACTIONS = {
    "delete_file",
    "delete_resource",
    "send_email_external",
    "share_file_external",
    "initiate_bank_transfer",
    "withdraw_funds",
    "approve_invoice_payment",
    "charge_customer",
    "refund_payment",
    "issue_payout",
    "place_market_order",
    "place_limit_order",
    "open_margin_position",
}

TOOL_ACTIONS = {
    "browse_web",
    "read_file",
    "read_file_safe",
    "write_file",
    "write_draft_file",
    "delete_file",
    "run_shell_command",
    "run_tests_sandbox",
    "execute_code",
    "install_package",
    "deploy_code",
    "deploy_config_change",
    "modify_database",
    "access_secret",
    "call_api",
    "retrieve_memory",
    "write_memory",
    "erase_memory",
    "view_account_balance",
    "access_financial_data",
    "paper_trade_limit_order",
    "paper_trade_order",
    "place_market_order",
    "place_limit_order",
    "cancel_order",
    "modify_order",
    "close_position",
    "open_margin_position",
    "set_stop_loss",
    "initiate_bank_transfer",
    "withdraw_funds",
    "approve_invoice_payment",
    "charge_customer",
    "refund_payment",
    "issue_payout",
    "send_email_external",
    "send_email_internal",
    "share_file_external",
    "delete_resource",
    "change_permissions",
}


@dataclass(frozen=True)
class PlannerConfig:
    """Configuration for CausalGate's deterministic agent planner."""

    action_registry_path: str = "action_registry.yaml"
    default_agent_mode: str = "general_agent"
    enrich_from_registry: bool = True
    expose_trusted_context_to_planner: bool = True
    max_candidates: int = 8
    include_safe_fallbacks: bool = True


@dataclass
class PlannerCandidate:
    action_name: str
    rationale: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    action_type: str = ""
    domain: str = ""
    risk_level: str = ""
    target_resource: str = ""
    requires_tool: bool | None = None
    requires_user_confirmation: bool | None = None
    priority: int = 50
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_action_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "action_name": self.action_name,
            "candidate_action": self.action_name,
            "params": dict(self.params or {}),
            "planner": {
                "rationale": self.rationale,
                "priority": self.priority,
                **dict(self.metadata or {}),
            },
        }
        for key in ("action_type", "domain", "risk_level", "target_resource"):
            value = getattr(self, key)
            if value:
                out[key] = value
        if self.requires_tool is not None:
            out["requires_tool"] = bool(self.requires_tool)
        if self.requires_user_confirmation is not None:
            out["requires_user_confirmation"] = bool(self.requires_user_confirmation)
        return out


class ActionPlanner(Protocol):
    """Planner interface used by CausalGateAgent.

    A planner proposes candidate actions only. It must never execute tools and
    must never be treated as an authority for runtime approval.
    """

    def propose_actions(
        self,
        user_message: str,
        *,
        trusted_runtime_context: Mapping[str, Any] | None = None,
        untrusted_llm_context: Mapping[str, Any] | None = None,
        planner_context: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        ...


class HierarchicalActionPlanner:
    """Deterministic, registry-aware planner for CausalGate agents.

    The planner performs four lightweight stages:
    1. Build a non-authoritative planning context.
    2. Infer domain/mode/risk from the user's goal.
    3. Propose a ranked set of candidate actions plus safe fallbacks.
    4. Enrich candidates from action_registry.yaml without authorizing them.

    It deliberately never calls tools and never grants approval. All sensitive
    runtime facts remain authoritative only when passed separately as
    trusted_runtime_context to DecisionGate/RegistryPolicy/ToolGuard.
    """

    def __init__(self, config: PlannerConfig | None = None, **kwargs: Any) -> None:
        if config is None:
            config = PlannerConfig(**kwargs) if kwargs else PlannerConfig()
        self.config = config
        self._registry_policy: AgentRegistryPolicy | None = None
        if self.config.enrich_from_registry:
            self._registry_policy = AgentRegistryPolicy(
                action_registry_path=_resolve_existing_path(self.config.action_registry_path),
                default_agent_mode=self.config.default_agent_mode,
            )

    def build_planner_context(
        self,
        *,
        trusted_runtime_context: Mapping[str, Any] | None = None,
        untrusted_llm_context: Mapping[str, Any] | None = None,
        planner_context: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        trusted = _as_dict(trusted_runtime_context)
        untrusted = _as_dict(untrusted_llm_context)
        planner = _as_dict(planner_context)

        context: Dict[str, Any] = {}
        if self.config.expose_trusted_context_to_planner:
            context.update(trusted)
        else:
            context.update({k: v for k, v in trusted.items() if k not in SENSITIVE_RUNTIME_KEYS})
        context.update(planner)

        # Untrusted hints can fill missing fields, but cannot overwrite runtime
        # facts or explicit planner context.
        for key, value in untrusted.items():
            context.setdefault(key, value)
        return context

    def _candidate(self, action_name: str, rationale: str, *, priority: int = 50, params: Mapping[str, Any] | None = None, **metadata: Any) -> PlannerCandidate:
        return PlannerCandidate(
            action_name=action_name,
            rationale=rationale,
            params=dict(params or {}),
            priority=priority,
            metadata={k: v for k, v in metadata.items() if v not in {None, ""}},
        )

    def _extract_params(self, message: str, context: Mapping[str, Any]) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        for key in (
            "path",
            "content",
            "query",
            "command",
            "url",
            "symbol",
            "instrument_symbol",
            "quantity",
            "notional_amount",
            "currency",
            "order_type",
            "trade_side",
            "recipient",
        ):
            if key in context:
                params[key] = context[key]
        if "query" not in params:
            params["query"] = message.strip()

        # Safe path extraction for common file prompts.  This is a hint only;
        # ToolRegistry schema validation still checks required args.
        path_match = re.search(r"(?:file|path|percorso)\s*[:=]?\s*([\w./\\-]+)", message, flags=re.I)
        if path_match and "path" not in params:
            params["path"] = path_match.group(1)

        symbol_match = re.search(r"\b([A-Z]{1,6})(?:/USD|USD)?\b", message)
        if symbol_match and _matches_any(message, TRADING_ORDER_PATTERNS + FINANCE_READ_PATTERNS) and "instrument_symbol" not in params:
            params["instrument_symbol"] = symbol_match.group(1)
        return params

    def _explicit_action_candidates(self, context: Mapping[str, Any]) -> List[PlannerCandidate]:
        candidates: List[PlannerCandidate] = []
        explicit = (
            context.get("action_name")
            or context.get("candidate_action")
            or context.get("requested_action")
            or context.get("tool_name")
        )
        if explicit:
            candidates.append(self._candidate(str(explicit), "explicit action requested by caller", priority=100))
        for item in _listish(context.get("candidate_actions")):
            candidates.append(self._candidate(item, "candidate action supplied by caller", priority=95))
        return candidates

    def _infer_candidates(self, message: str, context: Mapping[str, Any]) -> List[PlannerCandidate]:
        text = message.strip()
        params = self._extract_params(text, context)
        out: List[PlannerCandidate] = []
        requested_mode = context.get("agent_mode")
        mode_hint = _lower(requested_mode)

        out.extend(self._explicit_action_candidates(context))

        # Code and repository work.
        if _matches_any(text, CODE_READ_PATTERNS):
            out.append(self._candidate("read_file_safe", "inspect code/file inside sandbox before changing it", priority=88, params=params))
            out.append(self._candidate("read_file", "legacy read action alias for sandbox file inspection", priority=86, params=params))
        if _matches_any(text, CODE_WRITE_PATTERNS):
            out.append(self._candidate("write_draft_file", "write a safe draft patch without mutating source files", priority=86, params=params))
            out.append(self._candidate("write_file", "legacy write action alias; sandbox executor writes only drafts", priority=84, params=params))
            out.append(self._candidate("read_file_safe", "read current file before patching", priority=73, params=params))
            out.append(self._candidate("read_file", "legacy read action alias before patching", priority=72, params=params))
        if _matches_any(text, CODE_TEST_PATTERNS):
            out.append(self._candidate("run_tests_sandbox", "run the project's tests through the pytest-only sandbox", priority=84, params=params, sandbox_required=True))
            out.append(self._candidate("run_shell_command", "legacy shell action alias restricted to pytest by sandbox executor", priority=82, params=params, sandbox_required=True))
        if _matches_any(text, SHELL_PATTERNS):
            out.append(self._candidate("run_shell_command", "execute a shell command only if sandboxed and approved", priority=80, params=params, sandbox_required=True))
        if _matches_any(text, PACKAGE_PATTERNS):
            out.append(self._candidate("install_package", "change project dependencies", priority=78, params=params))

        # Ops and infrastructure.
        if _matches_any(text, OPS_DEPLOY_PATTERNS):
            out.append(self._candidate("deploy_code", "deploy application/code change", priority=84, params=params))
        if _matches_any(text, OPS_CONFIG_PATTERNS) and _matches_any(text, OPS_DEPLOY_PATTERNS):
            out.append(self._candidate("deploy_config_change", "deploy configuration change", priority=83, params=params))
        if _matches_any(text, OPS_DB_PATTERNS):
            out.append(self._candidate("modify_database", "database/schema/data mutation", priority=80, params=params))
        if _matches_any(text, OPS_SECRET_PATTERNS):
            out.append(self._candidate("access_secret", "access credentials/secrets", priority=76, params=params))

        # Finance and trading.
        if _matches_any(text, FINANCE_READ_PATTERNS):
            action = "view_account_balance" if _matches_any(text, (r"\bbalance\b", r"\bsaldo\b")) else "access_financial_data"
            out.append(self._candidate(action, "read financial/account/market information", priority=84, params=params))
        if _matches_any(text, FINANCE_TRANSFER_PATTERNS):
            action = "withdraw_funds" if _matches_any(text, (r"\bwithdraw\b", r"\bpreleva\b")) else "initiate_bank_transfer"
            out.append(self._candidate(action, "move real money", priority=80, params=params))
        if _matches_any(text, FINANCE_PAYMENT_PATTERNS):
            if _matches_any(text, (r"\brefund\b", r"\brimborso\b")):
                action = "refund_payment"
            elif _matches_any(text, (r"\bcharge\b", r"\baddebita\b")):
                action = "charge_customer"
            else:
                action = "approve_invoice_payment"
            out.append(self._candidate(action, "payment mutation", priority=78, params=params))
        if _matches_any(text, PAPER_TRADE_PATTERNS):
            out.append(self._candidate("paper_trade_order", "record simulated paper trade without live-money execution", priority=92, params=params))
            out.append(self._candidate("paper_trade_limit_order", "legacy paper-trading limit-order alias", priority=90, params=params))
        elif _matches_any(text, TRADING_ORDER_PATTERNS):
            action = "place_limit_order" if _matches_any(text, (r"\blimit order\b", r"\bordine limite\b")) else "place_market_order"
            out.append(self._candidate(action, "place live trading order", priority=82, params=params))
            out.append(self._candidate("paper_trade_order", "safer paper-trading alternative", priority=71, params=params, safer_alternative_for=action))
            out.append(self._candidate("paper_trade_limit_order", "legacy safer paper-trading alternative", priority=70, params=params, safer_alternative_for=action))
        if _matches_any(text, TRADING_CANCEL_PATTERNS):
            out.append(self._candidate("cancel_order", "cancel a trading order", priority=80, params=params))
        if _matches_any(text, TRADING_CLOSE_PATTERNS):
            out.append(self._candidate("close_position", "close trading position", priority=80, params=params))
        if _matches_any(text, TRADING_LEVERAGE_PATTERNS):
            out.append(self._candidate("open_margin_position", "open leveraged/margin exposure", priority=78, params=params))
        if _matches_any(text, TRADING_STOP_PATTERNS):
            out.append(self._candidate("set_stop_loss", "risk-control order", priority=82, params=params))

        # General tools and communications.
        if _matches_any(text, WEB_PATTERNS):
            out.append(self._candidate("browse_web", "retrieve current external information", priority=78, params=params))
        if _matches_any(text, EMAIL_PATTERNS):
            external = _matches_any(text, (r"\bexternal\b", r"\besterno\b", r"\bclient\b", r"\bcustomer\b")) or context.get("recipient_external") is True
            out.append(self._candidate("send_email_external" if external else "send_email_internal", "send email/communication", priority=76, params=params))
        if _matches_any(text, SHARE_PATTERNS):
            out.append(self._candidate("share_file_external", "share a file/link outside the trusted boundary", priority=74, params=params))
        if _matches_any(text, MEMORY_ERASE_PATTERNS):
            out.append(self._candidate("erase_memory", "remove stored memory", priority=75, params=params))
        elif _matches_any(text, MEMORY_WRITE_PATTERNS):
            out.append(self._candidate("write_memory", "store memory for future use", priority=75, params=params))
        elif _matches_any(text, MEMORY_READ_PATTERNS):
            out.append(self._candidate("retrieve_memory", "retrieve stored memory", priority=75, params=params))
        if _matches_any(text, DELETE_PATTERNS):
            if _matches_any(text, (r"\bfile\b", r"\bpath\b", r"\bfile\b")) or mode_hint == "code_agent":
                out.append(self._candidate("delete_file", "delete/overwrite file", priority=73, params=params))
            else:
                out.append(self._candidate("delete_resource", "delete/destructive resource mutation", priority=73, params=params))

        # Ambiguous or incomplete prompts should get clarification before direct execution.
        word_count = len([w for w in re.split(r"\s+", text) if w])
        if word_count <= 5 or _matches_any(text, CLARIFY_PATTERNS):
            out.append(self._candidate("ask_clarification", "request missing goal, target, or safety context", priority=68, params={}))

        if self.config.include_safe_fallbacks:
            if not out:
                out.append(self._candidate("ask_clarification", "no clear executable intent detected", priority=65, params={}))
            out.append(self._candidate("answer_directly", "safe conversational response", priority=20, params={}))
        return out

    def _needs_confirmation(self, action_name: str, risk_level: str, context: Mapping[str, Any]) -> bool:
        if risk_level in {"medium", "high", "critical"}:
            return True
        if _lower(context.get("environment")) in {"prod", "production"} and action_name not in {"answer_directly", "ask_clarification", "read_file", "read_file_safe", "browse_web"}:
            return True
        if action_name in IRREVERSIBLE_ACTIONS:
            return True
        return False

    def _missing_inputs(self, action_name: str, candidate: Mapping[str, Any], context: Mapping[str, Any]) -> List[str]:
        params = _as_dict(candidate.get("params"))
        missing: List[str] = []
        if action_name in {"write_file", "write_draft_file", "delete_file", "read_file", "read_file_safe"} and not params.get("path"):
            missing.append("path")
        if action_name in {"write_file", "write_draft_file"} and not params.get("content"):
            missing.append("content")
        if action_name in {"run_shell_command", "run_tests_sandbox"} and not params.get("command"):
            missing.append("command")
        if action_name in {"place_market_order", "place_limit_order", "paper_trade_limit_order", "paper_trade_order"}:
            for key in ("instrument_symbol", "trade_side", "quantity"):
                if not (params.get(key) or context.get(key)):
                    missing.append(key)
        if action_name in {"initiate_bank_transfer", "withdraw_funds", "issue_payout", "approve_invoice_payment", "charge_customer", "refund_payment"}:
            for key in ("notional_amount", "currency"):
                if not (params.get(key) or context.get(key)):
                    missing.append(key)
        if _lower(context.get("environment")) in {"prod", "production"} and context.get("approval_present") is not True and action_name not in {"answer_directly", "ask_clarification"}:
            missing.append("trusted_approval")
        if action_name in {"place_market_order", "place_limit_order", "open_margin_position", "initiate_bank_transfer", "withdraw_funds"}:
            if context.get("risk_limits_present") is not True:
                missing.append("risk_limits_present")
            if action_name not in {"paper_trade_limit_order", "paper_trade_order"} and context.get("real_money") is not False and context.get("live_trading") is not False:
                missing.append("live_money_review")
        return sorted(set(missing))

    def _normalize_and_enrich(
        self,
        raw_candidates: Sequence[PlannerCandidate],
        *,
        user_message: str,
        context: Mapping[str, Any],
        trusted_runtime_context: Mapping[str, Any] | None,
    ) -> List[Dict[str, Any]]:
        dedup: Dict[str, PlannerCandidate] = {}
        for item in raw_candidates:
            name = clean_str(item.action_name)
            if not name:
                continue
            existing = dedup.get(name)
            if existing is None or item.priority > existing.priority:
                dedup[name] = item

        ranked = sorted(dedup.values(), key=lambda c: c.priority, reverse=True)[: self.config.max_candidates]
        enriched: List[Dict[str, Any]] = []
        for index, item in enumerate(ranked, start=1):
            candidate = item.to_action_dict()
            name = clean_str(candidate.get("action_name"))
            candidate.setdefault("action_type", ACTION_TYPE_DEFAULTS.get(name, "unknown"))
            candidate.setdefault("domain", DOMAIN_DEFAULTS.get(name, "general"))
            candidate.setdefault("risk_level", RISK_DEFAULTS.get(name, "unknown"))
            candidate.setdefault("target_resource", "conversation" if candidate["action_type"] == "communication" else candidate.get("domain", "resource"))
            candidate.setdefault("requires_tool", name in TOOL_ACTIONS)
            candidate.setdefault("reversibility", "irreversible" if name in IRREVERSIBLE_ACTIONS else "reversible")
            candidate.setdefault("requires_user_confirmation", self._needs_confirmation(name, _lower(candidate.get("risk_level")), context))
            candidate.setdefault("user_message", user_message)

            if self._registry_policy is not None:
                candidate = self._registry_policy.enrich_candidate(
                    candidate,
                    trusted_runtime_context=trusted_runtime_context,
                )

            mode = candidate.get("agent_mode") or infer_agent_mode(
                candidate=candidate,
                trusted_runtime_context=trusted_runtime_context or context,
                default=self.config.default_agent_mode,
            )
            candidate["agent_mode"] = mode
            missing_inputs = self._missing_inputs(name, candidate, context)
            planner_meta = _as_dict(candidate.get("planner"))
            planner_meta.update(
                {
                    "stage": "hierarchical_action_planner",
                    "rank": index,
                    "missing_inputs": missing_inputs,
                    "execution_rule": "proposal_only_must_pass_decision_gate_registry_policy_and_tool_guard",
                }
            )
            candidate["planner"] = planner_meta
            if missing_inputs:
                candidate["missing_inputs"] = missing_inputs
            enriched.append(candidate)
        return enriched

    def propose_actions(
        self,
        user_message: str,
        *,
        trusted_runtime_context: Mapping[str, Any] | None = None,
        untrusted_llm_context: Mapping[str, Any] | None = None,
        planner_context: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        context = self.build_planner_context(
            trusted_runtime_context=trusted_runtime_context,
            untrusted_llm_context=untrusted_llm_context,
            planner_context=planner_context,
        )
        raw_candidates = self._infer_candidates(user_message, context)
        candidate_actions = self._normalize_and_enrich(
            raw_candidates,
            user_message=user_message,
            context=context,
            trusted_runtime_context=trusted_runtime_context,
        )
        return LLMResponse(
            user_message=user_message,
            candidate_actions=candidate_actions,
            context=dict(context),
            raw_model_output={
                "planner": "HierarchicalActionPlanner",
                "config": asdict(self.config),
                "candidate_count": len(candidate_actions),
            },
            source="hierarchical_action_planner",
        )


class LLMActionPlanner:
    """Adapter around an LLMClient plus deterministic post-processing.

    If an external LLM is supplied, its candidate actions are accepted but then
    normalized/enriched by HierarchicalActionPlanner.  If the external LLM
    returns no useful candidates, the deterministic planner provides a safe
    fallback plan.
    """

    def __init__(
        self,
        llm_client: Any | None = None,
        *,
        expose_trusted_context_to_planner: bool = True,
        action_registry_path: str = "action_registry.yaml",
        default_agent_mode: str = "general_agent",
        deterministic_fallback: bool = True,
    ) -> None:
        self.llm_client = llm_client or MockLLMClient()
        self.expose_trusted_context_to_planner = expose_trusted_context_to_planner
        self.deterministic_fallback = deterministic_fallback
        self.structured_planner = HierarchicalActionPlanner(
            PlannerConfig(
                action_registry_path=_resolve_existing_path(action_registry_path),
                default_agent_mode=default_agent_mode,
                expose_trusted_context_to_planner=expose_trusted_context_to_planner,
            )
        )

    def build_planner_context(
        self,
        *,
        trusted_runtime_context: Mapping[str, Any] | None = None,
        untrusted_llm_context: Mapping[str, Any] | None = None,
        planner_context: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        return self.structured_planner.build_planner_context(
            trusted_runtime_context=trusted_runtime_context,
            untrusted_llm_context=untrusted_llm_context,
            planner_context=planner_context,
        )

    def _coerce_llm_response(self, response: Any, user_message: str, context: Mapping[str, Any]) -> LLMResponse:
        if isinstance(response, LLMResponse):
            return response
        data = dict(response or {}) if isinstance(response, Mapping) else {}
        return LLMResponse(
            user_message=str(data.get("user_message", user_message) or ""),
            candidate_actions=list(data.get("candidate_actions", []) or []),
            context=dict(data.get("context", context) or {}),
            raw_model_output=dict(data.get("raw_model_output", data.get("raw", {})) or {}),
            source=str(data.get("source", getattr(self.llm_client, "name", "llm_action_planner")) or "llm_action_planner"),
        )

    def propose_actions(
        self,
        user_message: str,
        *,
        trusted_runtime_context: Mapping[str, Any] | None = None,
        untrusted_llm_context: Mapping[str, Any] | None = None,
        planner_context: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        context = self.build_planner_context(
            trusted_runtime_context=trusted_runtime_context,
            untrusted_llm_context=untrusted_llm_context,
            planner_context=planner_context,
        )
        llm_response = self._coerce_llm_response(
            self.llm_client.propose_actions(user_message, context=context),
            user_message,
            context,
        )

        llm_candidates = list(llm_response.candidate_actions or [])
        if not llm_candidates and self.deterministic_fallback:
            return self.structured_planner.propose_actions(
                user_message,
                trusted_runtime_context=trusted_runtime_context,
                untrusted_llm_context=untrusted_llm_context,
                planner_context=planner_context,
            )

        # Normalize/enrich LLM candidates by treating them as planner context,
        # then preserve them before deterministic fallbacks when possible.
        raw_planner_candidates: List[PlannerCandidate] = []
        for index, item in enumerate(llm_candidates):
            if isinstance(item, Mapping):
                name = clean_str(item.get("action_name") or item.get("candidate_action") or item.get("selected_action") or item.get("name"))
                if not name:
                    continue
                raw_planner_candidates.append(
                    PlannerCandidate(
                        action_name=name,
                        rationale=clean_str(_as_dict(item.get("planner")).get("rationale") or item.get("rationale"), "candidate supplied by LLM client"),
                        params=_as_dict(item.get("params")),
                        action_type=clean_str(item.get("action_type")),
                        domain=clean_str(item.get("domain")),
                        risk_level=clean_str(item.get("risk_level")),
                        target_resource=clean_str(item.get("target_resource")),
                        requires_tool=item.get("requires_tool") if isinstance(item.get("requires_tool"), bool) else None,
                        requires_user_confirmation=item.get("requires_user_confirmation") if isinstance(item.get("requires_user_confirmation"), bool) else None,
                        priority=100 - index,
                        metadata={"llm_source": llm_response.source},
                    )
                )
            elif isinstance(item, str):
                raw_planner_candidates.append(PlannerCandidate(action_name=item, rationale="candidate supplied by LLM client", priority=100 - index))

        if self.deterministic_fallback:
            raw_planner_candidates.extend(self.structured_planner._infer_candidates(user_message, context))

        candidate_actions = self.structured_planner._normalize_and_enrich(
            raw_planner_candidates,
            user_message=user_message,
            context=context,
            trusted_runtime_context=trusted_runtime_context,
        )
        raw_model_output = dict(llm_response.raw_model_output or {})
        raw_model_output.update(
            {
                "planner": "LLMActionPlanner+HierarchicalActionPlanner",
                "llm_source": llm_response.source,
                "candidate_count": len(candidate_actions),
            }
        )
        return LLMResponse(
            user_message=llm_response.user_message or user_message,
            candidate_actions=candidate_actions,
            context=dict(llm_response.context or context),
            raw_model_output=raw_model_output,
            source="llm_action_planner_structured",
        )


__all__ = [
    "ActionPlanner",
    "HierarchicalActionPlanner",
    "LLMActionPlanner",
    "PlannerCandidate",
    "PlannerConfig",
]
