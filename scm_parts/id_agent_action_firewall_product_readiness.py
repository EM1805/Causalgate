from __future__ import annotations

"""Step 98 product readiness report for the CausalGate Agent Action Firewall MVP.

This report does not replace the Step-97 Pearl readiness report.  It verifies
that the Pearl/veto core is packaged behind a sellable pre-execution agent
firewall surface: policy-as-code, fail-closed evaluation, ToolGuard integration,
audit digesting, and demo scenarios.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Mapping, Sequence

from causalgate.agent_firewall.gateway import evaluate_tool_call
from causalgate.agent_firewall.policy import HARD_BLOCK, PASS, REVIEW, default_firewall_policy, policy_digest
from scm_parts.id_final_pearl_readiness_report import run_final_pearl_readiness_report

AGENT_ACTION_FIREWALL_PRODUCT_READINESS_VERSION = "agent_action_firewall_mvp_v1_step98"
AGENT_ACTION_FIREWALL_PRODUCT_SCOPE = "pre_execution_ai_agent_firewall_policy_toolguard_audit_surface_step98"


@dataclass(frozen=True)
class FirewallProductRequirement:
    requirement: str
    passed: bool
    observed: str
    expected: str
    blocker_class: str
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "pass", "passed", "complete", "green"}


def _req(name: str, passed: bool, observed: object, expected: object, blocker_class: str, reason: str) -> FirewallProductRequirement:
    return FirewallProductRequirement(
        requirement=name,
        passed=bool(passed),
        observed=str(observed),
        expected=str(expected),
        blocker_class=blocker_class,
        reason=reason,
    )


def firewall_product_readiness_digest(payload: Mapping[str, object]) -> str:
    data = dict(payload)
    data.pop("report_digest", None)
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _demo_payloads() -> Dict[str, Dict[str, object]]:
    return {
        "delete_prod": {
            "request_id": "step98-delete-prod-demo",
            "action_name": "delete_resource",
            "candidate_action": "delete_resource",
            "action_type": "mutation",
            "target_resource": "prod_customer_table",
            "environment": "production",
            "risk_level": "critical",
            "reversibility": "irreversible",
            "requires_tool": True,
            "trusted_runtime_context": {"approval_present": False, "rollback_available": False},
            "untrusted_llm_context": {"llm_claimed_approval": True},
        },
        "external_email": {
            "request_id": "step98-external-email-demo",
            "action_name": "send_email_external",
            "candidate_action": "send_email_external",
            "action_type": "communication",
            "target_resource": "customer_export.csv",
            "environment": "staging",
            "risk_level": "medium",
            "requires_tool": True,
            "trusted_runtime_context": {"recipient_external": True, "data_classification": "customer", "approval_present": False},
        },
        "safe_internal": {
            "request_id": "step98-safe-internal-demo",
            "action_name": "send_email_internal",
            "candidate_action": "send_email_internal",
            "action_type": "communication",
            "target_resource": "weekly_summary.txt",
            "environment": "staging",
            "risk_level": "low",
            "requires_tool": True,
            "trusted_runtime_context": {"recipient_external": False, "approval_present": True, "rollback_available": True},
        },
    }


def run_agent_action_firewall_product_readiness(
    *,
    pearl_report: Mapping[str, object] | None = None,
    include_demo_results: bool = True,
) -> Dict[str, object]:
    policy = default_firewall_policy()
    pearl = dict(pearl_report or run_final_pearl_readiness_report(include_subreports=False))
    demos = _demo_payloads()
    demo_results = {
        key: evaluate_tool_call(payload, policy=policy, enable_tool_guard=True)
        for key, payload in demos.items()
    }

    expected_demo = {
        "delete_prod": HARD_BLOCK,
        "external_email": REVIEW,
        "safe_internal": PASS,
    }
    demo_passed = all(demo_results[key].get("firewall_decision") == expected for key, expected in expected_demo.items())
    audit_digest_present = all(bool(demo_results[key].get("decision_digest")) for key in expected_demo)
    toolguard_integrated = all("tool_guard_result" in demo_results[key] for key in ("external_email", "safe_internal"))

    requirements: Sequence[FirewallProductRequirement] = (
        _req(
            "step97_pearl_core_ready",
            bool(_truthy(pearl.get("final_pearl_readiness_allowed"))),
            pearl.get("final_pearl_readiness_allowed", 0),
            1,
            "pearl_core_not_ready",
            "The product firewall is premium only if the Step-97 causal/Pearl veto core is green.",
        ),
        _req(
            "policy_as_code_available",
            bool(policy.rules and policy.version),
            f"{policy.version};rules={len(policy.rules)}",
            "policy version with >=1 rule",
            "policy_as_code_missing",
            "The firewall must expose configurable YAML/dict policy rules, not only hard-coded runtime behavior.",
        ),
        _req(
            "fail_closed_policy_boundary",
            bool(policy.fail_closed_on_policy_error and policy.required_trusted_fields),
            f"fail_closed={int(policy.fail_closed_on_policy_error)};required={len(policy.required_trusted_fields)}",
            "fail_closed=1;required>=1",
            "firewall_not_fail_closed",
            "The product surface must fail closed when trusted runtime facts required by policy are missing.",
        ),
        _req(
            "pre_execution_demo_matrix_green",
            demo_passed,
            ";".join(f"{k}={demo_results[k].get('firewall_decision')}" for k in expected_demo),
            "delete_prod=HARD_BLOCK;external_email=REVIEW;safe_internal=PASS",
            "pre_execution_demo_matrix_not_green",
            "The firewall demo must show block/review/pass decisions before tool execution.",
        ),
        _req(
            "toolguard_integrated_for_nonblocked_cases",
            toolguard_integrated,
            f"external_email_has_tg={int(bool(demo_results['external_email'].get('tool_guard_result')))};safe_internal_has_tg={int(bool(demo_results['safe_internal'].get('tool_guard_result')))}",
            "1;1",
            "toolguard_integration_missing",
            "Non-preblocked actions must still pass through CausalGate ToolGuard/DecisionGate before execution.",
        ),
        _req(
            "audit_digest_present",
            audit_digest_present,
            f"digests={sum(1 for r in demo_results.values() if r.get('decision_digest'))}/{len(demo_results)}",
            "all demo decisions digest-bound",
            "audit_digest_missing",
            "Every product-level decision must carry an audit digest for evidence export.",
        ),
    )
    passed = sum(1 for req in requirements if req.passed)
    blockers = [req.blocker_class for req in requirements if not req.passed]
    report: Dict[str, object] = {
        "matrix_version": AGENT_ACTION_FIREWALL_PRODUCT_READINESS_VERSION,
        "scope": AGENT_ACTION_FIREWALL_PRODUCT_SCOPE,
        "product_name": "CausalGate Agent Action Firewall",
        "product_positioning": "pre_execution_ai_agent_firewall_with_causal_pearl_veto_and_audit_attestation",
        "firewall_product_readiness_allowed": int(passed == len(requirements)),
        "step97_final_pearl_readiness_allowed": int(_truthy(pearl.get("final_pearl_readiness_allowed"))),
        "policy_version": policy.version,
        "policy_digest": policy_digest(policy),
        "n_policy_rules": len(policy.rules),
        "fail_closed_on_policy_error": int(policy.fail_closed_on_policy_error),
        "required_trusted_fields": list(policy.required_trusted_fields),
        "demo_delete_prod_decision": demo_results["delete_prod"].get("firewall_decision"),
        "demo_external_email_decision": demo_results["external_email"].get("firewall_decision"),
        "demo_safe_internal_decision": demo_results["safe_internal"].get("firewall_decision"),
        "toolguard_integrated_for_nonblocked_cases": int(toolguard_integrated),
        "audit_digest_present": int(audit_digest_present),
        "n_requirements": len(requirements),
        "n_requirements_passed": passed,
        "n_blockers": len(blockers),
        "blocker_classes": "|".join(blockers),
        "requirements": [req.to_dict() for req in requirements],
    }
    if include_demo_results:
        report["demo_results"] = demo_results
    report["report_digest"] = firewall_product_readiness_digest(report)
    return report


def write_agent_action_firewall_product_readiness(path: str | Path = "out/agent_firewall_product_readiness_step98.json") -> Dict[str, object]:
    report = run_agent_action_firewall_product_readiness()
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return report


__all__ = [
    "AGENT_ACTION_FIREWALL_PRODUCT_READINESS_VERSION",
    "firewall_product_readiness_digest",
    "run_agent_action_firewall_product_readiness",
    "write_agent_action_firewall_product_readiness",
]
