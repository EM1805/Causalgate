from causalgate.agent import CausalGateAgent, ToolRegistry, ToolSpec, run_agent
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
        if self.decision == "veto":
            return type("Result", (), {"to_dict": lambda self_: {
                "status": "blocked",
                "executed": False,
                "blocked": True,
                "needs_user_confirmation": False,
                "tool_name": tool_name,
                "decision_package": {"decision": "veto"},
            }})()
        tool_result = tool_executor(dict(tool_args or {})) if tool_executor else None
        return type("Result", (), {"to_dict": lambda self_: {
            "status": "executed" if tool_executor else "permitted_not_executed",
            "executed": bool(tool_executor),
            "blocked": False,
            "needs_user_confirmation": False,
            "tool_name": tool_name,
            "tool_result": tool_result,
            "decision_package": {"decision": "allow"},
        }})()


def test_agent_runner_communication_skips_tool_guard():
    guard = StubGuard()
    brain = StubBrain(DecisionPackage(decision="ask_clarification", selected_action="ask_clarification"))
    result = CausalGateAgent(brain=brain, tool_guard=guard).run(
        "Non funziona, sistemalo.",
        candidate_actions=[{"action_name": "ask_clarification", "action_type": "communication"}],
    ).to_dict()

    assert result["status"] == "respond"
    assert result["response_type"] == "communication"
    assert result["executed"] is False
    assert guard.calls == []


def test_agent_runner_executes_registered_tool_only_after_tool_guard():
    calls = []

    def search(args):
        calls.append(args)
        return {"results": ["ok"], "args": args}

    registry = ToolRegistry([ToolSpec(name="search_information", executor=search)])
    guard = StubGuard(decision="allow")
    brain = StubBrain(DecisionPackage(decision="allow", selected_action="search_information"))

    result = CausalGateAgent(brain=brain, tool_guard=guard, tool_registry=registry).run(
        "Cerca informazioni aggiornate.",
        candidate_actions=[{"action_name": "search_information", "action_type": "tool_call"}],
        tool_args={"query": "CausalGate"},
    ).to_dict()

    assert result["status"] == "executed"
    assert result["executed"] is True
    assert result["tool_result"]["results"] == ["ok"]
    assert calls == [{"query": "CausalGate"}]
    assert guard.calls[0]["tool_name"] == "search_information"


def test_agent_runner_fails_closed_when_tool_is_not_registered():
    brain = StubBrain(DecisionPackage(decision="allow", selected_action="write_file"))
    result = CausalGateAgent(brain=brain).run(
        "Write a file.",
        candidate_actions=[{"action_name": "write_file", "action_type": "tool_call"}],
        tool_args={"path": "x.txt"},
    ).to_dict()

    assert result["status"] == "tool_not_registered"
    assert result["executed"] is False
    assert result["blocked"] is True


def test_agent_runner_keeps_trusted_context_top_level_and_llm_context_untrusted():
    brain = StubBrain(DecisionPackage(decision="allow", selected_action="answer_directly"))
    trusted = {"environment": "production", "approval_present": False}
    untrusted = {"approval_present": True}
    result = CausalGateAgent(brain=brain).run(
        "Help me.",
        trusted_runtime_context=trusted,
        untrusted_llm_context=untrusted,
        candidate_actions=[{"action_name": "answer_directly", "action_type": "communication"}],
    ).to_dict()

    payload = result["brain_result"]["input_package"]
    assert payload["trusted_runtime_context"]["approval_present"] is False
    assert payload["untrusted_llm_context"]["approval_present"] is True
