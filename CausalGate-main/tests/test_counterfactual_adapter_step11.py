from causalgate.causal_core.counterfactual import CounterfactualEngine
from causalgate.gate import DecisionGate
from causalgate.operational_brain import OperationalBrain


def test_counterfactual_recommends_safer_higher_success_action():
    result = CounterfactualEngine().compare({
        "current_action": "answer_directly",
        "candidate_actions": [
            {"action": "answer_directly", "expected_success": 0.52, "risk": "medium", "harm_probability": 0.08},
            {"action": "ask_clarification", "expected_success": 0.78, "risk": "low", "harm_probability": 0.01},
        ],
    }).to_dict()
    assert result["compared"] is True
    assert result["recommended_action"] == "ask_clarification"
    assert result["comparison_status"] == "alternative_recommended"


def test_decision_gate_attaches_counterfactual_payload():
    result = DecisionGate().evaluate({
        "action_name": "answer_directly",
        "action_type": "communication",
        "target_resource": "conversation",
        "environment": "development",
        "counterfactual_query": {
            "current_action": "answer_directly",
            "candidate_actions": [
                {"action": "answer_directly", "expected_success": 0.52, "risk": "medium", "harm_probability": 0.08},
                {"action": "ask_clarification", "expected_success": 0.78, "risk": "low", "harm_probability": 0.01},
            ],
        },
    }).to_dict()
    assert result["causal_counterfactual"]["recommended_action"] == "ask_clarification"
    assert "COUNTERFACTUAL_COMPARED" in result["reason_codes"]


def test_operational_brain_can_select_counterfactual_recommendation():
    result = OperationalBrain().run({
        "user_message": "Non funziona, sistemalo.",
        "context": {
            "environment": "development",
            "ambiguity": "high",
            "counterfactual_query": {
                "candidate_actions": [
                    {"action": "answer_directly", "expected_success": 0.52, "risk": "medium", "harm_probability": 0.08},
                    {"action": "ask_clarification", "expected_success": 0.78, "risk": "low", "harm_probability": 0.01},
                    {"action": "use_tool", "expected_success": 0.71, "risk": "low", "harm_probability": 0.02},
                ]
            },
        },
        "candidate_actions": ["answer_directly", "ask_clarification", "use_tool"],
    }).to_dict()
    assert result["selected"]["selected_action"] == "ask_clarification"
