import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_canonical_formula import canonical_id_formula_diagnostic
from scm_parts.id_full import full_id, identify_conditional_effect
from scm_parts.id_full_readiness import run_full_id_readiness_matrix
from scm_parts.id_status import id_capability_flags


def _contextual_frontdoor_graph():
    return admg_from_edges(
        ["X", "Z", "Y", "W"],
        [("X", "Z"), ("Z", "Y"), ("W", "Y")],
        [("X", "Y")],
    )


def test_step60_contextual_frontdoor_joint_query_has_canonical_id7_authority():
    graph = _contextual_frontdoor_graph()
    diag = canonical_id_formula_diagnostic(graph, ["X"], ["Y", "W"])
    payload = json.loads(diag.expression_json)

    assert diag.identified is True
    assert diag.status == "identified_canonical_id7_contextual_frontdoor_carried_q_formula_step60"
    assert diag.terminal_rule == "ID-7"
    assert diag.id7_carried_q_formula_used == 1
    assert diag.formula == "sum_{Z} P(W) * P(Z | X) * sum_{X_prime} P(X_prime | W) * P(Y | W,X_prime,Z)"
    assert payload["formula_authority"] == "id_canonical_formula_step60"
    assert payload["formula_ast_normalized"] == 1


def test_step60_full_id_uses_contextual_id7_for_joint_outcome():
    graph = _contextual_frontdoor_graph()
    row = full_id(graph, ["X"], ["Y", "W"]).to_dict()

    assert row["identified"] is True
    assert row["primary_formula_authority"] == "id_canonical_formula_step60"
    assert row["canonical_formula_used_for_output"] == 1
    assert row["canonical_id7_carried_q_formula_used"] == 1
    assert "P_{do(X)}(Y,W)" in row["formula"]
    assert "P(X_prime | W)" in row["formula"]
    assert row["full_id_claim_allowed"] == 1


def test_step60_idc_frontdoor_joint_condition_no_longer_delegates_joint():
    graph = _contextual_frontdoor_graph()
    row = identify_conditional_effect(graph, ["X"], ["Y"], ["W"]).to_dict()
    joint = json.loads(row["joint_full_id_json"])

    assert row["identified"] is True
    assert row["identification_status"] == "identified_idc_ratio_over_identified_joint_step57"
    assert joint["primary_formula_authority"] == "id_canonical_formula_step60"
    assert joint["canonical_formula_used_for_output"] == 1
    assert "P(X_prime | W)" in row["formula"]


def test_step60_readiness_matrix_tracks_contextual_id7_and_reduces_delegate_count():
    matrix = run_full_id_readiness_matrix()
    rows = {row["case_id"]: row for row in matrix["rows"]}

    assert matrix["matrix_version"] == "id_full_readiness_matrix_v11_step80"
    assert matrix["all_passed"] == 1
    assert matrix["n_cases"] >= 24
    assert matrix["n_delegated_formula_authority"] <= 6
    assert matrix["n_canonical_formula_authority"] >= 12
    assert rows["id_contextual_frontdoor_canonical_id7_step60"]["primary_formula_authority"] == "id_canonical_formula_step60"
    assert rows["id_contextual_frontdoor_canonical_id7_step60"]["canonical_id7_carried_q_formula_used"] == "1"
    assert rows["idc_frontdoor_joint_condition"]["joint_primary_formula_authority"] == "id_canonical_formula_step60"


def test_step60_status_flag_present_without_full_id_claim():
    flags = id_capability_flags()
    assert flags["id_full_contextual_id7_carried_q_formula_step60_implemented"] == 1
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1
