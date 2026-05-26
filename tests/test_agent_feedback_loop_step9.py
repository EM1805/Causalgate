from pathlib import Path

from causalgate.agent import (
    AgentFeedbackLoop,
    CausalGateAgent,
    ToolRegistry,
    ToolSpec,
    record_agent_outcome,
)
from causalgate.contracts import DecisionPackage
from causalgate.learning import DatasetBuilder, OutcomeTracker


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
            "decision_package": {"decision": self.decision, "runtime_decision": "PASS"},
        }})()


def test_agent_feedback_loop_writes_learning_decision_event(tmp_path):
    audit_path = tmp_path / "agent_learning.jsonl"
    brain = StubBrain(DecisionPackage(decision="veto", selected_action="delete_resource", risk_level="high"))
    result = CausalGateAgent(brain=brain, tool_guard=StubGuard(), audit_log_path=audit_path).run(
        "Cancella la risorsa in produzione.",
        trusted_runtime_context={"environment": "production", "approval_present": False},
        candidate_actions=[
            {
                "action_name": "delete_resource",
                "action_type": "state_change",
                "risk_level": "high",
                "trusted_runtime_context": {"environment": "production", "approval_present": False},
            }
        ],
    ).to_dict()

    event = result["audit_event"]
    assert event["event_type"] == "decision"
    assert event["source"] == "causalgate_agent_runtime"
    assert event["selected_action"] == "delete_resource"
    assert event["gate_decision"] == "ask_clarification"
    assert result["status"] == "production_approval_required"
    assert result["registry_policy_result"]["status"] == "production_approval_required"
    assert "recommendation" in event["payload"]
    assert "evidence_bundle" in event["payload"]
    assert "delete_resource" in event["candidate_actions"]


def test_agent_outcome_feedback_builds_learning_dataset(tmp_path):
    audit_path = tmp_path / "agent_learning.jsonl"
    calls = []

    def safe_tool(args):
        calls.append(dict(args))
        return {"ok": True, "args": dict(args)}

    registry = ToolRegistry()
    registry.register(ToolSpec(name="paper_trade_limit_order", executor=safe_tool))

    brain = StubBrain(DecisionPackage(decision="allow", selected_action="paper_trade_limit_order", risk_level="low"))
    result = CausalGateAgent(
        brain=brain,
        tool_guard=StubGuard(),
        tool_registry=registry,
        audit_log_path=audit_path,
    ).run(
        "Simula un paper trade con limite.",
        trusted_runtime_context={"paper_trading": True, "risk_limits_present": True},
        candidate_actions=[
            {
                "action_name": "paper_trade_limit_order",
                "action_type": "trade_execution",
                "risk_level": "low",
                "trusted_runtime_context": {"paper_trading": True, "risk_limits_present": True},
            }
        ],
        tool_args={"symbol": "BTC", "notional": 100},
    ).to_dict()

    outcome = record_agent_outcome(
        path=audit_path,
        decision_event_id=result["audit_event"]["event_id"],
        outcome="task_success",
        user_satisfaction=0.9,
        latency_ms=120,
        metadata={"observed_profit": 0, "mode": "paper"},
    )

    assert outcome["event_type"] == "outcome"
    records = OutcomeTracker(audit_path).build_records()
    assert len(records) == 1
    assert records[0].selected_action == "paper_trade_limit_order"
    assert records[0].success is True
    assert records[0].harm is False

    rows = DatasetBuilder(audit_path).build_learning_rows()
    assert len(rows) == 1
    assert rows[0]["selected_action"] == "paper_trade_limit_order"
    assert rows[0]["target_success"] == 1
    assert rows[0]["target_harm"] == 0


def test_feedback_loop_exports_datasets(tmp_path):
    audit_path = tmp_path / "agent_learning.jsonl"
    loop = AgentFeedbackLoop(audit_path)
    decision_event = loop.append_agent_decision({
        "status": "respond",
        "response_type": "communication",
        "user_message": "Spiega il blocco.",
        "selected_action": "ask_clarification",
        "decision": "ask_clarification",
        "executed": False,
        "blocked": False,
        "llm_response": {
            "candidate_actions": [{"action_name": "ask_clarification"}, {"action_name": "delete_resource"}]
        },
        "brain_result": {
            "selected": {"selected_action": "ask_clarification", "decision": "ask_clarification"},
            "evaluated_actions": [
                {"selected_action": "ask_clarification", "decision": "ask_clarification"},
                {"selected_action": "delete_resource", "decision": "veto"},
            ],
        },
        "recommendation": {},
        "evidence_bundle": {},
    })
    loop.record_outcome(decision_event_id=decision_event["event_id"], outcome="task_success")

    summary = loop.export_datasets(tmp_path / "datasets")
    assert summary["learning_rows"] == 1
    assert summary["finetuning_rows"] == 1
    assert Path(summary["files"]["learning_events_csv"]).exists()
