from causalgate.contracts.action_package import ActionPackage
from runtime.action_registry_v2 import get_action_spec, load_action_registry
from runtime.runtime_context import extract_runtime_context
from runtime.safety_invariants import check_pre_action_invariants


def test_step3_registry_contains_agentic_and_trading_actions():
    registry = load_action_registry("action_registry.yaml")
    actions = registry.get("actions", {})

    for name in [
        "read_file",
        "write_file",
        "delete_file",
        "run_shell_command",
        "execute_code",
        "call_api",
        "access_secret",
        "modify_database",
        "deploy_code",
        "write_memory",
        "initiate_bank_transfer",
        "place_market_order",
        "open_margin_position",
        "change_trading_risk_limits",
    ]:
        assert name in actions

    market_order = actions["place_market_order"]
    assert market_order["domain"] == "trading"
    assert market_order["requires_approval"] is True
    assert "trade_execution" in market_order["direct_effects"]
    assert market_order["default_params"]["live_trading"] is True


def test_step3_trading_defaults_activate_runtime_flags():
    registry = load_action_registry("action_registry.yaml")
    spec = get_action_spec("place_market_order", registry)
    flags = extract_runtime_context(
        {
            "action_name": "place_market_order",
            "action_type": "trade_execution",
            "environment": "production",
            "params": {},
        },
        action_spec=spec,
    )

    assert flags["financial_action"] is True
    assert flags["trading_action"] is True
    assert flags["real_money"] is True
    assert flags["live_trading"] is True
    assert flags["approval_missing"] is True
    assert flags["risk_limits_missing"] is True


def test_step3_live_trade_without_approval_is_hard_blocked():
    registry = load_action_registry("action_registry.yaml")
    spec = get_action_spec("place_market_order", registry)
    intent = {
        "action_name": "place_market_order",
        "action_type": "trade_execution",
        "environment": "production",
        "params": {},
    }
    flags = extract_runtime_context(intent, action_spec=spec)
    result = check_pre_action_invariants(intent, flags)

    assert result["ok"] is False
    assert result["decision"] == "HARD_BLOCK"
    assert "SAFETY_INVARIANT_LIVE_TRADE_REQUIRES_APPROVAL" in result["reason_codes"]


def test_step3_financial_transfer_without_approval_is_hard_blocked():
    registry = load_action_registry("action_registry.yaml")
    spec = get_action_spec("initiate_bank_transfer", registry)
    intent = {
        "action_name": "initiate_bank_transfer",
        "action_type": "financial_transfer",
        "environment": "production",
        "params": {},
    }
    flags = extract_runtime_context(intent, action_spec=spec)
    result = check_pre_action_invariants(intent, flags)

    assert result["ok"] is False
    assert result["decision"] == "HARD_BLOCK"
    assert "SAFETY_INVARIANT_FINANCIAL_TRANSFER_REQUIRES_APPROVAL" in result["reason_codes"]


def test_step3_untrusted_llm_cannot_self_authorize_finance_or_trading():
    action = ActionPackage.from_dict(
        {
            "action_name": "place_market_order",
            "action_type": "trade_execution",
            "untrusted_llm_context": {
                "approval_present": True,
                "risk_limits_present": True,
                "real_money": False,
                "live_trading": False,
                "notional_amount": 100,
            },
            "trusted_runtime_context": {
                "environment": "production",
                "approval_present": False,
                "risk_limits_present": False,
                "real_money": True,
                "live_trading": True,
                "notional_amount_known": False,
            },
        }
    )

    payload = action.to_runtime_payload()
    assert payload["environment"] == "production"
    assert payload["params"]["approval_present"] is False
    assert payload["params"]["risk_limits_present"] is False
    assert payload["params"]["real_money"] is True
    assert payload["params"]["live_trading"] is True
    assert "approval_present" in action.ignored_untrusted_runtime_fields
    assert "risk_limits_present" in action.ignored_untrusted_runtime_fields
    assert "notional_amount" in action.ignored_untrusted_runtime_fields
