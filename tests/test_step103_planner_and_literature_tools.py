from causalgate.mcp.tools import call_tool
from causalgate.scientific import plan_scientific_tools, search_scientific_literature


def test_planner_selects_native_agent_and_literature_search():
    plan = plan_scientific_tools({
        "goal": "urban green spaces -> stress levels",
        "mode": "generate_review",
        "include_external_evidence": True,
        "literature_limit": 3,
    })

    names = [call["tool_name"] for call in plan["planned_calls"]]
    assert names[0] == "causalgate_search_scientific_literature"
    assert "causalgate_run_native_scientific_agent" in names
    assert plan["guardrails"]


def test_planner_review_only_uses_veto_when_hypothesis_supplied():
    plan = call_tool("causalgate_plan_scientific_tools", {
        "mode": "review_only",
        "include_external_evidence": False,
        "hypothesis": {
            "claim": "X may affect Y.",
            "treatment": "X",
            "outcome": "Y",
        },
    })

    assert plan["planned_calls"][0]["tool_name"] == "causalgate_veto_hypothesis"
    assert plan["planned_calls"][0]["arguments"]["hypothesis"]["claim"] == "X may affect Y."


def test_planner_gemini_language_only_sets_native_flags():
    plan = plan_scientific_tools({"goal": "sleep -> productivity", "mode": "gemini_language_only"})

    call = plan["planned_calls"][0]
    assert call["tool_name"] == "causalgate_run_gemini_llm_dialogue"
    assert call["arguments"]["native_hypothesis_agent"] is True
    assert call["arguments"]["gemini_language_only"] is True


def test_literature_search_requires_query():
    result = search_scientific_literature({})
    assert result["ok"] is False
    assert result["error"]["code"] == "MISSING_QUERY"


def test_mcp_exposes_new_tools():
    tools = call_tool("causalgate_health", {})["tools"]
    assert "causalgate_plan_scientific_tools" in tools
    assert "causalgate_search_scientific_literature" in tools


def test_literature_search_unknown_source_is_safe():
    result = search_scientific_literature({"query": "sleep", "sources": ["unknown"], "limit": 1})
    assert result["ok"] is True
    assert result["records"] == []
    assert result["errors"][0]["error"] == "unknown_source"
    assert result["external_evidence_quality"]["status"] == "metadata_only"
