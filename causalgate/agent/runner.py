from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from causalgate.action_recommender import CausalActionRecommender
from causalgate.agent_guard import ToolGuard
from causalgate.llm_interface import LLMResponse, llm_response_to_brain_payload
from causalgate.operational_brain import OperationalBrain

from .evidence_reader import AgentEvidenceReader
from .feedback_loop import AgentFeedbackLoop
from .modes import infer_agent_mode
from .registry_policy import AgentRegistryPolicy
from .planner import LLMActionPlanner
from .tool_registry import ToolRegistry, ToolSpec, build_default_tool_registry, build_sandbox_tool_registry
from .types import AgentRunResult, as_dict, clean_str, is_communication_action


def _merge_dicts(*values: Mapping[str, Any] | None) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for value in values:
        if isinstance(value, Mapping):
            merged.update(dict(value))
    return merged


def _to_llm_response_dict(response: LLMResponse | Mapping[str, Any]) -> Dict[str, Any]:
    if isinstance(response, LLMResponse):
        return response.to_dict()
    return dict(response or {}) if isinstance(response, Mapping) else {}


def _candidate_name(candidate: Any) -> str:
    if isinstance(candidate, Mapping):
        return clean_str(
            candidate.get("action_name")
            or candidate.get("candidate_action")
            or candidate.get("selected_action")
            or candidate.get("name")
        )
    return clean_str(candidate)


def _find_candidate(payload: Mapping[str, Any], action_name: str) -> Dict[str, Any]:
    action_name = clean_str(action_name)
    for candidate in list(payload.get("candidate_actions", []) or []) + list(payload.get("actions", []) or []):
        if isinstance(candidate, Mapping) and _candidate_name(candidate) == action_name:
            return dict(candidate)
        if isinstance(candidate, str) and candidate == action_name:
            return {"action_name": candidate, "candidate_action": candidate}
    return {"action_name": action_name, "candidate_action": action_name}


class CausalGateAgent:
    """End-to-end online agent runtime for CausalGate.

    This class is the missing orchestration layer between an LLM planner and
    CausalGate's causal safety runtime:

        user -> planner -> OperationalBrain -> ToolGuard -> registered tool

    The planner proposes candidate actions only. Tool execution is fail-closed:
    an action must be selected by OperationalBrain, must not be a communication
    action, must be registered in ToolRegistry, and must pass ToolGuard.
    """

    def __init__(
        self,
        *,
        planner: Any | None = None,
        brain: OperationalBrain | None = None,
        tool_guard: ToolGuard | None = None,
        tool_registry: ToolRegistry | None = None,
        recommender: CausalActionRecommender | None = None,
        evidence_reader: AgentEvidenceReader | None = None,
        evidence_output_dir: str | Path = "out",
        enable_evidence_reader: bool = True,
        action_registry_path: str | Path = "action_registry.yaml",
        default_agent_mode: str = "general_agent",
        registry_policy: AgentRegistryPolicy | None = None,
        audit_log_path: str | Path | None = None,
        enable_sandbox_tools: bool = False,
        sandbox_root_dir: str | Path = ".",
        sandbox_out_dir: str | Path = "out",
        **gate_kwargs: Any,
    ) -> None:
        self.planner = planner or LLMActionPlanner()
        self.brain = brain or OperationalBrain(**gate_kwargs)
        self.tool_guard = tool_guard or ToolGuard(audit_log_path=audit_log_path, **gate_kwargs)
        if tool_registry is not None:
            self.tool_registry = tool_registry
        elif enable_sandbox_tools:
            self.tool_registry = build_sandbox_tool_registry(root_dir=sandbox_root_dir, out_dir=sandbox_out_dir)
        else:
            self.tool_registry = build_default_tool_registry()
        self.recommender = recommender or CausalActionRecommender()
        self.evidence_reader = evidence_reader or (AgentEvidenceReader(output_dir=evidence_output_dir) if enable_evidence_reader else None)
        self.registry_policy = registry_policy or AgentRegistryPolicy(
            action_registry_path=action_registry_path,
            default_agent_mode=default_agent_mode,
        )
        self.default_agent_mode = default_agent_mode
        self.audit_log_path = Path(audit_log_path) if audit_log_path else None

    def register_tool(self, tool: ToolSpec | Mapping[str, Any], executor: Any | None = None) -> ToolSpec:
        return self.tool_registry.register(tool, executor=executor)

    def build_brain_payload(
        self,
        *,
        user_message: str,
        llm_response: LLMResponse | Mapping[str, Any],
        trusted_runtime_context: Mapping[str, Any] | None = None,
        untrusted_llm_context: Mapping[str, Any] | None = None,
        candidate_actions: list[Mapping[str, Any]] | None = None,
        agent_mode: str | None = None,
    ) -> Dict[str, Any]:
        response_dict = _to_llm_response_dict(llm_response)
        payload = llm_response_to_brain_payload(response_dict)
        payload["user_message"] = clean_str(payload.get("user_message") or user_message)
        if candidate_actions is not None:
            payload["candidate_actions"] = list(candidate_actions or [])
        resolved_mode = self.registry_policy.resolve_mode(
            requested_mode=agent_mode,
            candidate=(payload.get("candidate_actions") or [{}])[0] if payload.get("candidate_actions") else None,
            trusted_runtime_context=trusted_runtime_context,
        )
        payload["agent_mode"] = resolved_mode

        # Split-context contract: trusted facts stay top-level and are the only
        # source that may authorize execution. LLM output remains untrusted.
        trusted = _merge_dicts(trusted_runtime_context)
        untrusted = _merge_dicts(
            untrusted_llm_context,
            {
                "llm_context": dict(response_dict.get("context", {}) or {}),
                "llm_raw_model_output": dict(response_dict.get("raw_model_output", {}) or {}),
            },
        )
        if trusted:
            payload["trusted_runtime_context"] = trusted
        if untrusted:
            payload["untrusted_llm_context"] = untrusted
        return payload

    def _selected_action_payload(
        self,
        *,
        brain_payload: Mapping[str, Any],
        selected: Mapping[str, Any],
        trusted_runtime_context: Mapping[str, Any] | None = None,
        untrusted_llm_context: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        action_name = clean_str(selected.get("selected_action") or selected.get("candidate_action"))
        candidate = _find_candidate(brain_payload, action_name)
        payload = dict(candidate)
        payload.setdefault("action_name", action_name)
        payload.setdefault("candidate_action", action_name)
        payload["user_message"] = clean_str(brain_payload.get("user_message"))
        payload["source"] = clean_str(brain_payload.get("source"), "causalgate_agent")
        payload["agent_mode"] = clean_str(payload.get("agent_mode") or brain_payload.get("agent_mode"), self.default_agent_mode)

        if "context" in brain_payload and "context" not in payload:
            payload["context"] = dict(brain_payload.get("context", {}) or {})

        payload["trusted_runtime_context"] = _merge_dicts(
            brain_payload.get("trusted_runtime_context"),
            trusted_runtime_context,
            as_dict(candidate.get("trusted_runtime_context") or candidate.get("trusted_context")),
        )
        payload["untrusted_llm_context"] = _merge_dicts(
            brain_payload.get("untrusted_llm_context"),
            untrusted_llm_context,
            as_dict(candidate.get("untrusted_llm_context") or candidate.get("llm_context")),
        )
        return payload

    def run(
        self,
        user_message: str,
        *,
        trusted_runtime_context: Mapping[str, Any] | None = None,
        untrusted_llm_context: Mapping[str, Any] | None = None,
        planner_context: Mapping[str, Any] | None = None,
        candidate_actions: list[Mapping[str, Any]] | None = None,
        tool_args: Mapping[str, Any] | None = None,
        execute_tools: bool = True,
        agent_mode: str | None = None,
    ) -> AgentRunResult:
        if candidate_actions is None:
            llm_response = self.planner.propose_actions(
                user_message,
                trusted_runtime_context=trusted_runtime_context,
                untrusted_llm_context=untrusted_llm_context,
                planner_context=planner_context,
            )
        else:
            llm_response = LLMResponse(
                user_message=user_message,
                candidate_actions=list(candidate_actions or []),
                context=dict(planner_context or {}),
                raw_model_output={"source": "caller_supplied_candidate_actions"},
                source="caller_supplied_candidate_actions",
            )

        brain_payload = self.build_brain_payload(
            user_message=user_message,
            llm_response=llm_response,
            trusted_runtime_context=trusted_runtime_context,
            untrusted_llm_context=untrusted_llm_context,
            candidate_actions=candidate_actions,
            agent_mode=agent_mode,
        )
        brain_payload = self._attach_registry_policy_to_brain_payload(brain_payload)
        brain_payload = self._attach_evidence_to_brain_payload(brain_payload)
        brain_result = self.brain.run(brain_payload).to_dict()
        llm_response_dict = _to_llm_response_dict(llm_response)
        brain_result["llm_response"] = llm_response_dict

        selected = as_dict(brain_result.get("selected"))
        selected_action = clean_str(selected.get("selected_action") or selected.get("candidate_action"))
        decision = clean_str(selected.get("decision"), "abstain")
        selected_payload = self._selected_action_payload(
            brain_payload=brain_payload,
            selected=selected,
            trusted_runtime_context=trusted_runtime_context,
            untrusted_llm_context=untrusted_llm_context,
        )
        evidence_bundle = self._evidence_bundle_for_selected(selected_payload)
        action_type = clean_str(selected_payload.get("action_type"))
        recommendation = self._build_recommendation(
            action_payload=selected_payload,
            selected=selected,
        )
        agent_mode_resolved = clean_str(selected_payload.get("agent_mode") or brain_payload.get("agent_mode"), self.default_agent_mode)
        tool_probe = self.tool_registry.get(selected_action)
        registry_policy_result = self.registry_policy.validate_selected_action(
            selected_payload,
            agent_mode=agent_mode_resolved,
            trusted_runtime_context=trusted_runtime_context,
            tool_registered=tool_probe is not None,
            execution_requested=bool(execute_tools),
        ).to_dict()

        if is_communication_action(selected_action, action_type):
            result = AgentRunResult(
                status="respond",
                response_type="communication",
                user_message=user_message,
                selected_action=selected_action,
                decision=decision,
                executed=False,
                blocked=decision in {"veto", "abstain"},
                needs_user_confirmation=decision == "ask_clarification",
                llm_response=llm_response_dict,
                brain_result=brain_result,
                recommendation=recommendation,
                recommended_action=as_dict(recommendation.get("recommended_action")),
                recommendation_summary=clean_str(recommendation.get("recommendation_summary")),
                recommendation_requires_recheck=True,
                evidence_bundle=evidence_bundle,
                evidence_tier=clean_str(evidence_bundle.get("evidence_tier"), "none"),
                evidence_warnings=list(evidence_bundle.get("evidence_warnings") or []),
                usable_for_autonomous_action=bool(evidence_bundle.get("usable_for_autonomous_action")),
                agent_mode=agent_mode_resolved,
                registry_policy_result=registry_policy_result,
                action_registry_registered=bool(registry_policy_result.get("action_registered")),
                tool_registry_registered=bool(registry_policy_result.get("tool_registered")),
                notes=[
                    "Selected action is communicative; ToolGuard was not invoked.",
                    "No external tool was executed.",
                ],
            )
            result.audit_event = self._append_agent_audit(result)
            return result

        if registry_policy_result.get("allowed") is False:
            result = AgentRunResult(
                status=clean_str(registry_policy_result.get("status"), "registry_policy_blocked"),
                response_type="tool_call",
                user_message=user_message,
                selected_action=selected_action,
                decision=clean_str(registry_policy_result.get("decision"), "ask_clarification"),
                executed=False,
                blocked=True,
                needs_user_confirmation=bool(registry_policy_result.get("needs_user_confirmation", True)),
                llm_response=llm_response_dict,
                brain_result=brain_result,
                tool_guard_result={"status": "not_invoked", "reason": "AgentRegistryPolicy blocked execution before ToolGuard."},
                recommendation=recommendation,
                recommended_action=as_dict(recommendation.get("recommended_action")),
                recommendation_summary=clean_str(recommendation.get("recommendation_summary")),
                recommendation_requires_recheck=True,
                evidence_bundle=evidence_bundle,
                evidence_tier=clean_str(evidence_bundle.get("evidence_tier"), "none"),
                evidence_warnings=list(evidence_bundle.get("evidence_warnings") or []),
                usable_for_autonomous_action=bool(evidence_bundle.get("usable_for_autonomous_action")),
                agent_mode=agent_mode_resolved,
                registry_policy_result=registry_policy_result,
                action_registry_registered=bool(registry_policy_result.get("action_registered")),
                tool_registry_registered=bool(registry_policy_result.get("tool_registered")),
                notes=[
                    clean_str(registry_policy_result.get("reason"), "Registry policy blocked execution."),
                    "No external tool was executed.",
                ],
            )
            result.audit_event = self._append_agent_audit(result)
            return result

        evidence_gate = self._evidence_execution_gate(evidence_bundle, decision)
        if evidence_gate.get("block"):
            result = AgentRunResult(
                status=clean_str(evidence_gate.get("status"), "evidence_review_required"),
                response_type="tool_call",
                user_message=user_message,
                selected_action=selected_action,
                decision=clean_str(evidence_gate.get("decision"), "ask_clarification"),
                executed=False,
                blocked=True,
                needs_user_confirmation=bool(evidence_gate.get("needs_user_confirmation", True)),
                llm_response=llm_response_dict,
                brain_result=brain_result,
                tool_guard_result={"status": "not_invoked", "reason": "AgentEvidenceReader blocked direct execution before ToolGuard."},
                recommendation=recommendation,
                recommended_action=as_dict(recommendation.get("recommended_action")),
                recommendation_summary=clean_str(recommendation.get("recommendation_summary")),
                recommendation_requires_recheck=True,
                evidence_bundle=evidence_bundle,
                evidence_tier=clean_str(evidence_bundle.get("evidence_tier"), "none"),
                evidence_warnings=list(evidence_bundle.get("evidence_warnings") or []),
                usable_for_autonomous_action=bool(evidence_bundle.get("usable_for_autonomous_action")),
                agent_mode=agent_mode_resolved,
                registry_policy_result=registry_policy_result,
                action_registry_registered=bool(registry_policy_result.get("action_registered")),
                tool_registry_registered=bool(registry_policy_result.get("tool_registered")),
                notes=[
                    clean_str(evidence_gate.get("reason"), "Structured causal evidence requires review before execution."),
                    "No external tool was executed.",
                ],
            )
            result.audit_event = self._append_agent_audit(result)
            return result

        tool = tool_probe
        if tool is None:
            guard_result = self.tool_guard.guard_tool_call(
                selected_payload,
                tool_executor=None,
                tool_args=tool_args,
                tool_name=selected_action,
                trusted_runtime_context=trusted_runtime_context,
                untrusted_llm_context=untrusted_llm_context,
            ).to_dict()
            result = AgentRunResult(
                status="tool_not_registered",
                response_type="tool_call",
                user_message=user_message,
                selected_action=selected_action,
                decision=decision,
                executed=False,
                blocked=True,
                needs_user_confirmation=bool(guard_result.get("needs_user_confirmation")),
                llm_response=llm_response_dict,
                brain_result=brain_result,
                tool_guard_result=guard_result,
                recommendation=recommendation,
                recommended_action=as_dict(recommendation.get("recommended_action")),
                recommendation_summary=clean_str(recommendation.get("recommendation_summary")),
                recommendation_requires_recheck=True,
                evidence_bundle=evidence_bundle,
                evidence_tier=clean_str(evidence_bundle.get("evidence_tier"), "none"),
                evidence_warnings=list(evidence_bundle.get("evidence_warnings") or []),
                usable_for_autonomous_action=bool(evidence_bundle.get("usable_for_autonomous_action")),
                agent_mode=agent_mode_resolved,
                registry_policy_result=registry_policy_result,
                action_registry_registered=bool(registry_policy_result.get("action_registered")),
                tool_registry_registered=bool(registry_policy_result.get("tool_registered")),
                notes=[
                    f"Tool '{selected_action}' is not registered in ToolRegistry.",
                    "Fail-closed: no tool was executed.",
                ],
            )
            result.audit_event = self._append_agent_audit(result)
            return result

        executor = tool.execute if execute_tools else None
        merged_tool_args = _merge_dicts(tool.metadata.get("default_args") if isinstance(tool.metadata, Mapping) else {}, tool_args)
        schema_errors = tool.validate_args(merged_tool_args) if execute_tools and hasattr(tool, "validate_args") else []
        if schema_errors:
            result = AgentRunResult(
                status="tool_schema_invalid",
                response_type="tool_call",
                user_message=user_message,
                selected_action=selected_action,
                decision="ask_clarification",
                executed=False,
                blocked=True,
                needs_user_confirmation=True,
                llm_response=llm_response_dict,
                brain_result=brain_result,
                tool_guard_result={"status": "not_invoked", "reason": "Tool input schema validation failed.", "schema_errors": schema_errors},
                recommendation=recommendation,
                recommended_action=as_dict(recommendation.get("recommended_action")),
                recommendation_summary=clean_str(recommendation.get("recommendation_summary")),
                recommendation_requires_recheck=True,
                evidence_bundle=evidence_bundle,
                evidence_tier=clean_str(evidence_bundle.get("evidence_tier"), "none"),
                evidence_warnings=list(evidence_bundle.get("evidence_warnings") or []),
                usable_for_autonomous_action=bool(evidence_bundle.get("usable_for_autonomous_action")),
                agent_mode=agent_mode_resolved,
                registry_policy_result=registry_policy_result,
                action_registry_registered=bool(registry_policy_result.get("action_registered")),
                tool_registry_registered=bool(registry_policy_result.get("tool_registered")),
                notes=[
                    "Tool input schema validation failed before ToolGuard/executor.",
                    *schema_errors,
                ],
            )
            result.audit_event = self._append_agent_audit(result)
            return result
        guard_result = self.tool_guard.guard_tool_call(
            selected_payload,
            tool_executor=executor,
            tool_args=merged_tool_args,
            tool_name=selected_action,
            trusted_runtime_context=trusted_runtime_context,
            untrusted_llm_context=untrusted_llm_context,
        ).to_dict()

        result = AgentRunResult(
            status=clean_str(guard_result.get("status"), "tool_guard_result"),
            response_type="tool_call",
            user_message=user_message,
            selected_action=selected_action,
            decision=clean_str(as_dict(guard_result.get("decision_package")).get("decision"), decision),
            executed=bool(guard_result.get("executed")),
            blocked=bool(guard_result.get("blocked")),
            needs_user_confirmation=bool(guard_result.get("needs_user_confirmation")),
            llm_response=llm_response_dict,
            brain_result=brain_result,
            tool_guard_result=guard_result,
            tool_result=guard_result.get("tool_result"),
            recommendation=recommendation,
            recommended_action=as_dict(recommendation.get("recommended_action")),
            recommendation_summary=clean_str(recommendation.get("recommendation_summary")),
            recommendation_requires_recheck=True,
            evidence_bundle=evidence_bundle,
            evidence_tier=clean_str(evidence_bundle.get("evidence_tier"), "none"),
            evidence_warnings=list(evidence_bundle.get("evidence_warnings") or []),
            usable_for_autonomous_action=bool(evidence_bundle.get("usable_for_autonomous_action")),
            agent_mode=agent_mode_resolved,
            registry_policy_result=registry_policy_result,
            action_registry_registered=bool(registry_policy_result.get("action_registered")),
            tool_registry_registered=bool(registry_policy_result.get("tool_registered")),
            notes=["ToolGuard was invoked before any tool execution."],
        )
        result.audit_event = self._append_agent_audit(result)
        return result


    def _evidence_execution_gate(self, evidence_bundle: Mapping[str, Any], current_decision: str) -> Dict[str, Any]:
        """Conservative runtime guard for structured evidence constraints.

        This does not replace DecisionGate. It only prevents direct tool
        execution when an offline causal contract or evidence warning says the
        row is recommendation-only, requires review, or forbids autonomous use.
        Missing evidence alone does not block low-risk utility tools here; the
        risk policy remains responsible for evidence-by-risk escalation.
        """

        bundle = as_dict(evidence_bundle)
        if not bundle:
            return {"block": False}
        hints = as_dict(bundle.get("decision_hints"))
        warnings = list(bundle.get("evidence_warnings") or [])
        ceiling = clean_str(hints.get("decision_ceiling"))
        autonomous = clean_str(hints.get("autonomous_execution"))
        requires_review = bool(hints.get("requires_review"))
        hard = current_decision in {"veto", "abstain"}

        if autonomous in {"forbidden_by_contract", "recommendation_only", "discovery_hypothesis_only"} or requires_review:
            return {
                "block": True,
                "status": "discovery_review_required" if autonomous == "discovery_hypothesis_only" else "evidence_review_required",
                "decision": "ask_clarification" if not hard else current_decision,
                "needs_user_confirmation": True,
                "reason": "Discovery-only or contract-limited causal evidence does not permit autonomous execution; route to review or use a proposal-only recommendation.",
            }
        if ceiling in {"veto", "abstain"}:
            return {
                "block": True,
                "status": "evidence_execution_blocked",
                "decision": ceiling,
                "needs_user_confirmation": ceiling != "veto",
                "reason": "AgentEvidenceReader found structured evidence that sets a stricter decision ceiling.",
            }
        if ceiling == "ask_clarification":
            return {
                "block": True,
                "status": "evidence_clarification_required",
                "decision": "ask_clarification",
                "needs_user_confirmation": True,
                "reason": "Structured causal evidence requires clarification or human review before execution.",
            }
        if any("failed" in str(w).lower() or "fragile" in str(w).lower() for w in warnings):
            return {
                "block": True,
                "status": "evidence_fragility_blocked",
                "decision": "abstain" if current_decision == "allow" else current_decision,
                "needs_user_confirmation": True,
                "reason": "Structured causal evidence contains fragile/failed diagnostics; do not execute directly.",
            }
        return {"block": False}



    def _attach_registry_policy_to_brain_payload(self, brain_payload: Mapping[str, Any]) -> Dict[str, Any]:
        """Attach action-registry/mode metadata to candidate actions.

        The action registry defines what may be proposed. The tool registry
        later defines what may execute. This enrichment gives DecisionGate,
        EvidenceReader and audit logs the same stable policy facts.
        """

        payload = dict(brain_payload or {})
        candidates = list(payload.get("candidate_actions", []) or [])
        if not candidates:
            return payload

        mode = clean_str(payload.get("agent_mode"), self.default_agent_mode)
        trusted = as_dict(payload.get("trusted_runtime_context"))
        enriched: list[Any] = []
        for candidate in candidates:
            if isinstance(candidate, Mapping):
                enriched.append(
                    self.registry_policy.enrich_candidate(
                        candidate,
                        agent_mode=mode,
                        trusted_runtime_context=trusted,
                    )
                )
            else:
                enriched.append(
                    self.registry_policy.enrich_candidate(
                        {"action_name": clean_str(candidate), "candidate_action": clean_str(candidate)},
                        agent_mode=mode,
                        trusted_runtime_context=trusted,
                    )
                )
        payload["candidate_actions"] = enriched
        return payload

    def _attach_evidence_to_brain_payload(self, brain_payload: Mapping[str, Any]) -> Dict[str, Any]:
        """Attach structured offline causal evidence to each candidate action.

        The evidence is attached before OperationalBrain/DecisionGate so the
        gate may consume structured estimation fields. It is still conservative:
        it never creates approvals, never executes tools, and remains visible in
        params/context for auditability.
        """

        payload = dict(brain_payload or {})
        if self.evidence_reader is None:
            return payload

        enriched: list[Any] = []
        candidates = list(payload.get("candidate_actions", []) or [])
        if not candidates:
            return payload

        base = dict(payload)
        base.pop("candidate_actions", None)
        for candidate in candidates:
            if isinstance(candidate, Mapping):
                candidate_payload = dict(base)
                candidate_payload.update(dict(candidate))
                try:
                    enriched.append(self.evidence_reader.enrich_candidate(candidate_payload))
                except Exception as exc:  # fail-safe: evidence can disappear, gates remain intact.
                    fallback = dict(candidate)
                    params = as_dict(fallback.get("params"))
                    params["agent_evidence_error"] = f"{exc.__class__.__name__}: {exc}"
                    fallback["params"] = params
                    enriched.append(fallback)
            else:
                candidate_payload = dict(base)
                candidate_payload.update({"action_name": clean_str(candidate), "candidate_action": clean_str(candidate)})
                try:
                    enriched.append(self.evidence_reader.enrich_candidate(candidate_payload))
                except Exception:
                    enriched.append(candidate)
        payload["candidate_actions"] = enriched
        return payload

    def _evidence_bundle_for_selected(self, selected_payload: Mapping[str, Any]) -> Dict[str, Any]:
        params = as_dict(selected_payload.get("params"))
        embedded = as_dict(params.get("agent_evidence_bundle"))
        if embedded:
            return embedded
        if self.evidence_reader is None:
            return {}
        try:
            bundle = self.evidence_reader.read(selected_payload)
            return bundle.to_dict() if hasattr(bundle, "to_dict") else dict(bundle or {})
        except Exception as exc:
            return {
                "evidence_tier": "none",
                "evidence_score": 0.0,
                "evidence_warnings": [f"AgentEvidenceReader failed safely: {exc.__class__.__name__}: {exc}"],
                "usable_for_autonomous_action": False,
                "generated_by": "causalgate.agent.evidence_reader",
            }


    def _build_recommendation(
        self,
        *,
        action_payload: Mapping[str, Any],
        selected: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Generate a proposal-only recommendation for the selected action.

        This is intentionally post-decision: the recommender receives the
        DecisionPackage-shaped selected mapping and may suggest a safer
        alternative. The alternative is never executed in this turn. It is an
        agent-facing candidate that must be re-checked by DecisionGate and
        ToolGuard before any side effect.
        """

        try:
            package = self.recommender.recommend(action_payload, selected)
            data = package.to_dict() if hasattr(package, "to_dict") else dict(package or {})
        except Exception as exc:  # defensive fail-open for recommendation only; execution gates stay intact.
            data = {
                "original_action": clean_str(selected.get("selected_action") or selected.get("candidate_action")),
                "decision": clean_str(selected.get("decision"), "abstain"),
                "recommended_action": {},
                "recommended_actions": [],
                "recommendation_summary": "Recommendation generation failed; keep the original gate decision.",
                "safety_constraints": ["decision_gate_required", "tool_guard_required"],
                "execution_status": "recommendation_error",
                "generated_by": "causalgate.action_recommender",
                "notes": [f"recommender_error: {exc.__class__.__name__}: {exc}"],
                "causal_inputs": {},
            }

        data.setdefault("recommended_action", {})
        data.setdefault("recommended_actions", [])
        data.setdefault("recommendation_summary", "")
        data.setdefault("safety_constraints", [])
        data.setdefault("execution_status", "no_recommendation")
        data["recommendation_requires_recheck"] = True
        data["may_execute_directly"] = False
        data.setdefault("notes", [])
        data["notes"] = list(data.get("notes") or []) + [
            "AgentRunner attaches recommendations as proposal-only outputs.",
            "Recommended actions are not auto-executed in the same turn.",
        ]
        return data

    def _append_agent_audit(self, result: AgentRunResult) -> Dict[str, Any]:
        if not self.audit_log_path:
            return {}
        return AgentFeedbackLoop(self.audit_log_path).append_agent_decision(result.to_dict())


def run_agent(
    user_message: str,
    *,
    trusted_runtime_context: Mapping[str, Any] | None = None,
    untrusted_llm_context: Mapping[str, Any] | None = None,
    planner_context: Mapping[str, Any] | None = None,
    candidate_actions: list[Mapping[str, Any]] | None = None,
    tool_args: Mapping[str, Any] | None = None,
    tool_registry: ToolRegistry | None = None,
    recommender: CausalActionRecommender | None = None,
    evidence_reader: AgentEvidenceReader | None = None,
    evidence_output_dir: str | Path = "out",
    enable_evidence_reader: bool = True,
    execute_tools: bool = True,
    agent_mode: str | None = None,
    action_registry_path: str | Path = "action_registry.yaml",
    default_agent_mode: str = "general_agent",
    audit_log_path: str | Path | None = None,
    **gate_kwargs: Any,
) -> Dict[str, Any]:
    agent = CausalGateAgent(
        tool_registry=tool_registry,
        recommender=recommender,
        evidence_reader=evidence_reader,
        evidence_output_dir=evidence_output_dir,
        enable_evidence_reader=enable_evidence_reader,
        action_registry_path=action_registry_path,
        default_agent_mode=default_agent_mode,
        audit_log_path=audit_log_path,
        **gate_kwargs,
    )
    return agent.run(
        user_message,
        trusted_runtime_context=trusted_runtime_context,
        untrusted_llm_context=untrusted_llm_context,
        planner_context=planner_context,
        candidate_actions=candidate_actions,
        tool_args=tool_args,
        execute_tools=execute_tools,
        agent_mode=agent_mode,
    ).to_dict()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run one CausalGate AI-agent turn.")
    parser.add_argument("--message", default="", help="User message to plan/evaluate.")
    parser.add_argument("--input", default="", help="Optional JSON with user_message, contexts, candidate_actions and tool_args.")
    parser.add_argument("--out", default="out/agent_run_result.json")
    parser.add_argument("--audit-log", default="")
    parser.add_argument("--evidence-out-dir", default="out", help="Directory containing structured causal outputs for AgentEvidenceReader.")
    parser.add_argument("--agent-mode", default="", help="Agent mode: general_agent, code_agent, ops_agent, finance_trading_agent.")
    parser.add_argument("--action-registry", default="action_registry.yaml", help="Path to action_registry.yaml for registry-policy validation.")
    parser.add_argument("--disable-evidence-reader", action="store_true", help="Do not read offline causal output evidence for this run.")
    parser.add_argument("--no-execute", action="store_true", help="Evaluate only; do not execute registered tools.")
    args = parser.parse_args(argv)

    payload: Dict[str, Any] = {}
    if args.input:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    user_message = clean_str(payload.get("user_message") or args.message)

    result = run_agent(
        user_message,
        trusted_runtime_context=as_dict(payload.get("trusted_runtime_context") or payload.get("trusted_context")),
        untrusted_llm_context=as_dict(payload.get("untrusted_llm_context") or payload.get("llm_context")),
        planner_context=as_dict(payload.get("planner_context")),
        candidate_actions=payload.get("candidate_actions"),
        tool_args=as_dict(payload.get("tool_args")),
        evidence_output_dir=payload.get("evidence_output_dir") or args.evidence_out_dir,
        enable_evidence_reader=not bool(payload.get("disable_evidence_reader") or args.disable_evidence_reader),
        execute_tools=not args.no_execute,
        agent_mode=payload.get("agent_mode") or args.agent_mode or None,
        action_registry_path=payload.get("action_registry_path") or args.action_registry,
        audit_log_path=args.audit_log or None,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({
        "status": result.get("status"),
        "out": str(out_path),
        "selected_action": result.get("selected_action"),
        "decision": result.get("decision"),
        "executed": result.get("executed"),
        "blocked": result.get("blocked"),
        "recommended_action": (result.get("recommended_action") or {}).get("action_name"),
        "evidence_tier": result.get("evidence_tier"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
