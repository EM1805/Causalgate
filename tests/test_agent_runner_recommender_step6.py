from causalgate.agent import CausalGateAgent, ToolRegistry, ToolSpec
from causalgate.contracts import DecisionPackage


class StubBrain:
    def __init__(self, selected, evaluated=None):
        self.selected = selected
        self.evaluated = evaluated or [selected]
        self.last_payload = None

    def run(self, payload):
        self.last_payload = payload

        class Run:
            def __init__(self, selected, evaluated, payload):
                self.selected = selected
                self.evaluated = evaluated
                self.payload = payload

            def to_dict(self):
                return {
                    "mode": "test",
                    "selected": self.selected.to_dict(),
                    "evaluated_actions": [item.to_dict() for item in self.evaluated],
                    "input_package": self.payload,
                    "notes": [],
                }

        return Run(self.selected, self.evaluated, payload)


class StubGuard:
    def __init__(self, decision="allow"):
        self.decision = decision
        self.calls = []

    def guard_tool_call(self, action_payload, *, tool_executor=None, tool_args=None, tool_name="", **kwargs):
        self.calls.append({"payload": action_payload, "tool_name": tool_name, "tool_args": dict(tool_args or {})})
        return type("Result", (), {"to_dict": lambda self_: {
            "status": "blocked" if self.decision == "veto" else ("executed" if tool_executor else "permitted_not_executed"),
            "executed": bool(tool_executor) and self.decision != "veto",
            "blocked": self.decision == "veto",
            "needs_user_confirmation": False,
            "tool_name": tool_name,
            "tool_result": tool_executor(dict(tool_args or {})) if tool_executor and self.decision != "veto" else None,
            "decision_package": {"decision": self.decision},
        }})()


def test_agent_runner_attaches_trading_recommendation_without_execution():
    brain = StubBrain(DecisionPackage(decision="veto", selected_action="place_market_order"))
    guard = StubGuard()
    result = CausalGateAgent(brain=brain, tool_guard=guard).run(
        "Compra BTC ora a mercato.",
        trusted_runtime_context={
            "live_trading": True,
            "real_money": True,
            "approval_present": False,
            "risk_limits_present": False,
        },
        candidate_actions=[
            {
                "action_name": "place_market_order",
                "action_type": "trade_execution",
                "trusted_runtime_context": {
                    "live_trading": True,
                    "real_money": True,
                    "approval_present": False,
                    "risk_limits_present": False,
                },
            }
        ],
    ).to_dict()

    assert result["status"] == "live_trading_veto_default"
    assert result["executed"] is False
    assert result["blocked"] is True
    assert result["recommended_action"]["action_name"] == "paper_trade_limit_order"
    assert result["recommended_action"]["may_execute_without_guard"] is False
    assert result["recommendation_requires_recheck"] is True
    assert "Do not execute place_market_order" in result["recommendation_summary"]
    assert result["recommendation"]["may_execute_directly"] is False
    assert result["tool_guard_result"]["status"] == "not_invoked"
    assert result["registry_policy_result"]["status"] == "live_trading_veto_default"
    assert guard.calls == []


def test_agent_runner_recommendation_does_not_autorun_registered_alternative():
    calls = []

    def paper_trade(args):
        calls.append(args)
        return {"paper_trade_created": True}

    registry = ToolRegistry([ToolSpec(name="paper_trade_limit_order", executor=paper_trade)])
    brain = StubBrain(DecisionPackage(decision="veto", selected_action="place_market_order"))
    result = CausalGateAgent(brain=brain, tool_guard=StubGuard(), tool_registry=registry).run(
        "Compra BTC live.",
        trusted_runtime_context={"live_trading": True, "real_money": True, "approval_present": False},
        candidate_actions=[
            {
                "action_name": "place_market_order",
                "action_type": "trade_execution",
                "trusted_runtime_context": {"live_trading": True, "real_money": True, "approval_present": False},
            }
        ],
    ).to_dict()

    assert result["recommended_action"]["action_name"] == "paper_trade_limit_order"
    assert calls == []
    assert result["executed"] is False
    assert result["selected_action"] == "place_market_order"
    assert result["status"] == "live_trading_veto_default"


def test_agent_runner_recommended_action_can_be_rechecked_as_new_candidate():
    calls = []

    def paper_trade(args):
        calls.append(args)
        return {"paper_trade_created": True, "args": args}

    registry = ToolRegistry([ToolSpec(name="paper_trade_limit_order", executor=paper_trade)])
    brain = StubBrain(DecisionPackage(decision="allow", selected_action="paper_trade_limit_order"))
    result = CausalGateAgent(brain=brain, tool_guard=StubGuard(), tool_registry=registry).run(
        "Simula paper trade con limite.",
        trusted_runtime_context={"live_trading": False, "paper_trading": True, "risk_limits_present": True},
        candidate_actions=[
            {
                "action_name": "paper_trade_limit_order",
                "action_type": "trade_execution",
                "trusted_runtime_context": {
                    "live_trading": False,
                    "paper_trading": True,
                    "risk_limits_present": True,
                },
            }
        ],
        tool_args={"symbol": "BTC", "notional": 100, "limit_price": 50000},
    ).to_dict()

    assert result["status"] == "executed"
    assert result["executed"] is True
    assert calls == [{"symbol": "BTC", "notional": 100, "limit_price": 50000}]
    assert result["recommendation_requires_recheck"] is True


def test_agent_runner_audit_includes_recommendation(tmp_path):
    audit_path = tmp_path / "agent_audit.jsonl"
    brain = StubBrain(DecisionPackage(decision="veto", selected_action="delete_resource"))
    result = CausalGateAgent(brain=brain, tool_guard=StubGuard(), audit_log_path=audit_path).run(
        "Cancella risorsa prod.",
        trusted_runtime_context={"environment": "production", "approval_present": False},
        candidate_actions=[
            {
                "action_name": "delete_resource",
                "action_type": "state_change",
                "trusted_runtime_context": {"environment": "production", "approval_present": False},
            }
        ],
    ).to_dict()

    assert result["audit_event"]
    text = audit_path.read_text(encoding="utf-8")
    assert "recommendation" in text
    assert "recommended_action" in text
    assert "delete_resource" in text
