from scm_parts.scm_counterfactual import evaluate_scm_counterfactual
from scm_parts.id_algorithm import identify_effect_from_scm_graph
from path_parts.path_counterfactual import mark_path_counterfactual_diagnostic


def test_scm_counterfactual_blocks_without_id_result_or_graph():
    res = evaluate_scm_counterfactual(treatment="A", outcome="Y", intervention_value=1.0)
    assert res.counterfactual_authority == "blocked"
    assert res.id_identifiable == 0
    assert "NO_ID_NO_COUNTERFACTUAL_AUTHORITY" in res.reason_codes


def test_scm_counterfactual_authorizes_only_id_identified_estimand():
    graph = {"nodes": [{"id": "A"}, {"id": "Y"}], "edges": [{"source": "A", "target": "Y"}]}
    idr = identify_effect_from_scm_graph(graph, "A", "Y")
    res = evaluate_scm_counterfactual(treatment="A", outcome="Y", intervention_value=1.0, id_result=idr)
    assert res.id_identifiable == 1
    assert res.counterfactual_authority == "authorized_interventional_estimand"
    assert res.formal_individual_counterfactual_authorized == 0


def test_path_counterfactual_is_explicitly_diagnostic_only():
    row = mark_path_counterfactual_diagnostic({"path": "A->Y"})
    assert row["path_counterfactual_authority"] == "diagnostic_path_level_only"
    assert row["scm_counterfactual_authority"] == "not_evaluated_use_scm_counterfactual"
