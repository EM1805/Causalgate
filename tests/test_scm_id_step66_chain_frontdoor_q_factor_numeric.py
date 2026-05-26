from __future__ import annotations

import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_full import full_id
from scm_parts.id_full_readiness import run_full_id_readiness_matrix
from scm_parts.id_status import id_capability_flags
from scm_parts.id_ast import P, Q
from scm_parts.q_factor_numeric import analyze_resolved_q_factor_ast
from scm_parts.symbolic_evaluator import evaluate_formula_ast_payload


def test_step66_chain_frontdoor_id7_formula_is_canonical():
    g = admg_from_edges(
        ["X", "Z1", "Z2", "Y"],
        [("X", "Z1"), ("Z1", "Z2"), ("Z2", "Y")],
        [("X", "Y")],
    )
    row = full_id(g, ["X"], ["Y"]).to_dict()
    assert row["identified"] is True
    assert row["primary_formula_authority"] == "id_canonical_formula_step60"
    assert row["canonical_formula_used_for_output"] == 1
    assert row["canonical_id7_carried_q_formula_used"] == 1
    assert "sum_{Z1,Z2}" in row["formula"]
    assert "P(Z1 | X)" in row["formula"]
    assert "P(Z2 | Z1)" in row["formula"]
    assert "P(Y | X_prime,Z1,Z2)" in row["formula"]
    payload = json.loads(row["canonical_formula_json"])
    assert payload["reason_codes"] == "CANONICAL_ID7_CHAIN_FRONTDOOR_CARRIED_Q_FORMULA_STEP66"


def test_step66_resolved_q_factor_ast_numeric_ready():
    ast = Q(["Y", "Z"], terms=[P(["Z"], given=["X"]), P(["Y"], given=["X", "Z"])], label="Q[Y,Z]")
    plan = analyze_resolved_q_factor_ast(ast).to_dict()
    assert plan["status"] == "q_factor_numeric_ready_step66"
    assert plan["numeric_ready"] == 1
    assert plan["route"] == "symbolic_numeric_resolved_q_factor_standardization"
    diag = evaluate_formula_ast_payload(ast, row={"treatment": "X", "outcome": "Y"}).to_dict()
    assert diag["numeric_estimator_ready"] == 1
    assert diag["symbolic_evaluator_status"] == "evaluable_formula_ast_resolved_q_factor_numeric_ready"


def test_step66_bare_q_factor_ast_stays_blocked():
    ast = Q(["Y", "Z"], label="Q[Y,Z]")
    plan = analyze_resolved_q_factor_ast(ast).to_dict()
    assert plan["status"] == "blocked_bare_q_factor_ast_step66"
    assert plan["numeric_ready"] == 0
    diag = evaluate_formula_ast_payload(ast, row={"treatment": "X", "outcome": "Y"}).to_dict()
    assert diag["symbolic_evaluator_status"] == "symbolic_formula_ast_q_factor_plan_only"
    assert diag["numeric_estimator_ready"] == 0


def test_step66_readiness_matrix_includes_chain_frontdoor_case():
    matrix = run_full_id_readiness_matrix()
    assert matrix["matrix_version"] == "id_full_readiness_matrix_v11_step80"
    assert matrix["all_passed"] == 1
    assert matrix["n_cases"] == 26
    rows = {r["case_id"]: r for r in matrix["rows"]}
    row = rows["id_chain_frontdoor_canonical_id7_step66"]
    assert row["passed"] is True
    assert row["canonical_id7_carried_q_formula_used"] == "1"


def test_step66_status_flags_present_without_full_id_claim():
    flags = id_capability_flags()
    assert flags["id_full_chain_frontdoor_id7_step66_implemented"] == 1
    assert flags["id_full_q_factor_numeric_step66_implemented"] == 1
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1
