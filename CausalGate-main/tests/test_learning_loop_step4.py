import json

from causalgate.learning import AuditLog, append_decision, append_outcome, build_decision_event
from causalgate.llm_interface import propose_and_decide


def test_learning_builds_decision_event_from_online_result():
    result = propose_and_decide("Non funziona, sistemalo.", context={"environment": "development"})
    event = build_decision_event(result)

    assert event.event_type == "decision"
    assert event.user_message == "Non funziona, sistemalo."
    assert event.selected_action == "ask_clarification"
    assert "ask_clarification" in event.candidate_actions
    assert event.gate_decision in {"allow", "warn", "ask_clarification"}


def test_learning_audit_log_appends_decision_and_outcome(tmp_path):
    log_path = tmp_path / "audit_log.jsonl"
    result = propose_and_decide("Non funziona, sistemalo.", context={"environment": "development"})

    decision_event = append_decision(result, path=log_path)
    outcome_event = append_outcome(
        path=log_path,
        event_id=decision_event["event_id"],
        selected_action=decision_event["selected_action"],
        outcome="task_success",
        user_satisfaction=1.0,
    )

    events = AuditLog(log_path).read_events()
    assert len(events) == 2
    assert events[0]["event_type"] == "decision"
    assert events[1]["event_type"] == "outcome"
    assert events[1]["payload"]["linked_event_id"] == decision_event["event_id"]


def test_propose_and_decide_can_write_audit_log(tmp_path):
    log_path = tmp_path / "online.jsonl"
    result = propose_and_decide(
        "Delete the production dataset if it looks wrong.",
        context={
            "environment": "production",
            "risk_level": "high",
            "ambiguity": "high",
            "approval_present": False,
            "rollback_available": False,
            "resource_sensitivity": "high",
        },
        audit_log_path=str(log_path),
    )

    assert "audit_event" in result
    events = AuditLog(log_path).read_events()
    assert len(events) == 1
    assert events[0]["selected_action"] == "ask_clarification"
    assert "delete_resource" in events[0]["candidate_actions"]
