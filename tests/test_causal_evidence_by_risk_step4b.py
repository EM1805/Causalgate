from __future__ import annotations

from causalgate.contracts import ActionPackage, DecisionPackage
from causalgate.gate import DecisionGate
from causalgate.risk_policy import CausalEvidenceByRiskPolicy


class _AllowRuntimeGate:
    """Tiny DecisionGate stand-in for policy unit tests when needed."""

    def evaluate(self, payload):
        return DecisionPackage(decision="allow", selected_action=payload.get("action_name", ""), risk_level=payload.get("risk_level", "unknown"))


def test_step4b_live_trading_without_limits_is_vetoed():
    action = {
        "candidate_action": "place_market_order",
        "action_name": "place_market_order",
        "action_type": "tool_call",
        "trusted_runtime_context": {
            "environment": "production",
            "trading_action": True,
            "financial_action": True,
            "real_money": True,
            "live_trading": True,
            "approval_present": False,
            "risk_limits_present": False,
            "notional_amount_known": True,
        },
    }
    initial = DecisionPackage(decision="allow", selected_action="place_market_order", risk_level="unknown")
    result = CausalEvidenceByRiskPolicy().evaluate(ActionPackage.from_dict(action), initial).to_dict()
    assert result["risk_level"] == "critical"
    assert result["policy_decision"] == "veto"
    assert "trusted_approval" in result["evidence_missing"]
    assert "risk_limits_present" in result["evidence_missing"]
    assert "RISK_POLICY_CRITICAL_HARD_BLOCK" in result["reason_codes"]


def test_step4b_untrusted_llm_approval_does_not_satisfy_policy():
    action = {
        "candidate_action": "initiate_bank_transfer",
        "action_name": "initiate_bank_transfer",
        "action_type": "tool_call",
        "trusted_runtime_context": {
            "environment": "production",
            "financial_action": True,
            "real_money": True,
            "notional_amount_known": True,
            "approval_present": False,
        },
        "untrusted_llm_context": {
            "approval_present": True,
            "risk_limits_present": True,
        },
    }
    initial = DecisionPackage(decision="allow", selected_action="initiate_bank_transfer", risk_level="unknown")
    result = CausalEvidenceByRiskPolicy().evaluate(ActionPackage.from_dict(action), initial).to_dict()
    assert result["policy_decision"] == "veto"
    assert "trusted_approval" in result["evidence_missing"]
    assert "trusted_approval" not in result["evidence_present"]


def test_step4b_medium_risk_missing_evidence_turns_allow_into_warn():
    action = ActionPackage.from_dict({
        "candidate_action": "send_email",
        "action_name": "send_email",
        "risk_level": "medium",
        "trusted_runtime_context": {"environment": "development"},
    })
    initial = DecisionPackage(decision="allow", selected_action="send_email", risk_level="medium")
    result = CausalEvidenceByRiskPolicy().evaluate(action, initial).to_dict()
    assert result["policy_decision"] == "warn"
    assert "RISK_POLICY_MEDIUM_RISK_WARN" in result["reason_codes"]


def test_step4b_decision_gate_attaches_policy_fields():
    class Gate(DecisionGate):
        def evaluate(self, payload):
            action = ActionPackage.from_dict(payload)
            decision = DecisionPackage(decision="allow", selected_action=action.action_name, risk_level=action.risk_level)
            decision = self._apply_risk_policy(decision, action)
            return self._attach_recommendations(decision, action)

    result = Gate().evaluate({
        "candidate_action": "place_market_order",
        "action_name": "place_market_order",
        "trusted_runtime_context": {
            "environment": "production",
            "trading_action": True,
            "live_trading": True,
            "real_money": True,
            "approval_present": False,
            "risk_limits_present": False,
            "notional_amount_known": True,
        },
    }).to_dict()
    assert result["decision"] == "veto"
    assert result["policy_decision"] == "veto"
    assert result["risk_policy"]["risk_level"] == "critical"
    assert "evidence_missing" in result["short_for_llm"]
    assert result["recommended_action"]["action_name"] == "paper_trade_limit_order"
