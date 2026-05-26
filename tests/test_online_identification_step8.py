from causalgate.gate import DecisionGate
from causalgate.operational_brain import OperationalBrain


SIMPLE_AGENT_GRAPH = {
    "nodes": [
        {"id": "agent_action"},
        {"id": "task_success"},
        {"id": "ambiguity"},
    ],
    "edges": [
        ["ambiguity", "agent_action"],
        ["ambiguity", "task_success"],
        ["agent_action", "task_success"],
    ],
}


def test_decision_gate_runs_optional_scm_id_when_graph_is_present():
    payload = {
        "action_name": "answer_directly",
        "candidate_action": "answer_directly",
        "action_type": "communication",
        "target_resource": "conversation",
        "environment": "development",
        "risk_level": "low",
        "scm_graph": SIMPLE_AGENT_GRAPH,
        "treatment": "agent_action",
        "outcome": "task_success",
        "adjustment_set": ["ambiguity"],
    }

    result = DecisionGate().evaluate(payload)

    assert result.decision == "allow"
    assert result.runtime_decision == "PASS"
    assert result.causal_identification["identified"] is True
    assert result.identification_tier == "identified_graphical"
    assert "SCM_ID_IDENTIFIED" in result.reason_codes


def test_decision_gate_does_not_require_scm_graph_for_runtime_routing():
    payload = {
        "action_name": "answer_directly",
        "candidate_action": "answer_directly",
        "action_type": "communication",
        "target_resource": "conversation",
        "environment": "development",
    }

    result = DecisionGate().evaluate(payload)

    assert result.decision == "allow"
    assert result.runtime_decision == "PASS"
    assert result.causal_identification == {}


def test_operational_brain_preserves_online_identification_in_evaluated_actions():
    payload = {
        "user_message": "Rispondi direttamente?",
        "candidate_actions": ["answer_directly", "ask_clarification"],
        "context": {"environment": "development", "ambiguity": "low"},
        "risk_level": "low",
        "scm_graph": SIMPLE_AGENT_GRAPH,
        "treatment": "agent_action",
        "outcome": "task_success",
        "adjustment_set": ["ambiguity"],
    }

    result = OperationalBrain().run(payload).to_dict()

    assert result["selected"]["decision"] == "allow"
    assert result["selected"]["causal_identification"]["identified"] is True
    assert all(item["causal_identification"] for item in result["evaluated_actions"])
