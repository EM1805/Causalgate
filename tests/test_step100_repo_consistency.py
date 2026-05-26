from causalgate import __version__
from causalgate.mcp.schemas import list_tool_schemas
from causalgate.scientific import normalize_scientific_hypothesis, run_native_scientific_agent, run_research_cycle


def _tool(name):
    return {tool["name"]: tool for tool in list_tool_schemas()}[name]


def test_step100_version_mentions_hypothesis_maturation():
    assert __version__ == "0.3.0.post107"


def test_step100_normalize_dag_accepts_directed_and_bidirected_edges():
    hyp = normalize_scientific_hypothesis({
        "hypothesis_id": "H-dag-100",
        "claim": "X may affect Y.",
        "treatment": "X",
        "outcome": "Y",
        "dag": {
            "nodes": ["X", "Y", "U"],
            "directed_edges": [["X", "Y"]],
            "bidirected_edges": [["X", "Y"]],
        },
    }).to_dict()

    edges = {(edge["source"], edge["target"], edge["edge_kind"]) for edge in hyp["dag"]["edges"]}
    assert ("X", "Y", "directed") in edges
    assert ("X", "Y", "bidirected") in edges
    assert "dag_with_nodes_and_edges" not in normalize_scientific_hypothesis(hyp).missing_core_items()


def test_step100_research_cycle_auto_expands_incomplete_hypothesis():
    result = run_research_cycle({
        "goal": "Mature a weak hypothesis.",
        "max_steps": 2,
        "auto_expand": True,
        "write_ledger": False,
        "enable_identification": False,
        "hypothesis": {
            "hypothesis_id": "H-cycle-expand",
            "claim": "Sleep may affect productivity.",
            "metadata": {"version": 1},
        },
    })

    assert result["auto_expand"] is True
    assert result["expansion_count"] >= 1
    assert result["steps_completed"] >= 1
    first = result["step_results"][0]
    assert "expansion" in first
    assert first["expansion"]["expanded_hypothesis"]["metadata"]["expanded_by"] == "causalgate.scientific.hypothesis_expansion"


def test_step100_native_agent_can_auto_expand_without_external_generator():
    result = run_native_scientific_agent({
        "goal": "Mature a weak hypothesis natively.",
        "max_iterations": 2,
        "auto_expand_hypothesis": True,
        "write_ledger": False,
        "enable_identification": False,
        "hypothesis": {
            "hypothesis_id": "H-native-expand",
            "claim": "X may affect Y.",
            "metadata": {"version": 1},
        },
    })

    assert result["state"]["metadata"]["auto_expand_hypothesis"] is True
    assert "hypothesis_expansion_generated" in result["trace"]
    expansion = result["state"]["metadata"].get("last_hypothesis_expansion")
    assert expansion
    assert expansion["expanded_hypothesis"]["metadata"]["expanded_by"] == "causalgate.scientific.hypothesis_expansion"


def test_step100_mcp_schema_exposes_auto_expansion_flags():
    cycle_props = _tool("causalgate_run_research_cycle")["inputSchema"]["properties"]
    native_props = _tool("causalgate_run_native_scientific_agent")["inputSchema"]["properties"]
    assert "auto_expand" in cycle_props
    assert "auto_expand_hypothesis" in native_props
    assert cycle_props["hypothesis"]["properties"]["requested_claim_level"]["enum"]
