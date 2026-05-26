from scm_parts.admg import admg_from_edges
from scm_parts.id_full import identify_conditional_effect
from scm_parts.idc_rules import idc_pruning_diagnostic
from scm_parts.id_full_readiness import run_full_id_readiness_matrix


def test_idc_prunes_isolated_condition_to_marginal_effect_step62():
    graph = admg_from_edges(["X", "Y", "Z"], [("X", "Y")])
    result = identify_conditional_effect(graph, ["X"], ["Y"], ["Z"]).to_dict()
    assert result["identified"] is True
    assert result["identification_status"] == "identified_idc_pruned_to_marginal_effect_step62"
    assert result["idc_pruning_status"] == "idc_pruning_all_conditions_removed_step62"
    assert result["idc_pruned_conditions"] == "Z"
    assert result["idc_effective_conditions"] == ""
    assert "P_{do(X)}(Y | Z) = P_{do(X)}(Y)" in result["formula"]
    assert result["full_id_claim_allowed"] == 1


def test_idc_keeps_condition_connected_to_outcome_step62():
    graph = admg_from_edges(["X", "Y", "Z"], [("X", "Y"), ("Z", "Y")])
    pruning = idc_pruning_diagnostic(graph, ["X"], ["Y"], ["Z"])
    assert pruning.status == "idc_pruning_no_conditions_removed_step62"
    assert pruning.kept_conditions == ("Z",)
    assert pruning.pruned_conditions == ()


def test_idc_partially_prunes_disconnected_condition_step62():
    graph = admg_from_edges(["X", "Y", "W", "Z"], [("X", "Y"), ("W", "Y")])
    result = identify_conditional_effect(graph, ["X"], ["Y"], ["W", "Z"]).to_dict()
    assert result["identified"] is True
    assert result["identification_status"] == "identified_idc_ratio_over_identified_joint_step57"
    assert result["idc_pruning_status"] == "idc_pruning_partial_conditions_removed_step62"
    assert result["idc_effective_conditions"] == "W"
    assert result["idc_pruned_conditions"] == "Z"
    assert "P_{do(X)}(Y | W,Z) = P_{do(X)}(Y | W)" in result["formula"]


def test_step62_readiness_matrix_passes():
    matrix = run_full_id_readiness_matrix()
    assert matrix["matrix_version"] == "id_full_readiness_matrix_v11_step80"
    assert matrix["n_cases"] == 26
    assert matrix["n_passed"] == 26
    assert matrix["all_passed"] == 1
