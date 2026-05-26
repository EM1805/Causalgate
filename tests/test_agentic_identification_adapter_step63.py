from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from causalgate.causal_core.identification.engine import (
    IdentificationEngine,
    IdentificationQuery,
    identify_effect,
    identify_many,
)


def _graph(nodes, directed=(), bidirected=()):
    edges = [[a, b] for a, b in directed]
    edges += [{"source": a, "target": b, "edge_kind": "bidirected"} for a, b in bidirected]
    return {"nodes": list(nodes), "edges": edges}


def test_step63_adapter_routes_single_query_to_full_id_api():
    result = identify_effect({
        "graph": _graph(["X", "Y"], [("X", "Y")]),
        "treatment": "X",
        "outcome": "Y",
    })
    assert result["identified"] is True
    assert result["treatments"] == ["X"]
    assert result["outcomes"] == ["Y"]
    assert result["identification_tier"] == "identified_canonical"
    assert result["primary_formula_authority"].startswith("id_canonical_formula")
    assert "P_{do(X)}(Y)" in result["estimand"]
    assert result["full_id_claim_allowed"] == 1


def test_step63_adapter_accepts_set_valued_treatments_and_outcomes():
    result = identify_effect({
        "graph": _graph(["X1", "X2", "Y1", "Y2"], [("X1", "Y1"), ("X2", "Y2")]),
        "treatments": ["X1", "X2"],
        "outcomes": ["Y1", "Y2"],
    })
    assert result["identified"] is True
    assert result["treatments"] == ["X1", "X2"]
    assert result["outcomes"] == ["Y1", "Y2"]
    assert "P_{do(X1,X2)}(Y1,Y2)" in result["estimand"]
    assert result["raw_id_result"]["canonical_formula_used_for_output"] == 1


def test_step63_adapter_routes_conditions_to_idc_pruning_api():
    result = identify_effect({
        "graph": _graph(["X", "Y", "Z"], [("X", "Y")]),
        "treatment": "X",
        "outcome": "Y",
        "conditions": ["Z"],
    })
    assert result["identified"] is True
    assert result["identification_tier"] == "identified_conditional"
    assert result["conditions"] == ["Z"]
    assert result["idc_pruned_conditions"] == "Z"
    assert result["idc_pruning_status"] == "idc_pruning_all_conditions_removed_step62"
    assert "P_{do(X)}(Y | Z) = P_{do(X)}(Y)" in result["estimand"]


def test_step63_adapter_preserves_blocked_failure_certificate_channel():
    result = identify_effect({
        "graph": _graph(["X", "Y"], [("X", "Y")], [("X", "Y")]),
        "treatment": "X",
        "outcome": "Y",
    })
    assert result["identified"] is False
    assert result["identification_tier"] == "blocked_nonidentifiable"
    assert result["failure_certificate_status"]
    assert result["failure_certified"] == 1
    assert result["raw_id_result"]["failure_certificate_json"]


def test_step63_adapter_allows_valid_no_edge_graphs():
    result = identify_effect({
        "graph": _graph(["X", "Y"]),
        "treatment": "X",
        "outcome": "Y",
    })
    assert result["identified"] is True
    assert "P(Y)" in result["estimand"]


def test_step63_identify_many_uses_graph_queries_with_sets_and_conditions():
    graph = _graph(["X", "Y", "Z"], [("X", "Y")])
    payload = {
        "graph": {
            **graph,
            "queries": [
                {"treatments": ["X"], "outcomes": ["Y"]},
                {"treatments": ["X"], "outcomes": ["Y"], "conditions": ["Z"]},
            ],
        }
    }
    results = identify_many(payload)
    assert len(results) == 2
    assert results[0]["identified"] is True
    assert results[1]["identified"] is True
    assert results[1]["identification_tier"] == "identified_conditional"


def test_step63_action_effect_bridge_can_pass_conditions():
    graph = _graph(["A", "Harm", "Context"], [("A", "Harm")])
    result = IdentificationEngine().identify_action_effect(
        {"action_name": "A", "protected_outcome": "Harm", "conditions": ["Context"]},
        graph,
    ).to_dict()
    assert result["identified"] is True
    assert result["conditions"] == ["Context"]
    assert result["idc_pruned_conditions"] == "Context"


if __name__ == "__main__":
    for fn in [
        test_step63_adapter_routes_single_query_to_full_id_api,
        test_step63_adapter_accepts_set_valued_treatments_and_outcomes,
        test_step63_adapter_routes_conditions_to_idc_pruning_api,
        test_step63_adapter_preserves_blocked_failure_certificate_channel,
        test_step63_adapter_allows_valid_no_edge_graphs,
        test_step63_identify_many_uses_graph_queries_with_sets_and_conditions,
        test_step63_action_effect_bridge_can_pass_conditions,
    ]:
        fn()
    print("step63 adapter tests passed")
