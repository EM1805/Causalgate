from causalgate.causal_core.identification import IdentificationEngine, identify_effect, identify_many, normalize_scm_graph


def test_identification_adapter_accepts_compact_edges():
    graph = {
        "nodes": [{"id": "agent_action"}, {"id": "task_success"}, {"id": "ambiguity"}],
        "edges": [
            ["ambiguity", "agent_action"],
            ["ambiguity", "task_success"],
            ["agent_action", "task_success"],
        ],
    }
    result = IdentificationEngine().identify({
        "scm_graph": graph,
        "treatment": "agent_action",
        "outcome": "task_success",
        "adjustment_set": ["ambiguity"],
    })
    assert result.treatment == "agent_action"
    assert result.outcome == "task_success"
    assert result.identified is True
    assert result.identification_tier.startswith("identified")
    assert result.estimand


def test_identification_adapter_blocks_missing_graph():
    result = IdentificationEngine().identify({
        "treatment": "agent_action",
        "outcome": "task_success",
    })
    assert result.identified is False
    assert result.identification_strategy == "blocked_missing_graph"
    assert "MISSING_SCM_GRAPH" in result.reason_codes


def test_identification_adapter_runs_many_queries():
    payload = {
        "scm_graph": {
            "nodes": ["agent_action", "action_intensity", "user_or_system_harm", "environment_context"],
            "edges": [
                ["environment_context", "agent_action"],
                ["environment_context", "user_or_system_harm"],
                ["agent_action", "action_intensity"],
                ["action_intensity", "user_or_system_harm"],
            ],
            "queries": [
                {"id": "q1", "treatment": "agent_action", "outcome": "user_or_system_harm"},
                {"id": "q2", "treatment": "action_intensity", "outcome": "user_or_system_harm"},
            ],
        }
    }
    results = IdentificationEngine().identify_many(payload)
    assert len(results) == 2
    assert all(r.treatment for r in results)
    assert all(r.outcome for r in results)


def test_identification_adapter_functional_helper():
    result = identify_effect({
        "nodes": ["x", "y"],
        "edges": [["x", "y"]],
        "treatment": "x",
        "outcome": "y",
    })
    assert result["identified"] is True
    assert result["treatment"] == "x"


def test_normalize_scm_graph_promotes_edge_nodes():
    graph = normalize_scm_graph({"edges": [["x", "y"]]})
    node_ids = {n["id"] for n in graph["nodes"]}
    assert {"x", "y"}.issubset(node_ids)
    assert graph["edges"][0]["source"] == "x"
    assert graph["edges"][0]["target"] == "y"
