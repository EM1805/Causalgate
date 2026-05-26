from scm_parts.admg import admg_from_edges
from scm_parts.do_calculus import (
    do_calculus_diagnostic,
    rule1_insertion_deletion_observation,
    rule2_action_observation_exchange,
    rule3_insertion_deletion_action,
)
from scm_parts.id_algorithm import identify_effect


def test_do_calculus_rules_are_explicit_and_audited():
    g = admg_from_edges(["x", "z", "y"], [("x", "z"), ("z", "y")])
    r1 = rule1_insertion_deletion_observation(g, y="y", x="x", z="z")
    r2 = rule2_action_observation_exchange(g, y="y", x="x", z="z")
    r3 = rule3_insertion_deletion_action(g, y="y", x="x", z="z")
    assert r1.rule == "rule1_observation_insertion_deletion"
    assert r2.rule == "rule2_action_observation_exchange"
    assert r3.rule == "rule3_action_insertion_deletion"
    assert r1.status in {"applicable", "blocked"}
    assert r2.status in {"applicable", "blocked"}
    assert r3.status in {"applicable", "blocked"}
    assert "P(" in r1.expression_before


def test_id_result_carries_do_calculus_audit_fields():
    g = admg_from_edges(["x", "z", "y"], [("x", "z"), ("z", "y")])
    row = identify_effect(g, "x", "y", mediators=["z"]).to_dict()
    assert row["do_calculus_status"] in {"rules_applicable_audit_only", "no_rule_applicable_audit_only"}
    assert "rules" in row["do_calculus_rule_trace_json"]
    assert row["do_calculus_reason_codes"] == "DO_CALCULUS_RULES_EXPLICIT_AUDIT_ONLY"


def test_do_calculus_diagnostic_does_not_authorize_full_id_by_itself():
    g = admg_from_edges(["x", "y"], [("x", "y")], [("x", "y")])
    diag = do_calculus_diagnostic(g, "x", "y")
    assert diag.do_calculus_status in {"rules_applicable_audit_only", "no_rule_applicable_audit_only"}
    assert diag.reason_codes == "DO_CALCULUS_RULES_EXPLICIT_AUDIT_ONLY"
