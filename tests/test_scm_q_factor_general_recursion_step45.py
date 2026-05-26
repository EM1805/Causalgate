import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_algorithm import id_algorithm_summary, identify_effect
from scm_parts.id_status import id_capability_flags
from scm_parts.q_factor import identify_q_factor


def test_step45_q_factor_delegates_active_x_subdistrict_to_recursive_hedge():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    qdiag = identify_q_factor(
        g,
        ["Y"],
        containing_district=["X", "Y"],
        outcome_set=["Y"],
        intervention_set=["X"],
    )
    payload = json.loads(qdiag.q_factor_json)
    trace = json.loads(qdiag.q_factor_recursive_trace_json)["trace"]

    assert qdiag.q_factor_identified is False
    assert qdiag.q_factor_status == "blocked_general_q_input_recursion_formal_hedge"
    assert payload["type"] == "general_q_input_recursion_formal_hedge"
    assert payload["rule"] == "general_q_input_recursive_subproblem_step45"
    assert payload["q_input"] == "Q[X,Y]"
    assert payload["recursive_status"] == "blocked_formal_hedge_certificate"
    assert payload["formal_hedge_candidate"]["F"] == ["X", "Y"]
    assert payload["formal_hedge_candidate"]["F_prime"] == ["Y"]
    assert any(step["step"] == "formal_hedge_certificate" for step in trace)
    assert '"node_type":"hedge_fail"' in qdiag.q_factor_ast_json


def test_step45_q_factor_safe_branch_still_identifies_frontdoor_subdistrict():
    g = admg_from_edges(["X", "Z", "Y"], [("X", "Z"), ("Z", "Y")], [("X", "Y")])
    qdiag = identify_q_factor(
        g,
        ["Y"],
        containing_district=["X", "Y"],
        outcome_set=["Y"],
        intervention_set=["X", "Z"],
    )

    assert qdiag.q_factor_identified is True
    assert qdiag.q_factor_status == "identified_safe_subdistrict_q_input"
    assert "P(Y | X',Z)" in qdiag.q_factor_formula
    assert "Q_INPUT_SUBDISTRICT_RECURSION_IDENTIFIED_STEP40" in qdiag.q_factor_reason_codes


def test_step45_q_factor_general_recursion_can_be_disabled_for_legacy_blocker():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    qdiag = identify_q_factor(
        g,
        ["Y"],
        containing_district=["X", "Y"],
        outcome_set=["Y"],
        intervention_set=["X"],
        enable_general_recursion=False,
    )

    assert qdiag.q_factor_identified is False
    assert qdiag.q_factor_status == "blocked_q_input_active_x_remains_ancestor"
    assert qdiag.q_factor_blocker == "X"


def test_step45_capability_flags_and_summary_are_reported():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [])
    row = identify_effect(g, "X", "Y").to_dict()
    summary = id_algorithm_summary(g, [row])
    flags = id_capability_flags()

    assert flags["q_factor_general_recursion_step45_implemented"] == 1
    assert summary["q_factor_general_recursion_step45_implemented"] == 1
    assert "q_factor_general_recursion_step45" in summary["id_algorithm_status"]
    assert "n_q_factor_general_q_input_recursion_step45" in summary
