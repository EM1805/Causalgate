from causalgate.agent_guard import ToolGuard, guard_tool_call
from causalgate.contracts import DecisionPackage


class StubGate:
    def __init__(self, decision):
        self.decision = decision

    def evaluate(self, payload):
        action_name = payload.get("action_name") or payload.get("candidate_action") or "tool_call"
        return DecisionPackage(
            decision=self.decision,
            selected_action=action_name,
            candidate_action=action_name,
            reason="stub decision",
            reason_codes=["STUB_DECISION"],
            runtime_decision="STUB",
            llm_instruction="stub instruction",
        )


def test_tool_guard_veto_blocks_executor():
    calls = []

    def executor(args):
        calls.append(args)
        return {"ok": True}

    result = ToolGuard(decision_gate=StubGate("veto")).guard_tool_call(
        {"action_name": "delete_resource"},
        tool_executor=executor,
        tool_args={"path": "prod.csv"},
    )

    assert result.executed is False
    assert result.blocked is True
    assert result.execution_action == "block"
    assert result.blocked_response["decision"] == "veto"
    assert calls == []


def test_tool_guard_allow_executes_executor():
    calls = []

    def executor(args):
        calls.append(args)
        return {"ok": True, "args": args}

    result = ToolGuard(decision_gate=StubGate("allow")).guard_tool_call(
        {"action_name": "read_file"},
        tool_executor=executor,
        tool_args={"path": "README.md"},
    )

    assert result.executed is True
    assert result.blocked is False
    assert result.execution_action == "execute"
    assert result.tool_result["ok"] is True
    assert calls == [{"path": "README.md"}]


def test_tool_guard_warn_executes_with_warning():
    result = guard_tool_call(
        {"action_name": "send_email_internal"},
        decision_gate=StubGate("warn"),
        tool_executor=lambda args: {"sent": True},
        tool_args={"to": "team@example.com"},
    )

    assert result["executed"] is True
    assert result["status"] == "executed_with_warning"
    assert result["execution_action"] == "execute_with_warning"
    assert result["warning"] == "stub decision"


def test_tool_guard_ask_clarification_does_not_execute():
    result = ToolGuard(decision_gate=StubGate("ask_clarification")).guard_tool_call(
        {"action_name": "change_permissions"},
        tool_executor=lambda args: {"changed": True},
        tool_args={"resource": "repo"},
    )

    assert result.executed is False
    assert result.blocked is True
    assert result.needs_user_confirmation is True
    assert result.execution_action == "ask_user"
