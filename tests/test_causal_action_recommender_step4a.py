from causalgate.action_recommender import CausalActionRecommender, recommend_actions
from causalgate.agent_guard import ToolGuard
from causalgate.contracts import ActionPackage, DecisionPackage
from causalgate.gate import DecisionGate


class StubGateWithRecommendation:
    def evaluate(self, payload):
        return DecisionPackage(
            decision="veto",
            selected_action="place_market_order",
            candidate_action="place_market_order",
            reason="stub veto",
            reason_codes=["STUB_VETO"],
            recommended_action={
                "action_name": "paper_trade_limit_order",
                "execution_status": "proposal_only_requires_gate_review",
                "may_execute_without_guard": False,
            },
            recommended_actions=[
                {
                    "action_name": "paper_trade_limit_order",
                    "execution_status": "proposal_only_requires_gate_review",
                    "may_execute_without_guard": False,
                }
            ],
            recommendation_summary="Do not execute live order; propose paper trade.",
            recommendation_status="proposal_only_requires_gate_review",
        )


def test_step4a_recommender_proposes_paper_trade_for_vetoed_live_order():
    action = ActionPackage.from_dict(
        {
            "action_name": "place_market_order",
            "action_type": "trade_execution",
            "trusted_runtime_context": {
                "environment": "production",
                "financial_action": True,
                "trading_action": True,
                "real_money": True,
                "live_trading": True,
                "approval_present": False,
                "risk_limits_present": False,
                "margin_used": True,
            },
        }
    )
    decision = DecisionPackage(
        decision="veto",
        selected_action="place_market_order",
        risk_level="high",
        reason="Live trading requires trusted approval and risk limits.",
        reason_codes=["SAFETY_INVARIANT_LIVE_TRADE_REQUIRES_APPROVAL"],
    )

    rec = CausalActionRecommender().recommend(action, decision).to_dict()

    assert rec["recommended_action"]["action_name"] == "paper_trade_limit_order"
    assert rec["recommended_action"]["may_execute_without_guard"] is False
    assert rec["recommended_action"]["gate_required"] is True
    assert rec["recommended_action"]["execution_status"] == "proposal_only_requires_gate_review"
    assert "paper_trading_only_until_approved" in rec["safety_constraints"]
    assert "tool_guard_required" in rec["safety_constraints"]


def test_step4a_counterfactual_recommendation_becomes_next_candidate_only():
    decision = DecisionPackage(
        decision="warn",
        selected_action="answer_directly",
        causal_counterfactual={
            "compared": True,
            "current_action": "answer_directly",
            "recommended_action": "ask_clarification",
            "comparison_status": "alternative_recommended",
            "score_margin": 0.31,
        },
        reason_codes=["COUNTERFACTUAL_ALTERNATIVE_RECOMMENDED"],
    )

    rec = recommend_actions({"action_name": "answer_directly", "action_type": "communication"}, decision)

    assert rec["recommended_action"]["action_name"] == "ask_clarification"
    assert rec["recommended_action"]["recommendation_type"] == "counterfactual_safer_alternative"
    assert rec["recommended_action"]["may_execute_without_guard"] is False
    assert rec["execution_status"] == "proposal_only_requires_gate_review"


def test_step4a_decision_gate_attaches_recommendation_and_short_for_llm():
    result = DecisionGate().evaluate(
        {
            "action_name": "answer_directly",
            "action_type": "communication",
            "target_resource": "conversation",
            "environment": "development",
            "counterfactual_query": {
                "current_action": "answer_directly",
                "candidate_actions": [
                    {"action": "answer_directly", "expected_success": 0.52, "risk": "medium", "harm_probability": 0.08},
                    {"action": "ask_clarification", "expected_success": 0.78, "risk": "low", "harm_probability": 0.01},
                ],
            },
        }
    ).to_dict()

    assert result["recommended_action"]["action_name"] == "ask_clarification"
    assert result["recommended_action"]["may_execute_without_guard"] is False
    assert "ACTION_RECOMMENDATION_AVAILABLE" in result["reason_codes"]
    assert result["short_for_llm"]["recommended_action"]["action_name"] == "ask_clarification"
    assert "ToolGuard" in result["short_for_llm"]["execution_rule"]


def test_step4a_tool_guard_does_not_execute_recommended_action_when_original_is_vetoed():
    calls = []

    def executor(args):
        calls.append(args)
        return {"executed": True}

    result = ToolGuard(decision_gate=StubGateWithRecommendation()).guard_tool_call(
        {"action_name": "place_market_order"},
        tool_executor=executor,
        tool_args={"symbol": "BTC", "notional": 10000},
    )

    assert result.executed is False
    assert result.blocked is True
    assert calls == []
    assert result.decision_package["recommended_action"]["action_name"] == "paper_trade_limit_order"
    assert result.decision_package["recommended_action"]["may_execute_without_guard"] is False
