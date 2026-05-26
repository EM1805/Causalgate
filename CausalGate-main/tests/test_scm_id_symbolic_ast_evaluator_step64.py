from __future__ import annotations

import json

from scm_parts.id_ast import Do, Fraction, HedgeFail, P, Product, Q, Sum
from scm_parts.symbolic_evaluator import (
    SYMBOLIC_EVALUATOR_VERSION,
    evaluate_formula_ast_payload,
    evaluate_symbolic_formula_row,
)


def test_step64_ast_sum_product_do_numeric_ready():
    ast = Do(
        ["X"],
        Sum(["Z"], Product([P(["Z"], given=["X"]), P(["Y"], given=["X", "Z"])])),
        label="canonical_g_formula_ast",
    )
    diag = evaluate_formula_ast_payload(ast, row={"treatment": "X", "outcome": "Y"}).to_dict()
    assert diag["symbolic_evaluator_status"] == "evaluable_formula_ast_probability_sum_product_do"
    assert diag["formula_evaluable"] == 1
    assert diag["numeric_estimator_ready"] == 1
    assert diag["estimator_route"] == "symbolic_numeric_ast_standardization"
    assert "sum" in diag["formula_ast_node_types"]
    assert "product" in diag["formula_ast_node_types"]
    assert diag["formula_ast_evaluator_version"] == SYMBOLIC_EVALUATOR_VERSION


def test_step64_ast_fraction_routes_to_step65_numeric_ready_when_resolved():
    joint = P(["Y", "W"], interventions=["X"])
    ast = Fraction(joint, Sum(["Y"], joint), label="idc_ratio_ast")
    diag = evaluate_formula_ast_payload(ast, row={"treatment": "X", "outcome": "Y"}).to_dict()
    assert diag["symbolic_evaluator_status"] == "evaluable_formula_ast_idc_fraction_numeric_ready"
    assert diag["formula_evaluable"] == 1
    assert diag["numeric_estimator_ready"] == 1
    assert diag["estimator_route"] == "symbolic_numeric_idc_fraction_ratio"


def test_step64_ast_q_factor_with_resolved_children_routes_numeric_ready_step66():
    ast = Q(["Y", "Z"], terms=[P(["Z"], given=["X"]), P(["Y"], given=["X", "Z"])], label="Q[Y,Z]")
    diag = evaluate_formula_ast_payload(ast, row={"treatment": "X", "outcome": "Y"}).to_dict()
    assert diag["symbolic_evaluator_status"] == "evaluable_formula_ast_resolved_q_factor_numeric_ready"
    assert diag["formula_evaluable"] == 1
    assert diag["numeric_estimator_ready"] == 1
    assert diag["estimator_route"] == "symbolic_numeric_resolved_q_factor_standardization"
    assert diag["formula_ast_q_factors"]


def test_step64_bare_q_factor_stays_symbolic_only():
    ast = Q(["Y", "Z"], label="Q[Y,Z]")
    diag = evaluate_formula_ast_payload(ast, row={"treatment": "X", "outcome": "Y"}).to_dict()
    assert diag["symbolic_evaluator_status"] == "symbolic_formula_ast_q_factor_plan_only"
    assert diag["formula_evaluable"] == 1
    assert diag["numeric_estimator_ready"] == 0
    assert diag["blocker"] == "BARE_Q_FACTOR_WITHOUT_EXPANDED_TERMS"


def test_step64_ast_hedge_fail_blocks_numeric_evaluation():
    ast = HedgeFail(["X", "Y"], ["Y"], roots=["Y"], label="formal_hedge_certificate")
    diag = evaluate_formula_ast_payload(ast, row={"treatment": "X", "outcome": "Y"}).to_dict()
    assert diag["symbolic_evaluator_status"] == "blocked_formula_ast_hedge_failure"
    assert diag["formula_evaluable"] == 0
    assert diag["numeric_estimator_ready"] == 0
    assert diag["blocker"] == "FORMAL_HEDGE_OR_ID_FAILURE_AST"


def test_step64_row_fallback_uses_formula_ast_json_when_symbolic_json_missing():
    ast = Do(["X"], P(["Y"], given=["X"]), label="simple_ast")
    diag = evaluate_symbolic_formula_row({"formula_ast_json": json.dumps(ast.to_dict()), "treatment": "X", "outcome": "Y"}).to_dict()
    assert diag["formula_ast_present"] == 1
    assert diag["symbolic_evaluator_status"] == "evaluable_formula_ast_probability_sum_product_do"
