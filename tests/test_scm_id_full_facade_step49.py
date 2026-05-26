import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_full import ID_FULL_INTERFACE_VERSION, full_id, full_id_from_scm_graph
from scm_parts.id_status import id_capability_flags


def test_step49_full_id_facade_identifies_observed_dag_without_full_claim():
    graph = admg_from_edges(["X", "Y"], [("X", "Y")], [])
    result = full_id(graph, ["X"], ["Y"]).to_dict()
    assert result["interface_version"] == ID_FULL_INTERFACE_VERSION
    assert result["identified"] is True
    assert result["identification_status"] in {
        "identified_observed_dag_truncated_factorization",
        "identified_q_factor_full_district",
        "identified_recursive_district_decomposition",
        "identified_observed_dag_truncated_factorization_set_case",
    }
    assert result["formula"].startswith("P_{do(X)}(Y) = ")
    assert result["full_id_claim_allowed"] == 1
    assert "full_recursive_id_implemented_flag_enabled" in result["full_id_claim_reason"]
    ast = json.loads(result["formula_ast_json"])
    assert ast["ast_version"] == "id_ast_v1"


def test_step49_full_id_facade_preserves_formal_hedge_fail_branch():
    graph = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    result = full_id(graph, "X", "Y").to_dict()
    assert result["identified"] is False
    assert result["identification_status"] == "blocked_formal_hedge_certificate"
    assert result["blocker_class"] == "formal_hedge_certificate"
    assert "ID-5" in result["canonical_rules"]
    assert result["formula"] == ""
    ast = json.loads(result["formula_ast_json"])
    assert ast["node_type"] == "hedge_fail"


def test_step49_full_id_facade_supports_set_valued_queries():
    graph = admg_from_edges(["X1", "X2", "Y"], [("X1", "Y"), ("X2", "Y")], [])
    result = full_id(graph, ["X1", "X2"], ["Y"]).to_dict()
    assert result["identified"] is True
    assert result["treatments"] == "X1|X2"
    assert result["outcomes"] == "Y"
    assert "P_{do(X1,X2)}(Y) = " in result["formula"]


def test_step49_full_id_facade_blocks_invalid_overlap():
    graph = admg_from_edges(["X", "Y"], [("X", "Y")], [])
    result = full_id(graph, ["X"], ["X"]).to_dict()
    assert result["identified"] is False
    assert result["identification_status"] == "invalid_full_id_query"
    assert result["blocker_class"] == "invalid_query"
    assert "TREATMENT_OUTCOME_OVERLAP:X" in result["reason_codes"]


def test_step49_full_id_from_scm_graph_and_status_flags():
    scm_graph = {
        "nodes": [{"id": "X"}, {"id": "Y"}],
        "edges": [{"source": "X", "target": "Y"}],
    }
    result = full_id_from_scm_graph(scm_graph, "X", "Y").to_dict()
    assert result["identified"] is True
    flags = id_capability_flags()
    assert flags["id_full_public_facade_step49_implemented"] == 1
    assert flags["full_recursive_id_implemented"] == 1
