from causalgate.agent import CausalGateAgent, ToolRegistry, ToolSpec
from causalgate.contracts import DecisionPackage


class StubBrain:
    def __init__(self, selected):
        self.selected = selected

    def run(self, payload):
        selected = self.selected

        class Run:
            def to_dict(self):
                return {"selected": selected.to_dict(), "evaluated_actions": [selected.to_dict()], "notes": []}

        return Run()


class StubGuard:
    def __init__(self):
        self.calls = []

    def guard_tool_call(self, action_payload, *, tool_executor=None, tool_args=None, tool_name="", **kwargs):
        self.calls.append({"tool_name": tool_name, "tool_args": dict(tool_args or {})})
        return type("Result", (), {"to_dict": lambda self_: {
            "status": "executed" if tool_executor else "permitted_not_executed",
            "executed": bool(tool_executor),
            "blocked": False,
            "needs_user_confirmation": False,
            "tool_name": tool_name,
            "tool_result": tool_executor(dict(tool_args or {})) if tool_executor else None,
            "decision_package": {"decision": "allow"},
        }})()


def test_live_trading_blocked_by_finance_mode_registry_policy():
    registry = ToolRegistry([ToolSpec(name="place_market_order", executor=lambda args: {"executed": True})])
    agent = CausalGateAgent(brain=StubBrain(DecisionPackage(decision="allow", selected_action="place_market_order")), tool_guard=StubGuard(), tool_registry=registry)
    result = agent.run(
        "buy live",
        agent_mode="finance_trading_agent",
        trusted_runtime_context={"live_trading": True, "real_money": True, "approval_present": False},
        candidate_actions=[{"action_name": "place_market_order"}],
        execute_tools=True,
    ).to_dict()
    assert result["status"] == "live_trading_veto_default"
    assert result["executed"] is False
    assert result["agent_mode"] == "finance_trading_agent"


def test_code_mode_blocks_ops_action_before_toolguard():
    registry = ToolRegistry([ToolSpec(name="delete_resource", executor=lambda args: {"deleted": True})])
    guard = StubGuard()
    agent = CausalGateAgent(brain=StubBrain(DecisionPackage(decision="allow", selected_action="delete_resource")), tool_guard=guard, tool_registry=registry)
    result = agent.run(
        "delete prod",
        agent_mode="code_agent",
        trusted_runtime_context={"environment": "production", "approval_present": True},
        candidate_actions=[{"action_name": "delete_resource"}],
        execute_tools=True,
    ).to_dict()
    assert result["status"] == "action_not_allowed_in_agent_mode"
    assert result["executed"] is False
    assert guard.calls == []


def test_tool_schema_validation_blocks_missing_required_arg():
    calls = []
    def write_file(args):
        calls.append(args)
        return {"ok": True}
    registry = ToolRegistry([ToolSpec(name="write_file", executor=write_file, input_schema={"required": ["path", "content"]})])
    agent = CausalGateAgent(brain=StubBrain(DecisionPackage(decision="allow", selected_action="write_file")), tool_guard=StubGuard(), tool_registry=registry)
    result = agent.run(
        "write",
        agent_mode="code_agent",
        trusted_runtime_context={"approval_present": True},
        candidate_actions=[{"action_name": "write_file"}],
        tool_args={"path": "x.txt"},
        execute_tools=True,
    ).to_dict()
    assert result["status"] == "tool_schema_invalid"
    assert calls == []


def test_safe_read_file_can_execute_in_code_mode():
    calls = []
    def read_file(args):
        calls.append(args)
        return {"content": "ok"}
    registry = ToolRegistry([ToolSpec(name="read_file", executor=read_file, input_schema={"required": ["path"]})])
    agent = CausalGateAgent(brain=StubBrain(DecisionPackage(decision="allow", selected_action="read_file")), tool_guard=StubGuard(), tool_registry=registry)
    result = agent.run(
        "read",
        agent_mode="code_agent",
        candidate_actions=[{"action_name": "read_file"}],
        tool_args={"path": "README.md"},
        execute_tools=True,
    ).to_dict()
    assert result["executed"] is True
    assert calls == [{"path": "README.md"}]
