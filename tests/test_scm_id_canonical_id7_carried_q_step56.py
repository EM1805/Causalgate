import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_canonical_formula import canonical_id_formula_diagnostic
from scm_parts.id_full import full_id
from scm_parts.id_status import id_capability_flags


def test_step56_frontdoor_formula_owned_by_canonical_id7():
    graph = admg_from_edges(["X", "Z", "Y"], [("X", "Z"), ("Z", "Y")], [("X", "Y")])
    diag = canonical_id_formula_diagnostic(graph, "X", "Y")
    payload = json.loads(diag.expression_json)
    trace = json.loads(diag.trace_json)["trace"]
    assert diag.identified is True
    assert diag.status == "identified_canonical_id7_frontdoor_carried_q_formula_step60"
    assert diag.terminal_rule == "ID-7"
    assert diag.id7_carried_q_formula_used == 1
    assert diag.formula == "sum_{Z} P(Z | X) * sum_{X_prime} P(X_prime) * P(Y | X_prime,Z)"
    assert payload["formula_ast_normalized"] == 1
    assert any(t["rule"] == "ID-7" and t["status"] == "identified_frontdoor_carried_q_formula" for t in trace)


def test_step56_full_id_uses_canonical_frontdoor_but_no_full_id_claim():
    graph = admg_from_edges(["X", "Z", "Y"], [("X", "Z"), ("Z", "Y")], [("X", "Y")])
    row = full_id(graph, "X", "Y").to_dict()
    assert row["identified"] is True
    assert row["primary_formula_authority"] == "id_canonical_formula_step60"
    assert row["canonical_formula_used_for_output"] == 1
    assert row["canonical_id7_carried_q_formula_used"] == 1
    assert row["formula"] == "P_{do(X)}(Y) = sum_{Z} P(Z | X) * sum_{X_prime} P(X_prime) * P(Y | X_prime,Z)"
    assert row["full_id_claim_allowed"] == 1


def test_step56_direct_confounding_remains_blocked():
    graph = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    diag = canonical_id_formula_diagnostic(graph, "X", "Y")
    row = full_id(graph, "X", "Y").to_dict()
    assert diag.identified is False
    assert diag.status == "blocked_canonical_id5_fail_branch_step59"
    assert diag.blocker_class == "canonical_fail_branch"
    assert row["identified"] is False
    assert row["primary_formula_authority"] == "id_failure_certificate_step68"
    assert row["failure_certificate_status"] == "formal_hedge_certified_step68"
    assert row["failure_certified"] == 1
    assert row["full_id_claim_allowed"] == 1


def test_step56_q_factor_keeps_outside_predecessors():
    graph = admg_from_edges(["X", "A", "Y"], [("X", "A"), ("A", "Y")], [("A", "Y")])
    diag = canonical_id_formula_diagnostic(graph, "X", "Y")
    assert diag.identified is True
    assert diag.formula == "sum_{A} P(A | X) * P(Y | X,A)"


def test_step56_status_flag_present():
    flags = id_capability_flags()
    assert flags["id_full_canonical_id7_carried_q_formula_step56_implemented"] == 1
    assert flags["full_recursive_id_implemented"] == 1
