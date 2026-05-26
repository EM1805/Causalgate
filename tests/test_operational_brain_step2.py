import json

from causalgate.operational_brain import run_operational_brain


def test_operational_brain_prefers_clarification_for_high_ambiguity():
    payload = {
        "user_message": "Non funziona, sistemalo.",
        "candidate_actions": ["answer_directly", "ask_clarification"],
        "context": {
            "ambiguity": "high",
            "risk_level": "medium",
            "environment": "development",
            "rollback_available": True,
        },
    }
    result = run_operational_brain(payload)
    selected = result["selected"]

    assert selected["decision"] in {"allow", "warn", "ask_clarification"}
    assert selected["selected_action"] == "ask_clarification"
    assert len(result["evaluated_actions"]) == 2


def test_operational_brain_can_route_from_destructive_action_to_safe_alternative():
    payload = {
        "user_message": "Delete the production dataset if it looks wrong.",
        "candidate_actions": [
            {
                "action_name": "delete_resource",
                "action_type": "state_change",
                "target_resource": "production_dataset",
                "environment": "production",
                "risk_level": "high",
                "reversibility": "irreversible",
                "context": {
                    "approval_present": False,
                    "rollback_available": False,
                    "resource_sensitivity": "high",
                },
            },
            {
                "action_name": "ask_clarification",
                "action_type": "communication",
                "target_resource": "conversation",
                "environment": "production",
                "risk_level": "medium",
                "context": {
                    "approval_present": False,
                    "rollback_available": True,
                },
            },
        ],
        "context": {
            "ambiguity": "high",
            "risk_level": "high",
            "environment": "production",
        },
    }

    result = run_operational_brain(payload)
    selected = result["selected"]
    evaluated = {item["selected_action"]: item for item in result["evaluated_actions"]}

    assert evaluated["delete_resource"]["decision"] == "veto"
    assert selected["selected_action"] == "ask_clarification"
    assert selected["decision"] in {"allow", "warn", "ask_clarification"}


def test_operational_brain_cli_writes_output(tmp_path):
    payload_path = tmp_path / "payload.json"
    out_path = tmp_path / "decision.json"
    payload_path.write_text(json.dumps({
        "user_message": "Help me debug.",
        "candidate_actions": ["ask_clarification"],
        "context": {"ambiguity": "high", "environment": "development"},
    }), encoding="utf-8")

    from causalgate.operational_brain.orchestrator import main

    assert main(["--input", str(payload_path), "--out", str(out_path)]) == 0
    result = json.loads(out_path.read_text(encoding="utf-8"))
    assert result["selected"]["selected_action"] == "ask_clarification"
