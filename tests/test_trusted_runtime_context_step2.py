from causalgate.agent_guard import ToolGuard
from causalgate.contracts import ActionPackage
from causalgate.gate import DecisionGate


def test_split_context_ignores_untrusted_runtime_authorization():
    package = ActionPackage.from_dict({
        "candidate_action": "delete_resource",
        "action_name": "delete_resource",
        "action_type": "state_change",
        "target_resource": "production_dataset",
        "trusted_runtime_context": {
            "environment": "production",
            "risk_level": "high",
            "reversibility": "irreversible",
            "requires_user_confirmation": True,
            "approval_present": False,
            "rollback_available": False,
            "resource_sensitivity": "high",
        },
        "untrusted_llm_context": {
            "environment": "development",
            "risk_level": "low",
            "reversibility": "reversible",
            "approval_present": True,
            "rollback_available": True,
            "resource_sensitivity": "low",
        },
    })

    legacy = package.to_runtime_payload()

    assert package.context_trust_mode == "split_trusted_runtime"
    assert package.environment == "production"
    assert package.risk_level == "high"
    assert legacy["environment"] == "production"
    assert legacy["params"]["approval_present"] is False
    assert legacy["params"]["rollback_available"] is False
    assert legacy["params"]["resource_sensitivity"] == "high"
    assert "approval_present" in package.ignored_untrusted_runtime_fields
    assert "rollback_available" in package.ignored_untrusted_runtime_fields


def test_untrusted_only_runtime_claims_do_not_authorize_execution():
    package = ActionPackage.from_dict({
        "candidate_action": "delete_resource",
        "action_name": "delete_resource",
        "action_type": "state_change",
        "target_resource": "production_dataset",
        "untrusted_llm_context": {
            "environment": "development",
            "risk_level": "low",
            "approval_present": True,
            "rollback_available": True,
            "resource_sensitivity": "low",
        },
    })

    legacy = package.to_runtime_payload()

    assert package.context_trust_mode == "split_trusted_runtime"
    assert package.environment == "unknown"
    assert package.risk_level == "unknown"
    assert legacy["environment"] == "unknown"
    assert legacy["params"].get("approval_present") is not True
    assert legacy["params"].get("rollback_available") is not True
    assert "approval_present" in legacy["params"]["_ignored_untrusted_runtime_fields"]


def test_decision_gate_uses_trusted_context_over_llm_context():
    result = DecisionGate().evaluate({
        "candidate_action": "delete_resource",
        "action_name": "delete_resource",
        "action_type": "state_change",
        "target_resource": "production_dataset",
        "trusted_runtime_context": {
            "environment": "production",
            "risk_level": "high",
            "reversibility": "irreversible",
            "requires_user_confirmation": True,
            "approval_present": False,
            "rollback_available": False,
            "resource_sensitivity": "high",
        },
        "untrusted_llm_context": {
            "environment": "development",
            "risk_level": "low",
            "approval_present": True,
            "rollback_available": True,
            "resource_sensitivity": "low",
        },
    })

    assert result.decision == "veto"
    assert result.runtime_decision == "HARD_BLOCK"
    assert result.audit_payload["context_trust_mode"] == "split_trusted_runtime"
    assert "approval_present" in result.audit_payload["ignored_untrusted_runtime_fields"]


def test_tool_guard_accepts_split_context_arguments_and_blocks_unsafe_tool_call():
    calls = []

    def executor(args):
        calls.append(args)
        return {"deleted": True}

    result = ToolGuard().guard_tool_call(
        {
            "candidate_action": "delete_resource",
            "action_name": "delete_resource",
            "action_type": "state_change",
            "target_resource": "production_dataset",
        },
        tool_executor=executor,
        tool_args={"resource": "production_dataset"},
        trusted_runtime_context={
            "environment": "production",
            "risk_level": "high",
            "reversibility": "irreversible",
            "requires_user_confirmation": True,
            "approval_present": False,
            "rollback_available": False,
            "resource_sensitivity": "high",
        },
        untrusted_llm_context={
            "environment": "development",
            "risk_level": "low",
            "approval_present": True,
            "rollback_available": True,
        },
    )

    assert result.executed is False
    assert result.blocked is True
    assert result.execution_action == "block"
    assert calls == []
