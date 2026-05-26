from causalgate.learning import AuditLog, OutcomeTracker, build_outcome_records, record_outcome, summarize_outcomes
from causalgate.llm_interface import propose_and_decide


def test_outcome_tracker_links_decision_to_success_outcome(tmp_path):
    log_path = tmp_path / "learning.jsonl"
    result = propose_and_decide(
        "Non funziona, sistemalo.",
        context={"environment": "development"},
        audit_log_path=str(log_path),
    )
    decision_event_id = result["audit_event"]["event_id"]

    outcome_event = record_outcome(
        path=log_path,
        decision_event_id=decision_event_id,
        outcome="task_success",
        user_satisfaction=1.0,
        latency_ms=1200,
    )

    events = AuditLog(log_path).read_events()
    assert len(events) == 2
    assert outcome_event["payload"]["linked_event_id"] == decision_event_id
    assert outcome_event["payload"]["success"] is True
    assert outcome_event["payload"]["harm"] is False

    records = OutcomeTracker(log_path).build_records()
    assert len(records) == 1
    assert records[0].decision_event_id == decision_event_id
    assert records[0].selected_action == "ask_clarification"
    assert records[0].outcome == "task_success"
    assert records[0].success is True
    assert records[0].harm is False


def test_outcome_tracker_summary_and_export(tmp_path):
    log_path = tmp_path / "learning.jsonl"
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

    record_outcome(
        path=log_path,
        decision_event_id=result["audit_event"]["event_id"],
        outcome="task_success",
        user_satisfaction=0.8,
    )

    summary = summarize_outcomes(log_path)
    assert summary["records_n"] == 1
    assert summary["by_action"]["ask_clarification"]["success_rate"] == 1.0
    assert summary["by_action"]["ask_clarification"]["avg_user_satisfaction"] == 0.8

    out = tmp_path / "records.jsonl"
    count = OutcomeTracker(log_path).export_records_jsonl(out)
    assert count == 1
    assert "ask_clarification" in out.read_text(encoding="utf-8")

    records = build_outcome_records(log_path)
    assert records[0]["gate_decision"] == "allow"
