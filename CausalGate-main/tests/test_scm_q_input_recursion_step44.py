import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_algorithm import identify_effect, id_algorithm_summary
from scm_parts.id_recursive_expression import recursive_id_set_expression_diagnostic
from scm_parts.id_status import id_capability_flags


def test_direct_confounded_effect_uses_structured_q_input_recursion_before_hedge():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    expr = recursive_id_set_expression_diagnostic(g, ["X"], ["Y"])
    payload = json.loads(expr.expression_json)
    trace = json.loads(expr.trace_json)["trace"]

    assert expr.expression_identified is False
    assert expr.expression_status == "blocked_formal_hedge_certificate"
    assert payload["type"] == "general_q_input_recursion_formal_hedge"
    assert payload["subexpressions"][0]["q_input"] == "Q[X,Y]"
    assert payload["subexpressions"][0]["rule"] == "general_q_input_recursive_subproblem_step44"
    assert any(step["step"] == "q_input_general_recursion_step44" for step in trace)


def test_identify_effect_preserves_formal_hedge_certificate_after_step44():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    row = identify_effect(g, "X", "Y").to_dict()
    payload = json.loads(row["recursive_expression_json"])

    assert row["identifiable"] is False
    assert row["formal_hedge_certified"] == 1
    assert row["recursive_blocker_class"] == "formal_hedge_certificate"
    assert payload["type"] == "general_q_input_recursion_formal_hedge"


def test_frontdoor_still_identified_and_not_marked_as_hedge():
    g = admg_from_edges(["X", "Z", "Y"], [("X", "Z"), ("Z", "Y")], [("X", "Y")])
    row = identify_effect(g, "X", "Y").to_dict()

    assert row["identifiable"] is True
    assert row["formal_hedge_certified"] == 0
    assert "frontdoor" in row["id_strategy"] or "recursive" in row["identification_authority"]


def test_step44_capability_flags_are_reported():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [])
    summary = id_algorithm_summary(g, [identify_effect(g, "X", "Y").to_dict()])
    flags = id_capability_flags()

    assert flags["general_q_input_recursion_step44_implemented"] == 1
    assert flags["full_recursive_id_step5_partial_implemented"] == 1
    assert summary["general_q_input_recursion_step44_implemented"] == 1
    assert "q_input_recursion_step44" in summary["id_algorithm_status"]
