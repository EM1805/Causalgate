from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from causalgate.agent_guard import ToolGuard
from causalgate.agent_guard.execution_policy import ASK_USER, BLOCK, EXECUTE, EXECUTE_WITH_WARNING
from causalgate.learning.audit_log import AuditLog
from causalgate.evidence import CausalEvidence
from causalgate.authority import score_causal_authority

from .policy import HARD_BLOCK, PASS, REVIEW, AgentFirewallPolicy, build_firewall_context, load_firewall_policy, policy_digest

ToolExecutor = Callable[[Dict[str, Any]], Any]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _stable_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(payload: object) -> str:
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _tool_guard_gate_decision(tool_guard_result: Mapping[str, Any]) -> str:
    decision_pkg = _as_dict(tool_guard_result.get("decision_package"))
    return _clean_str(decision_pkg.get("decision"), "abstain")


def _tool_guard_runtime_decision(tool_guard_result: Mapping[str, Any]) -> str:
    decision_pkg = _as_dict(tool_guard_result.get("decision_package"))
    return _clean_str(decision_pkg.get("runtime_decision"), "UNKNOWN")


def _finalize_decision(policy_decision: str, tool_guard_result: Mapping[str, Any]) -> tuple[str, str]:
    if policy_decision == HARD_BLOCK:
        return HARD_BLOCK, BLOCK
    if policy_decision == REVIEW:
        return REVIEW, ASK_USER

    tg = dict(tool_guard_result or {})
    # In policy-only/demo mode ToolGuard may be disabled.  A policy PASS should
    # remain a PASS rather than failing closed because there is no ToolGuard
    # execution_action to inspect.  Actual execution still only happens when the
    # caller passes execute=True and a tool executor.
    if not tg:
        return PASS, EXECUTE
    action = _clean_str(tg.get("execution_action"), BLOCK)
    if action == BLOCK:
        return HARD_BLOCK, BLOCK
    if action == ASK_USER:
        return REVIEW, ASK_USER
    if action == EXECUTE_WITH_WARNING:
        return REVIEW, EXECUTE_WITH_WARNING
    if action == EXECUTE:
        return PASS, EXECUTE
    return HARD_BLOCK, BLOCK


_DECISION_RANK = {PASS: 0, REVIEW: 1, HARD_BLOCK: 2}


def _strictest_decision(*decisions: str) -> str:
    current = PASS
    for decision in decisions:
        if _DECISION_RANK.get(decision, 1) > _DECISION_RANK.get(current, 1):
            current = decision
    return current


@dataclass
class AgentFirewallResult:
    """Product-level result for a pre-execution AI-agent tool-call check."""

    product: str = "CausalGate Agent Action Firewall"
    matrix_version: str = "agent_action_firewall_mvp_v1_step98"
    request_id: str = ""
    timestamp: str = field(default_factory=_utc_now_iso)
    tool_name: str = ""
    firewall_decision: str = REVIEW
    execution_action: str = ASK_USER
    executed: bool = False
    blocked: bool = True
    needs_approval: bool = True
    policy_evaluation: Dict[str, Any] = field(default_factory=dict)
    authority_evaluation: Dict[str, Any] = field(default_factory=dict)
    causal_evidence: Dict[str, Any] = field(default_factory=dict)
    tool_guard_result: Dict[str, Any] = field(default_factory=dict)
    audit_event: Dict[str, Any] = field(default_factory=dict)
    decision_digest: str = ""
    reason_codes: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def authority_score(self) -> int | None:
        value = self.authority_evaluation.get("authority_score")
        return int(value) if isinstance(value, (int, float)) else None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        from causalgate.reports import render_markdown_report
        return render_markdown_report(self)


class AgentActionFirewall:
    """Pre-execution firewall for AI-agent tool calls.

    This product layer combines YAML policy-as-code with CausalGate's existing
    ToolGuard/DecisionGate boundary.  Policy can fail closed before any tool is
    touched; allowed actions are still passed through ToolGuard before execution.
    """

    def __init__(
        self,
        *,
        policy: str | Path | Mapping[str, Any] | AgentFirewallPolicy | None = None,
        tool_guard: ToolGuard | None = None,
        enable_tool_guard: bool = True,
        audit_log_path: str | Path | None = None,
        **tool_guard_kwargs: Any,
    ) -> None:
        self.policy = load_firewall_policy(policy)
        self.tool_guard = tool_guard or ToolGuard(**tool_guard_kwargs)
        self.enable_tool_guard = enable_tool_guard
        self.audit_log_path = Path(audit_log_path) if audit_log_path else None

    def evaluate_tool_call(
        self,
        action_payload: Mapping[str, Any] | None,
        *,
        tool_name: str = "",
        tool_args: Mapping[str, Any] | None = None,
        trusted_runtime_context: Mapping[str, Any] | None = None,
        untrusted_llm_context: Mapping[str, Any] | None = None,
        causal_evidence: CausalEvidence | Mapping[str, Any] | str | Path | None = None,
        require_causal_evidence: bool = False,
        execute: bool = False,
        tool_executor: ToolExecutor | None = None,
    ) -> AgentFirewallResult:
        payload = dict(action_payload or {})
        resolved_tool_name = _clean_str(tool_name or payload.get("tool_name") or payload.get("action_name") or payload.get("candidate_action"))
        context = build_firewall_context(
            payload,
            tool_name=resolved_tool_name,
            tool_args=tool_args,
            trusted_runtime_context=trusted_runtime_context,
            untrusted_llm_context=untrusted_llm_context,
        )
        policy_eval = self.policy.evaluate(context)
        policy_decision = _clean_str(policy_eval.get("firewall_decision"), REVIEW)

        evidence_obj = CausalEvidence.coerce(causal_evidence)
        authority_eval: Dict[str, Any] = {}
        causal_evidence_payload: Dict[str, Any] = {}
        authority_decision = PASS
        if evidence_obj is not None or require_causal_evidence:
            evidence_obj = evidence_obj or CausalEvidence()
            authority = score_causal_authority(
                evidence_obj,
                risk_level=_clean_str(context.get("risk_level"), "unknown"),
                require_evidence=require_causal_evidence,
            )
            authority_eval = authority.to_dict()
            causal_evidence_payload = evidence_obj.to_dict()
            authority_decision = authority.authority_decision

        gated_policy_decision = _strictest_decision(policy_decision, authority_decision)
        if authority_eval:
            policy_eval = dict(policy_eval)
            policy_eval["causal_authority_applied"] = True
            policy_eval["pre_authority_firewall_decision"] = policy_decision
            policy_eval["firewall_decision"] = gated_policy_decision
        policy_decision = gated_policy_decision

        tool_guard_result: Dict[str, Any] = {}
        if policy_decision != HARD_BLOCK and self.enable_tool_guard:
            executor = tool_executor if execute and policy_decision == PASS else None
            tool_guard_result = self.tool_guard.guard_tool_call(
                payload,
                tool_executor=executor,
                tool_args=tool_args,
                tool_name=resolved_tool_name,
                trusted_runtime_context=trusted_runtime_context,
                untrusted_llm_context=untrusted_llm_context,
            ).to_dict()

        final_decision, execution_action = _finalize_decision(policy_decision, tool_guard_result)
        executed = bool(_as_dict(tool_guard_result).get("executed")) and final_decision == PASS
        blocked = final_decision == HARD_BLOCK
        needs_approval = final_decision == REVIEW
        request_id = _clean_str(payload.get("request_id") or _as_dict(payload.get("trusted_runtime_context")).get("request_id"))
        reason_codes = list(policy_eval.get("reason_codes", []) or [])
        if authority_eval:
            authority_code = f"CAUSAL_AUTHORITY_{_clean_str(authority_eval.get('authority_level'), 'UNKNOWN').upper()}"
            if authority_code not in reason_codes:
                reason_codes.append(authority_code)
        if tool_guard_result:
            reason_codes.extend([code for code in _as_dict(tool_guard_result.get("decision_package")).get("reason_codes", []) or [] if code not in reason_codes])

        audit_event = self._build_audit_event(
            request_id=request_id,
            tool_name=resolved_tool_name,
            context=context,
            policy_eval=policy_eval,
            tool_guard_result=tool_guard_result,
            authority_eval=authority_eval,
            final_decision=final_decision,
            execution_action=execution_action,
            executed=executed,
        )
        digest = _sha256({
            "matrix_version": "agent_action_firewall_mvp_v1_step98",
            "request_id": request_id,
            "tool_name": resolved_tool_name,
            "firewall_decision": final_decision,
            "execution_action": execution_action,
            "policy_eval": policy_eval,
            "authority_eval": authority_eval,
            "tool_guard_gate_decision": _tool_guard_gate_decision(tool_guard_result),
            "tool_guard_runtime_decision": _tool_guard_runtime_decision(tool_guard_result),
            "policy_digest": policy_digest(self.policy),
        })
        audit_event["decision_digest"] = digest
        audit_event["policy_digest"] = policy_digest(self.policy)

        summary = self._summary(final_decision, resolved_tool_name, policy_eval, tool_guard_result, authority_eval)
        result = AgentFirewallResult(
            request_id=request_id,
            tool_name=resolved_tool_name,
            firewall_decision=final_decision,
            execution_action=execution_action,
            executed=executed,
            blocked=blocked,
            needs_approval=needs_approval,
            policy_evaluation=policy_eval,
            authority_evaluation=authority_eval,
            causal_evidence=causal_evidence_payload,
            tool_guard_result=tool_guard_result,
            audit_event=audit_event,
            decision_digest=digest,
            reason_codes=reason_codes,
            summary=summary,
        )
        self._append_audit(result)
        return result

    def evaluate(
        self,
        *,
        action: str = "",
        tool_name: str = "",
        tool_args: Mapping[str, Any] | None = None,
        risk_level: str = "unknown",
        environment: str = "unknown",
        action_type: str = "unknown",
        target_resource: str = "",
        approval_present: bool = False,
        rollback_available: bool = False,
        requires_user_confirmation: bool = False,
        evidence_available: str = "unknown",
        evidence: CausalEvidence | Mapping[str, Any] | str | Path | None = None,
        require_causal_evidence: bool | None = None,
        treatment: str = "",
        outcome: str = "",
        scm_graph: Mapping[str, Any] | None = None,
        causal_query: Mapping[str, Any] | None = None,
        trusted_runtime_context: Mapping[str, Any] | None = None,
        untrusted_llm_context: Mapping[str, Any] | None = None,
        execute: bool = False,
        tool_executor: ToolExecutor | None = None,
        **extra: Any,
    ) -> AgentFirewallResult:
        """Evaluate one proposed AI-agent action with a product-friendly API.

        This is the public facade for the commercial/product direction:
        caller code supplies the proposed action plus trusted runtime facts, and
        CausalGate returns PASS, REVIEW, or HARD_BLOCK before any tool is run.

        Sensitive execution facts are placed in ``trusted_runtime_context`` so
        they cannot be overridden by untrusted LLM text.
        """

        resolved_tool_name = _clean_str(tool_name or action or extra.get("candidate_action"))
        trusted = {
            "environment": _clean_str(environment, "unknown"),
            "risk_level": _clean_str(risk_level, "unknown"),
            "action_type": _clean_str(action_type, "unknown"),
            "target_resource": _clean_str(target_resource),
            "approval_present": bool(approval_present),
            "rollback_available": bool(rollback_available),
            "requires_user_confirmation": bool(requires_user_confirmation),
            "evidence_available": _clean_str(evidence_available, "unknown"),
            "tool_name": resolved_tool_name,
        }
        trusted.update(_as_dict(trusted_runtime_context))

        payload: Dict[str, Any] = {
            "action_name": _clean_str(action or resolved_tool_name),
            "candidate_action": _clean_str(action or resolved_tool_name),
            "tool_name": resolved_tool_name,
            "action_type": trusted.get("action_type", "unknown"),
            "target_resource": trusted.get("target_resource", ""),
            "risk_level": trusted.get("risk_level", "unknown"),
            "environment": trusted.get("environment", "unknown"),
            "approval_present": trusted.get("approval_present", False),
            "rollback_available": trusted.get("rollback_available", False),
            "requires_user_confirmation": trusted.get("requires_user_confirmation", False),
            "evidence_available": trusted.get("evidence_available", "unknown"),
            "treatment": _clean_str(treatment),
            "outcome": _clean_str(outcome),
            "scm_graph": _as_dict(scm_graph),
            "causal_query": _as_dict(causal_query),
            "causal_evidence": CausalEvidence.coerce(evidence).to_dict() if evidence is not None else {},
            "trusted_runtime_context": trusted,
            "untrusted_llm_context": _as_dict(untrusted_llm_context),
        }
        payload.update({str(k): v for k, v in extra.items() if v is not None})

        should_require_evidence = bool(require_causal_evidence) if require_causal_evidence is not None else bool(treatment or outcome or evidence is not None)
        return self.evaluate_tool_call(
            payload,
            tool_name=resolved_tool_name,
            tool_args=tool_args,
            trusted_runtime_context=trusted,
            untrusted_llm_context=untrusted_llm_context,
            causal_evidence=evidence,
            require_causal_evidence=should_require_evidence,
            execute=execute,
            tool_executor=tool_executor,
        )

    def _build_audit_event(
        self,
        *,
        request_id: str,
        tool_name: str,
        context: Mapping[str, Any],
        policy_eval: Mapping[str, Any],
        tool_guard_result: Mapping[str, Any],
        authority_eval: Mapping[str, Any],
        final_decision: str,
        execution_action: str,
        executed: bool,
    ) -> Dict[str, Any]:
        return {
            "event_type": "agent_action_firewall",
            "matrix_version": "agent_action_firewall_mvp_v1_step98",
            "timestamp": _utc_now_iso(),
            "request_id": request_id,
            "tool_name": tool_name,
            "environment": context.get("environment", "unknown"),
            "target_resource": context.get("target_resource", ""),
            "firewall_decision": final_decision,
            "execution_action": execution_action,
            "executed": int(executed),
            "blocked": int(final_decision == HARD_BLOCK),
            "needs_approval": int(final_decision == REVIEW),
            "policy_version": policy_eval.get("policy_version"),
            "matched_rule_ids": list(policy_eval.get("matched_rule_ids", []) or []),
            "tool_guard_gate_decision": _tool_guard_gate_decision(tool_guard_result),
            "tool_guard_runtime_decision": _tool_guard_runtime_decision(tool_guard_result),
            "authority_score": authority_eval.get("authority_score"),
            "authority_level": authority_eval.get("authority_level"),
            "authority_decision": authority_eval.get("authority_decision"),
            "reason_codes": list(policy_eval.get("reason_codes", []) or []),
        }

    def _summary(self, final_decision: str, tool_name: str, policy_eval: Mapping[str, Any], tool_guard_result: Mapping[str, Any], authority_eval: Mapping[str, Any]) -> str:
        authority_text = ""
        if authority_eval:
            authority_text = f" Causal authority score: {authority_eval.get('authority_score')}/100 ({authority_eval.get('authority_level')})."
        if final_decision == HARD_BLOCK:
            return f"CausalGate blocked tool '{tool_name}' before execution." + authority_text
        if final_decision == REVIEW:
            return f"CausalGate routed tool '{tool_name}' to human/approval review before execution." + authority_text
        tg_status = _clean_str(tool_guard_result.get("status"), "permitted") if tool_guard_result else "permitted_by_policy"
        return f"CausalGate allowed tool '{tool_name}' after firewall policy, causal authority, and ToolGuard checks ({tg_status})." + authority_text

    def _append_audit(self, result: AgentFirewallResult) -> None:
        if not self.audit_log_path:
            return
        AuditLog(self.audit_log_path).append_event(result.audit_event)


def evaluate_tool_call(
    action_payload: Mapping[str, Any] | None,
    *,
    policy: str | Path | Mapping[str, Any] | AgentFirewallPolicy | None = None,
    tool_name: str = "",
    tool_args: Mapping[str, Any] | None = None,
    trusted_runtime_context: Mapping[str, Any] | None = None,
    untrusted_llm_context: Mapping[str, Any] | None = None,
    causal_evidence: CausalEvidence | Mapping[str, Any] | str | Path | None = None,
    require_causal_evidence: bool = False,
    execute: bool = False,
    tool_executor: ToolExecutor | None = None,
    enable_tool_guard: bool = True,
    audit_log_path: str | Path | None = None,
    **tool_guard_kwargs: Any,
) -> Dict[str, Any]:
    return AgentActionFirewall(
        policy=policy,
        enable_tool_guard=enable_tool_guard,
        audit_log_path=audit_log_path,
        **tool_guard_kwargs,
    ).evaluate_tool_call(
        action_payload,
        tool_name=tool_name,
        tool_args=tool_args,
        trusted_runtime_context=trusted_runtime_context,
        untrusted_llm_context=untrusted_llm_context,
        causal_evidence=causal_evidence,
        require_causal_evidence=require_causal_evidence,
        execute=execute,
        tool_executor=tool_executor,
    ).to_dict()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate an AI-agent tool call through the CausalGate Agent Action Firewall.")
    parser.add_argument("--input", required=True, help="Path to ActionPackage/tool-call JSON.")
    parser.add_argument("--policy", default="", help="Optional firewall policy YAML path.")
    parser.add_argument("--tool-name", default="")
    parser.add_argument("--tool-args", default="", help="Optional JSON file with tool arguments.")
    parser.add_argument("--out", default="out/agent_action_firewall_result.json")
    parser.add_argument("--audit-log", default="")
    parser.add_argument("--disable-tool-guard", action="store_true", help="Use policy-only mode for dry-run/demo.")
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    tool_args = json.loads(Path(args.tool_args).read_text(encoding="utf-8")) if args.tool_args else {}
    result = evaluate_tool_call(
        payload,
        policy=args.policy or None,
        tool_name=args.tool_name,
        tool_args=tool_args,
        enable_tool_guard=not args.disable_tool_guard,
        audit_log_path=args.audit_log or None,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "out": str(out_path),
        "firewall_decision": result.get("firewall_decision"),
        "execution_action": result.get("execution_action"),
        "executed": result.get("executed"),
        "blocked": result.get("blocked"),
        "tool_name": result.get("tool_name"),
        "decision_digest": result.get("decision_digest"),
    }, indent=2))
    return 0


__all__ = ["AgentActionFirewall", "AgentFirewallResult", "evaluate_tool_call"]


if __name__ == "__main__":
    raise SystemExit(main())
