from __future__ import annotations

"""Apps-SDK-ready tool schema metadata for CausalGate's MCP bridge."""

from copy import deepcopy
from typing import Any, Dict, List

SECURITY_SCHEMES: List[Dict[str, Any]] = [{"type": "noauth"}]
STRING_ARRAY = {"type": "array", "items": {"type": "string"}}
EDGE_PAIR_SCHEMA = {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2}
EDGE_OBJECT_SCHEMA = {"type": "object", "additionalProperties": True}
EDGE_SCHEMA = {"oneOf": [EDGE_OBJECT_SCHEMA, EDGE_PAIR_SCHEMA]}
GENERIC_OBJECT_OUTPUT: Dict[str, Any] = {"type": "object", "additionalProperties": True}
CLAIM_LEVEL_ENUM = ["blocked", "observation_only", "hypothesis_only", "testable_candidate", "supported_candidate", "identified_candidate", "experimentally_validated", "validated_external", "conjecture_candidate", "proof_or_counterexample_candidate"]


def _base_annotations(*, read_only: bool = True, idempotent: bool = True) -> Dict[str, Any]:
    return {"readOnlyHint": read_only, "destructiveHint": False, "openWorldHint": False, "idempotentHint": idempotent}


def _meta(invoking: str, invoked: str) -> Dict[str, Any]:
    return {"securitySchemes": deepcopy(SECURITY_SCHEMES), "openai/toolInvocation/invoking": invoking[:64], "openai/toolInvocation/invoked": invoked[:64]}


def _description(text: str) -> str:
    value = str(text or "").strip()
    if value.startswith("Use this when"):
        return value
    if value.startswith("Use this for "):
        return "Use this when " + value[len("Use this for "):]
    if not value:
        return "Use this when you need this CausalGate tool."
    return "Use this when " + value[:1].lower() + value[1:]


DAG_SCHEMA: Dict[str, Any] = {"type": "object", "description": "Optional graph/protocol shape. For empirical/physics hypotheses use edges or directed_edges. Mathematical conjectures may also include verification_protocol.", "properties": {"nodes": STRING_ARRAY, "edges": {"type": "array", "items": EDGE_SCHEMA}, "directed_edges": {"type": "array", "items": EDGE_PAIR_SCHEMA}, "bidirected_edges": {"type": "array", "items": EDGE_PAIR_SCHEMA}}, "additionalProperties": True}

HYPOTHESIS_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "description": "Physics/mechanistic hypothesis or mathematical conjecture candidate submitted to CausalGate for conservative review.",
    "properties": {
        "hypothesis_id": {"type": "string"}, "title": {"type": "string"}, "claim": {"type": "string", "description": "The claim. Avoid claiming proof, confirmed law, or final truth."}, "domain": {"type": "string"}, "hypothesis_kind": {"type": "string"}, "domain_diagnostic": {"type": "object", "additionalProperties": True}, "treatment": {"type": "string"}, "outcome": {"type": "string"}, "variables": {"type": "object", "additionalProperties": True}, "confounders": STRING_ARRAY, "adjustment_set": STRING_ARRAY, "observed_confounder_measurements": {"type": "object", "additionalProperties": True}, "identification_strategy": {"type": "string"}, "estimation_plan": {"type": "string"}, "counterfactual_query": {"type": "string"}, "mechanism_plausible": {"type": "string"}, "negative_controls": STRING_ARRAY, "negative_control_variables": STRING_ARRAY, "negative_control_tests": STRING_ARRAY, "falsification_tests": STRING_ARRAY, "measurable_predictions": STRING_ARRAY, "placebo_tests": STRING_ARRAY, "sensitivity_checks": STRING_ARRAY, "assumptions": STRING_ARRAY, "data_requirements": STRING_ARRAY, "evidence_refs": STRING_ARRAY, "external_evidence_quality": {"type": "object", "additionalProperties": True}, "simulation_plan": {"type": "string"}, "test_plan": {"type": "string"}, "verification_protocol": {"type": "object", "additionalProperties": True}, "dag": DAG_SCHEMA, "claim_level": {"type": "string", "enum": CLAIM_LEVEL_ENUM}, "requested_claim_level": {"type": "string", "enum": CLAIM_LEVEL_ENUM}, "metadata": {"type": "object", "additionalProperties": True}
    },
    "additionalProperties": True,
}

HYPOTHESIS_WRAPPER_SCHEMA: Dict[str, Any] = {"type": "object", "properties": {"hypothesis": HYPOTHESIS_SCHEMA}, "required": ["hypothesis"], "additionalProperties": False}
ENABLE_ID_SCHEMA: Dict[str, Any] = {"type": "boolean", "description": "When true, run graphical identification checks when relevant. Mathematical conjectures skip empirical causal identification.", "default": True}
AUTO_EXPAND_SCHEMA: Dict[str, Any] = {"type": "boolean", "description": "When true, mature REVISE/TEST_MORE/ABSTAIN hypotheses by generating a conservative expanded draft for re-checking.", "default": False}
NATIVE_DISCOVERY_SCHEMA: Dict[str, Any] = {"type": "boolean", "description": "When true, CausalGate's deterministic native generator creates the initial structured physics/math candidate.", "default": False}
GEMINI_LANGUAGE_ONLY_SCHEMA: Dict[str, Any] = {"type": "boolean", "description": "Deprecated compatibility flag. Gemini is disabled in native JSON mode.", "default": False}

VETO_OUTPUT_SCHEMA: Dict[str, Any] = {"type": "object", "properties": {"decision": {"type": "string", "enum": ["FINAL_CANDIDATE", "REVISE", "TEST_MORE", "BLOCK", "ABSTAIN"]}, "reason_codes": STRING_ARRAY, "missing_items": STRING_ARRAY, "next_instruction": {"type": "string"}}, "additionalProperties": True}
EXPANSION_OUTPUT_SCHEMA: Dict[str, Any] = {"type": "object", "properties": {"state": {"type": "string"}, "accepted": {"type": "boolean"}, "should_continue": {"type": "boolean"}, "next_required_step": {"type": "string"}, "expanded_hypothesis": HYPOTHESIS_SCHEMA, "expansion_questions": STRING_ARRAY, "warnings": STRING_ARRAY}, "additionalProperties": True}
GENERATION_SCHEMA: Dict[str, Any] = {"type": "object", "properties": {"goal": {"type": "string"}, "research_goal": {"type": "string"}, "objective": {"type": "string"}, "claim": {"type": "string"}, "hypothesis": HYPOTHESIS_SCHEMA, "confounders": STRING_ARRAY, "treatment": {"type": "string"}, "outcome": {"type": "string"}, "domain": {"type": "string"}}, "additionalProperties": True}
PLANNER_SCHEMA: Dict[str, Any] = {"type": "object", "properties": {"goal": {"type": "string"}, "research_goal": {"type": "string"}, "objective": {"type": "string"}, "mode": {"type": "string", "enum": ["auto", "generate_review", "literature_first", "review_only", "native_json_only"]}, "hypothesis": HYPOTHESIS_SCHEMA, "claim": {"type": "string"}, "include_external_evidence": {"type": "boolean", "default": True}, "sources": STRING_ARRAY, "literature_limit": {"type": "integer", "minimum": 1, "maximum": 25, "default": 5}, "max_steps": {"type": "integer", "minimum": 1, "maximum": 25, "default": 6}, "max_iterations": {"type": "integer", "minimum": 1, "maximum": 25, "default": 6}, "enable_identification": ENABLE_ID_SCHEMA, "write_ledger": {"type": "boolean", "default": False}}, "additionalProperties": True}
LITERATURE_SEARCH_SCHEMA: Dict[str, Any] = {"type": "object", "properties": {"query": {"type": "string"}, "goal": {"type": "string"}, "research_goal": {"type": "string"}, "sources": {"type": "array", "items": {"type": "string", "enum": ["crossref", "openalex", "pubmed", "arxiv"]}, "default": ["crossref", "openalex", "pubmed", "arxiv"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 25, "default": 5}}, "additionalProperties": False}

MATH_CLAIM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "description": "Mathematical conjecture/proof-sketch candidate for CausalGate's Step-99 math hypothesis loop.",
    "properties": {
        "claim_id": {"type": "string"},
        "title": {"type": "string"},
        "claim": {"type": "string", "description": "Mathematical statement or proof-sketch claim. Do not use solved/proved wording without checker attestation."},
        "problem_name": {"type": "string"},
        "claim_type": {"type": "string"},
        "claim_level": {"type": "string", "enum": ["informal_idea", "conjecture_candidate", "proof_sketch_only", "numerical_evidence_only", "proof_obligation_candidate", "formal_proof_claimed", "formally_verified_theorem", "counterexample_candidate"]},
        "definitions": STRING_ARRAY,
        "assumptions": STRING_ARRAY,
        "proof_sketch": {"type": "string"},
        "proof_steps": STRING_ARRAY,
        "lemmas": STRING_ARRAY,
        "dependencies": STRING_ARRAY,
        "formal_system": {"type": "string"},
        "formal_statement": {"type": "string"},
        "lean_code": {"type": "string"},
        "proof_checker_result": {"type": "object", "additionalProperties": True},
        "numerical_evidence": STRING_ARRAY,
        "counterexamples": STRING_ARRAY,
        "known_obstructions": STRING_ARRAY,
        "references": STRING_ARRAY,
        "metadata": {"type": "object", "additionalProperties": True},
    },
    "additionalProperties": True,
}

MATH_HYPOTHESIS_LOOP_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "dialogue_id": {"type": "string"},
        "math_claim": MATH_CLAIM_SCHEMA,
        "hypothesis": MATH_CLAIM_SCHEMA,
        "max_rounds": {"type": "integer", "minimum": 1, "maximum": 12, "default": 3},
        "auto_revise": {"type": "boolean", "default": True},
    },
    "additionalProperties": True,
}


def _tool(name: str, title: str, description: str, input_schema: Dict[str, Any], output_schema: Dict[str, Any], invoking: str, invoked: str, *, read_only: bool = True, idempotent: bool = True, open_world: bool = False) -> Dict[str, Any]:
    annotations = _base_annotations(read_only=read_only, idempotent=idempotent)
    annotations["openWorldHint"] = open_world
    return {"name": name, "title": title, "description": _description(description), "inputSchema": input_schema, "outputSchema": output_schema, "annotations": annotations, "securitySchemes": deepcopy(SECURITY_SCHEMES), "_meta": _meta(invoking, invoked)}


RESEARCH_STEP_SCHEMA = {"type": "object", "properties": {"goal": {"type": "string"}, "run_id": {"type": "string"}, "step": {"type": "integer", "minimum": 0}, "feedback": {"type": "string"}, "hypothesis": HYPOTHESIS_SCHEMA, "write_ledger": {"type": "boolean", "default": False}, "ledger_path": {"type": "string", "default": "out/scientific/ledger.jsonl"}, "enable_identification": ENABLE_ID_SCHEMA}, "required": ["goal"], "additionalProperties": False}
RESEARCH_CYCLE_SCHEMA = {"type": "object", "properties": {"goal": {"type": "string"}, "run_id": {"type": "string"}, "dialogue_id": {"type": "string"}, "max_steps": {"type": "integer", "minimum": 1, "maximum": 20, "default": 3}, "max_iterations": {"type": "integer", "minimum": 1, "maximum": 20, "default": 3}, "start_step": {"type": "integer", "minimum": 0, "default": 0}, "feedback": {"type": "string"}, "hypothesis": HYPOTHESIS_SCHEMA, "candidate_hypotheses": {"type": "array", "items": HYPOTHESIS_SCHEMA}, "write_ledger": {"type": "boolean", "default": False}, "ledger_path": {"type": "string", "default": "out/scientific/ledger.jsonl"}, "enable_identification": ENABLE_ID_SCHEMA, "auto_expand": AUTO_EXPAND_SCHEMA, "auto_expand_hypothesis": AUTO_EXPAND_SCHEMA, "agent_repair": {"type": "boolean", "default": True}, "native_hypothesis_agent": NATIVE_DISCOVERY_SCHEMA, "gemini_language_only": GEMINI_LANGUAGE_ONLY_SCHEMA, "use_langgraph": {"type": "boolean", "default": False}}, "required": ["goal"], "additionalProperties": False}

TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    _tool("causalgate_health", "Check CausalGate health", "Use this when you need to confirm the CausalGate MCP server is alive and see its available tool names.", {"type": "object", "properties": {}, "additionalProperties": False}, GENERIC_OBJECT_OUTPUT, "Checking CausalGate…", "CausalGate is reachable"),
    _tool("causalgate_normalize_hypothesis", "Normalize scientific candidate", "Use this when a physics hypothesis or mathematical conjecture needs CausalGate's canonical contract before review.", HYPOTHESIS_WRAPPER_SCHEMA, GENERIC_OBJECT_OUTPUT, "Normalizing candidate…", "Candidate normalized"),
    _tool("causalgate_generate_hypothesis", "Generate native candidate", "Use this when CausalGate should create an initial structured physics hypothesis or mathematical conjecture deterministically from a goal. This does not create evidence, proof, or final truth.", GENERATION_SCHEMA, GENERIC_OBJECT_OUTPUT, "Generating candidate…", "Candidate generated", read_only=False, idempotent=False),
    _tool("causalgate_plan_scientific_tools", "Plan scientific tool calls", "Use this when CausalGate should choose next MCP tools for generation, review, or literature lookup. The planner selects tools; it does not execute them or upgrade claim level.", PLANNER_SCHEMA, GENERIC_OBJECT_OUTPUT, "Planning tool calls…", "Tool plan ready"),
    _tool("causalgate_search_scientific_literature", "Search scientific literature metadata", "Use this when you need public scientific metadata including Crossref, OpenAlex, PubMed, and arXiv. Results are references for review, not proof or validation.", LITERATURE_SEARCH_SCHEMA, GENERIC_OBJECT_OUTPUT, "Searching literature…", "Literature metadata ready", open_world=True),
    _tool("causalgate_veto_hypothesis", "Veto scientific candidate", "Use this when you need CausalGate to conservatively review a physics claim or mathematical conjecture and return FINAL_CANDIDATE, REVISE, TEST_MORE, BLOCK, or ABSTAIN.", {"type": "object", "properties": {"hypothesis": HYPOTHESIS_SCHEMA, "enable_identification": ENABLE_ID_SCHEMA}, "required": ["hypothesis"], "additionalProperties": False}, VETO_OUTPUT_SCHEMA, "Running veto…", "Veto result ready"),
    _tool("causalgate_expand_hypothesis", "Expand scientific candidate", "Use this when a candidate is REVISE/TEST_MORE/ABSTAIN and you want CausalGate to preserve it, add missing structure, ask targeted questions, and return the next draft.", {"type": "object", "properties": {"hypothesis": HYPOTHESIS_SCHEMA, "verdict": VETO_OUTPUT_SCHEMA, "enable_identification": ENABLE_ID_SCHEMA}, "required": ["hypothesis"], "additionalProperties": False}, EXPANSION_OUTPUT_SCHEMA, "Expanding candidate…", "Candidate expansion ready", read_only=False, idempotent=False),
    _tool("causalgate_repair_hypothesis", "Repair scientific candidate", "Use this when a candidate hypothesis needs deterministic repair of missing or inconsistent contract fields before veto/review.", {"type": "object", "properties": {"hypothesis": HYPOTHESIS_SCHEMA, "goal": {"type": "string"}, "feedback": {"type": "string"}}, "additionalProperties": True}, GENERIC_OBJECT_OUTPUT, "Repairing candidate…", "Candidate repair ready", read_only=False, idempotent=False),
    _tool("causalgate_run_llm_dialogue", "Run LLM-CausalGate dialogue", "Use this for a bounded LLM-to-CausalGate dialogue where the LLM proposes/revises and CausalGate controls veto, expansion, and final candidate status.", RESEARCH_CYCLE_SCHEMA, GENERIC_OBJECT_OUTPUT, "Running LLM dialogue…", "LLM dialogue reviewed", read_only=False, idempotent=False, open_world=True),
    _tool("causalgate_run_native_json_hypothesis", "Run native JSON hypothesis", "Use this for the Hugging Face/demo behavior: CausalGate generates a physics or mathematics candidate natively, reviews it, shows cycles, and returns JSON only. No external LLM is called.", RESEARCH_CYCLE_SCHEMA, GENERIC_OBJECT_OUTPUT, "Running native JSON…", "Native JSON reviewed", read_only=False, idempotent=False),
    _tool("causalgate_run_gemini_llm_dialogue", "Run native JSON hypothesis compatibility alias", "Use this when older callers request the legacy Gemini-named dialogue tool. It is a compatibility alias for causalgate_run_native_json_hypothesis; Gemini is disabled and no external Gemini call is made.", RESEARCH_CYCLE_SCHEMA, GENERIC_OBJECT_OUTPUT, "Running native JSON…", "Native JSON reviewed", read_only=False, idempotent=False),
    _tool("causalgate_assess_falsification", "Assess falsification plan", "Use this when you need to check falsification tests, negative controls, placebo tests, sensitivity checks, and review readiness.", HYPOTHESIS_WRAPPER_SCHEMA, GENERIC_OBJECT_OUTPUT, "Assessing falsification…", "Falsification assessment ready"),
    _tool("causalgate_infer_evidence_requirements", "Infer evidence requirements", "Use this when you need the minimum evidence checklist required before promoting a candidate to a higher claim level.", HYPOTHESIS_WRAPPER_SCHEMA, GENERIC_OBJECT_OUTPUT, "Inferring evidence requirements…", "Evidence checklist ready"),
    _tool("causalgate_run_research_step", "Run one research step", "Use this when an LLM or user has proposed one candidate and you want CausalGate to veto it and produce the next revision instruction.", RESEARCH_STEP_SCHEMA, GENERIC_OBJECT_OUTPUT, "Running research step…", "Research step reviewed", read_only=False, idempotent=False),
    _tool("causalgate_run_research_cycle", "Run bounded research cycle", "Use this when you have one or more candidate hypotheses/conjectures and want a bounded propose-veto-revise cycle with optional auto-expansion.", RESEARCH_CYCLE_SCHEMA, GENERIC_OBJECT_OUTPUT, "Running research cycle…", "Research cycle reviewed", read_only=False, idempotent=False),
    _tool("causalgate_run_math_hypothesis_loop", "Run math hypothesis loop", "Use this when an LLM proposes a mathematical conjecture, proof sketch, or alleged proof and you want a bounded veto-recommend-revise loop with proof-overclaim protection.", MATH_HYPOTHESIS_LOOP_SCHEMA, GENERIC_OBJECT_OUTPUT, "Running math critic…", "Math hypothesis reviewed", read_only=False, idempotent=False),
    _tool("causalgate_run_native_scientific_agent", "Run native scientific agent", "Use this when you want CausalGate's own stdlib scientific-agent runtime without LangGraph: it runs veto/audit, deterministic routing, and optional expansion without inventing science autonomously.", RESEARCH_CYCLE_SCHEMA, GENERIC_OBJECT_OUTPUT, "Running native agent…", "Native agent routed", read_only=False, idempotent=False),
    _tool("causalgate_run_langgraph_scientific_agent", "Run LangGraph scientific agent", "Use this when you want a graph-shaped scientific agent cycle where an optional LangGraph backend orchestrates CausalGate's conservative veto and revision routing.", RESEARCH_CYCLE_SCHEMA, GENERIC_OBJECT_OUTPUT, "Running scientific graph…", "Scientific graph reviewed", read_only=False, idempotent=False),
    _tool("causalgate_run_claude_research_cycle", "Run Claude + CausalGate cycle", "Use this when explicitly testing Claude as the hypothesis generator and CausalGate as the veto layer. It uses dry_run when no Anthropic API key is configured.", {"type": "object", "properties": {"goal": {"type": "string"}, "run_id": {"type": "string"}, "max_steps": {"type": "integer", "minimum": 1, "maximum": 20, "default": 3}, "feedback": {"type": "string"}, "model": {"type": "string"}, "api_key": {"type": "string"}, "dry_run": {"type": "boolean", "default": True}, "write_ledger": {"type": "boolean", "default": False}, "ledger_path": {"type": "string"}, "enable_identification": ENABLE_ID_SCHEMA, "domain": {"type": "string"}, "constraints": STRING_ARRAY}, "required": ["goal"], "additionalProperties": False}, GENERIC_OBJECT_OUTPUT, "Running Claude cycle…", "Claude cycle reviewed", read_only=False, idempotent=False, open_world=True),
    _tool("causalgate_read_scientific_ledger", "Read scientific ledger", "Use this when you need to inspect recent CausalGate scientific research-loop ledger events.", {"type": "object", "properties": {"ledger_path": {"type": "string", "default": "out/scientific/ledger.jsonl"}, "run_id": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50}}, "additionalProperties": False}, GENERIC_OBJECT_OUTPUT, "Reading scientific ledger…", "Scientific ledger loaded"),
]


def list_tool_schemas() -> List[Dict[str, Any]]:
    return deepcopy(TOOL_DEFINITIONS)


def app_metadata(base_url: str | None = None) -> Dict[str, Any]:
    mcp_url = "/mcp" if not base_url else base_url.rstrip("/") + "/mcp"
    return {"name": "CausalGate", "slug": "causalgate", "description": "Conservative empirical/physics/math hypothesis and conjecture tools for native JSON generation, review, falsification/proof planning, claim-level auditing, literature metadata lookup, and bounded research loops. Gemini compatibility names are aliases only; Gemini is disabled.", "mcp_endpoint": mcp_url, "auth": {"type": "none"}, "securitySchemes": deepcopy(SECURITY_SCHEMES), "tool_count": len(TOOL_DEFINITIONS), "tools": [{"name": tool["name"], "title": tool.get("title", tool["name"]), "description": tool.get("description", ""), "readOnlyHint": tool.get("annotations", {}).get("readOnlyHint")} for tool in TOOL_DEFINITIONS]}


__all__ = ["SECURITY_SCHEMES", "app_metadata", "list_tool_schemas"]
