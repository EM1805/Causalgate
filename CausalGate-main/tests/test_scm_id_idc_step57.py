import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_full import identify_conditional_effect, identify_conditional_effect_from_scm_graph
from scm_parts.id_status import id_capability_flags


def test_step57_idc_ratio_on_observed_dag_joint():
    graph = admg_from_edges(["X", "Z", "Y"], [("X", "Z"), ("Z", "Y")], [])
    row = identify_conditional_effect(graph, "X", "Y", "Z").to_dict()
    payload = json.loads(row["expression_json"])
    ast = json.loads(row["formula_ast_json"])
    assert row["identified"] is True
    assert row["identification_status"] == "identified_idc_ratio_over_identified_joint_step57"
    assert row["formula"].startswith("P_{do(X)}(Y | Z) =")
    assert row["denominator_formula"].startswith("sum_{Y}")
    assert payload["kind"] == "idc_conditional_effect_ratio_step57"
    assert payload["formula_ast_normalized"] == 1
    assert ast["node_type"] == "fraction"
    assert row["full_id_claim_allowed"] == 1


def test_step57_idc_uses_frontdoor_joint_when_available():
    graph = admg_from_edges(["X", "M", "Y", "Z"], [("X", "M"), ("M", "Y"), ("Y", "Z")], [("X", "Y")])
    row = identify_conditional_effect(graph, "X", "Y", "Z").to_dict()
    joint = json.loads(row["joint_full_id_json"])
    assert row["identified"] is True
    assert joint["identified"] is True
    assert row["formula"].startswith("P_{do(X)}(Y | Z) =")
    assert row["full_id_claim_allowed"] == 1


def test_step57_idc_blocks_when_joint_not_identified():
    graph = admg_from_edges(["X", "Y", "Z"], [("X", "Y")], [("X", "Y")])
    row = identify_conditional_effect(graph, "X", "Y", "Z").to_dict()
    assert row["identified"] is False
    # Step 62+ may conservatively prune isolated Z first; the marginal query still blocks.
    assert row["identification_status"] in {"blocked_idc_joint_not_identified_step57", "blocked_idc_pruned_marginal_not_identified_step62"}
    assert row["pending_operator"] in {"identify_joint_yz_under_do_x_before_idc_ratio", "identify_marginal_y_under_do_x_after_idc_pruning"}
    assert row["full_id_claim_allowed"] == 1


def test_step57_idc_rejects_overlapping_sets():
    graph = admg_from_edges(["X", "Y"], [("X", "Y")], [])
    row = identify_conditional_effect(graph, "X", "Y", "Y").to_dict()
    assert row["identified"] is False
    assert row["identification_status"] == "invalid_idc_query"
    assert "OUTCOME_CONDITION_OVERLAP" in row["reason_codes"]


def test_step57_idc_scm_graph_adapter_and_status_flag():
    scm_graph = {"nodes": ["X", "Y", "Z"], "directed_edges": [["X", "Y"], ["Z", "Y"]], "bidirected_edges": []}
    row = identify_conditional_effect_from_scm_graph(scm_graph, "X", "Y", "Z").to_dict()
    flags = id_capability_flags()
    assert row["identified"] is True
    assert flags["id_full_idc_normalization_step57_implemented"] == 1
    assert flags["full_recursive_id_implemented"] == 1
