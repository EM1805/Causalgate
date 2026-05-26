from __future__ import annotations

"""Tool-call facade for CausalGate's MCP bridge."""

from typing import Any, Dict, List, Mapping

from causalgate import __version__
from causalgate.math_hypothesis import run_math_hypothesis_loop
from causalgate.scientific import (
    assess_falsification,
    evaluate_hypothesis,
    expand_hypothesis,
    generate_hypothesis,
    infer_evidence_requirements,
    normalize_scientific_hypothesis,
    plan_scientific_tools,
    read_scientific_ledger,
    repair_hypothesis,
    run_langgraph_scientific_agent,
    run_llm_dialogue,
    run_native_scientific_agent,
    run_research_cycle,
    run_research_step,
    search_scientific_literature,
)
from causalgate.scientific.diagnostic_attention import apply_diagnostic_attention_to_dialogue_result

from .schemas import list_tool_schemas


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _intish(value: Any, default: int = 1, minimum: int = 1, maximum: int = 25) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _dialogue_result_with_diagnostic_attention(result: Mapping[str, Any]) -> Dict[str, Any]:
    return apply_diagnostic_attention_to_dialogue_result(result)


def list_tools() -> Dict[str, Any]:
    return {"tools": list_tool_schemas()}


def _run_native_json_hypothesis(args: Mapping[str, Any]) -> Dict[str, Any]:
    from causalgate.integrations.gemini_dialogue_adapter import run_native_json_hypothesis_dialogue
    return _dialogue_result_with_diagnostic_attention(run_native_json_hypothesis_dialogue(args))


def call_tool(name: str, arguments: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    args = _as_dict(arguments)

    if name == "causalgate_health":
        return {"status": "ok", "service": "causalgate-mcp", "version": __version__, "tools": [tool["name"] for tool in list_tool_schemas()]}

    if name == "causalgate_normalize_hypothesis":
        payload = args.get("hypothesis") if isinstance(args.get("hypothesis"), Mapping) else args
        return {"hypothesis": normalize_scientific_hypothesis(payload).to_dict()}

    if name == "causalgate_generate_hypothesis":
        return generate_hypothesis(args)

    if name == "causalgate_plan_scientific_tools":
        return plan_scientific_tools(args)

    if name == "causalgate_search_scientific_literature":
        return search_scientific_literature(args)

    if name == "causalgate_veto_hypothesis":
        payload = args.get("hypothesis") if isinstance(args.get("hypothesis"), Mapping) else args
        enable_identification = bool(args.get("enable_identification", True))
        return evaluate_hypothesis(payload, enable_identification=enable_identification)

    if name == "causalgate_expand_hypothesis":
        enable_identification = bool(args.get("enable_identification", True))
        return expand_hypothesis(args, enable_identification=enable_identification)

    if name == "causalgate_repair_hypothesis":
        return repair_hypothesis(args)

    if name == "causalgate_run_llm_dialogue":
        enable_identification = bool(args.get("enable_identification", True))
        return _dialogue_result_with_diagnostic_attention(run_llm_dialogue(args, enable_identification=enable_identification))

    if name in {"causalgate_run_native_json_hypothesis", "causalgate_run_gemini_llm_dialogue"}:
        return _run_native_json_hypothesis(args)

    if name == "causalgate_assess_falsification":
        payload = args.get("hypothesis") if isinstance(args.get("hypothesis"), Mapping) else args
        return assess_falsification(payload)

    if name == "causalgate_infer_evidence_requirements":
        payload = args.get("hypothesis") if isinstance(args.get("hypothesis"), Mapping) else args
        return infer_evidence_requirements(payload)

    if name == "causalgate_run_research_step":
        enable_identification = bool(args.get("enable_identification", True))
        return run_research_step(args, enable_identification=enable_identification)

    if name == "causalgate_run_research_cycle":
        enable_identification = bool(args.get("enable_identification", True))
        return run_research_cycle(args, enable_identification=enable_identification)

    if name == "causalgate_run_math_hypothesis_loop":
        return run_math_hypothesis_loop(args)

    if name == "causalgate_run_native_scientific_agent":
        return run_native_scientific_agent(args)

    if name == "causalgate_run_langgraph_scientific_agent":
        return run_langgraph_scientific_agent(args)

    if name == "causalgate_run_claude_research_cycle":
        from causalgate.integrations.claude import run_claude_research_cycle
        try:
            return {"ok": True, "tool": name, "result": run_claude_research_cycle(args)}
        except Exception as exc:  # pragma: no cover - defensive MCP boundary
            return {"ok": False, "tool": name, "error": {"code": "CLAUDE_RESEARCH_CYCLE_ERROR", "message": f"{type(exc).__name__}: {exc}"}}

    if name == "causalgate_read_scientific_ledger":
        return read_scientific_ledger(path=_clean_str(args.get("ledger_path"), "out/scientific/ledger.jsonl"), run_id=_clean_str(args.get("run_id")) or None, limit=_intish(args.get("limit", 50), default=50, minimum=1, maximum=500))

    return {"error": {"code": "UNKNOWN_TOOL", "message": f"Unknown CausalGate MCP tool: {name}", "available_tools": [tool["name"] for tool in list_tool_schemas()]}}


__all__ = ["call_tool", "list_tools"]
