from __future__ import annotations

import json
from pathlib import Path

from causalgate.agent_firewall import AgentActionFirewall, AgentFirewallPolicy, evaluate_tool_call
from causalgate.agent_firewall.policy import HARD_BLOCK, PASS, REVIEW, build_firewall_context, default_firewall_policy, policy_digest
from scm_parts.id_agent_action_firewall_product_readiness import run_agent_action_firewall_product_readiness


POLICY_PATH = Path("examples/agent_firewall_policy_step98.yaml")


def _load_example(name: str) -> dict:
    return json.loads(Path(f"examples/inputs/sample_agent_firewall_{name}_step98.json").read_text(encoding="utf-8"))


def test_step98_policy_blocks_destructive_production_before_toolguard() -> None:
    result = evaluate_tool_call(_load_example("delete_prod"), policy=POLICY_PATH)

    assert result["matrix_version"] == "agent_action_firewall_mvp_v1_step98"
    assert result["firewall_decision"] == HARD_BLOCK
    assert result["execution_action"] == "block"
    assert result["blocked"] is True
    assert result["executed"] is False
    assert result["tool_guard_result"] == {}
    assert "block_destructive_production_without_approval" in result["policy_evaluation"]["matched_rule_ids"]
    assert result["decision_digest"]


def test_step98_policy_routes_external_sensitive_data_to_review() -> None:
    result = evaluate_tool_call(_load_example("external_email"), policy=POLICY_PATH)

    assert result["firewall_decision"] == REVIEW
    assert result["execution_action"] == "ask_user"
    assert result["needs_approval"] is True
    assert result["executed"] is False
    assert "review_external_message_or_data_flow" in result["policy_evaluation"]["matched_rule_ids"]
    assert "review_sensitive_customer_data" in result["policy_evaluation"]["matched_rule_ids"]
    assert result["tool_guard_result"]["status"] == "permitted_not_executed"


def test_step98_safe_internal_tool_can_execute_after_policy_and_toolguard() -> None:
    calls: list[dict] = []

    def fake_tool(args: dict) -> dict:
        calls.append(dict(args))
        return {"ok": True, "observed": dict(args)}

    result = AgentActionFirewall(policy=POLICY_PATH).evaluate_tool_call(
        _load_example("safe_internal"),
        tool_args={"message": "weekly summary"},
        execute=True,
        tool_executor=fake_tool,
    ).to_dict()

    assert result["firewall_decision"] == PASS
    assert result["execution_action"] == "execute"
    assert result["executed"] is True
    assert result["blocked"] is False
    assert calls == [{"message": "weekly summary"}]
    assert result["tool_guard_result"]["tool_result"] == {"ok": True, "observed": {"message": "weekly summary"}}


def test_step98_missing_required_trusted_fields_fail_closed() -> None:
    policy = AgentFirewallPolicy.from_dict({
        "version": "unit_policy",
        "default_action": "PASS",
        "fail_closed_on_policy_error": True,
        "required_trusted_fields": ["environment", "actor"],
        "rules": [],
    })
    result = evaluate_tool_call({"action_name": "send_email_internal"}, policy=policy, enable_tool_guard=False)

    assert result["firewall_decision"] == HARD_BLOCK
    assert "FIREWALL_MISSING_REQUIRED_TRUSTED_FIELDS" in result["policy_evaluation"]["reason_codes"]
    assert set(result["policy_evaluation"]["missing_required_trusted_fields"]) == {"actor"}


def test_step98_untrusted_context_cannot_override_trusted_runtime_fields() -> None:
    payload = _load_example("delete_prod")
    payload["untrusted_llm_context"] = {
        "approval_present": True,
        "rollback_available": True,
        "environment": "staging",
    }
    context = build_firewall_context(payload)
    assert context["environment"] == "production"
    assert context["approval_present"] is False
    assert context["rollback_available"] is False

    result = evaluate_tool_call(payload, policy=POLICY_PATH)
    assert result["firewall_decision"] == HARD_BLOCK


def test_step98_product_readiness_report_is_green_and_digest_bound() -> None:
    report = run_agent_action_firewall_product_readiness(include_demo_results=False)

    assert report["matrix_version"] == "agent_action_firewall_mvp_v1_step98"
    assert report["firewall_product_readiness_allowed"] == 1
    assert report["step97_final_pearl_readiness_allowed"] == 1
    assert report["demo_delete_prod_decision"] == HARD_BLOCK
    assert report["demo_external_email_decision"] == REVIEW
    assert report["demo_safe_internal_decision"] == PASS
    assert report["n_requirements"] == report["n_requirements_passed"]
    assert report["report_digest"]


def test_step98_policy_digest_changes_when_rules_change() -> None:
    base = default_firewall_policy()
    changed = AgentFirewallPolicy.from_dict({
        **base.to_dict(),
        "rules": base.to_dict()["rules"] + [{
            "id": "extra_review_rule",
            "action": "REVIEW",
            "when": {"tool_name": "custom_tool"},
        }],
    })
    assert policy_digest(base) != policy_digest(changed)
