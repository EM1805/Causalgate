from causalgate.contracts import ActionPackage
from causalgate.gate import DecisionGate


def test_action_package_converts_to_legacy_runtime_payload():
    package = ActionPackage.from_dict({
        "candidate_action": "delete_resource",
        "action_type": "mutation",
        "target_resource": "prod_table",
        "environment": "production",
        "risk_level": "high",
        "reversibility": "irreversible",
        "requires_user_confirmation": True,
        "context": {"approval_present": False},
    })
    legacy = package.to_runtime_payload()
    assert legacy["action_name"] == "delete_resource"
    assert legacy["params"]["rollback_available"] is False
    assert legacy["params"]["approval_present"] is False


def test_decision_gate_maps_irreversible_prod_delete_to_veto():
    result = DecisionGate().evaluate({
        "candidate_action": "delete_resource",
        "action_name": "delete_resource",
        "action_type": "mutation",
        "target_resource": "prod_table",
        "environment": "production",
        "risk_level": "high",
        "reversibility": "irreversible",
        "requires_user_confirmation": True,
        "context": {"approval_present": False, "rollback_available": False, "resource_sensitivity": "high"},
    })
    assert result.decision == "veto"
    assert result.runtime_decision == "HARD_BLOCK"
    assert "SAFETY_INVARIANT_IRREVERSIBLE_DESTRUCTIVE_PROD" in result.reason_codes


def test_missing_action_name_becomes_ask_clarification_not_product_veto():
    result = DecisionGate().evaluate({
        "user_message": "Do the thing",
        "candidate_action": "",
        "environment": "production",
    })
    assert result.decision == "ask_clarification"
    assert result.runtime_decision == "HARD_BLOCK"
