from pathlib import Path

from causalgate.learning import (
    DatasetBuilder,
    build_finetuning_dataset,
    build_learning_dataset,
    build_rct_dataset,
    export_learning_datasets,
    record_outcome,
)
from causalgate.llm_interface import propose_and_decide


def _make_logged_success(log_path: Path):
    result = propose_and_decide(
        "Non funziona, sistemalo.",
        context={"environment": "development", "ambiguity": "high", "risk_level": "low"},
        audit_log_path=str(log_path),
    )
    record_outcome(
        path=log_path,
        decision_event_id=result["audit_event"]["event_id"],
        outcome="task_success",
        user_satisfaction=1.0,
        latency_ms=900,
    )
    return result


def test_dataset_builder_creates_learning_and_rct_rows(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    _make_logged_success(log_path)

    learning_rows = build_learning_dataset(log_path)
    assert len(learning_rows) == 1
    row = learning_rows[0]
    assert row["selected_action"] == "ask_clarification"
    assert row["treatment_action"] == "ask_clarification"
    assert row["target_success"] == 1
    assert row["target_harm"] == 0
    assert row["observed"] == 1

    rct_rows = build_rct_dataset(log_path)
    assert len(rct_rows) == 1
    assert rct_rows[0]["eligible_for_rct"] == 1
    assert rct_rows[0]["rct_target"] == "target_success"


def test_dataset_builder_creates_finetuning_rows_and_exports(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    _make_logged_success(log_path)

    finetuning_rows = build_finetuning_dataset(log_path)
    assert len(finetuning_rows) == 1
    row = finetuning_rows[0]
    assert row["input"] == "Non funziona, sistemalo."
    assert row["selected_action"] == "ask_clarification"
    assert "answer_directly" in row["rejected_actions"]
    assert row["metadata"]["risk_level"] == "low"

    out_dir = tmp_path / "datasets"
    summary = export_learning_datasets(log_path, out_dir)
    assert summary["learning_rows"] == 1
    assert summary["rct_rows"] == 1
    assert summary["finetuning_rows"] == 1
    assert Path(summary["files"]["learning_events_csv"]).exists()
    assert Path(summary["files"]["finetuning_pairs_jsonl"]).exists()

    exported = Path(summary["files"]["finetuning_pairs_jsonl"]).read_text(encoding="utf-8")
    assert "ask_clarification" in exported


def test_dataset_builder_marks_harm_or_veto_as_not_rct_eligible(tmp_path):
    log_path = tmp_path / "audit.jsonl"
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
        outcome="harm_event",
        harm=True,
        user_satisfaction=0.0,
    )

    rct_rows = DatasetBuilder(log_path).build_rct_candidate_rows()
    assert rct_rows[0]["eligible_for_rct"] == 0
    assert "observed_harm" in rct_rows[0]["rct_exclusion_reason"]
