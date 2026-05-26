from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scm_parts.admg import admg_from_edges
from scm_parts.id_algorithm import (
    identify_effect,
    identify_effect_set,
    id_algorithm_summary,
    recursive_id_expression_diagnostic,
    recursive_id_set_expression_diagnostic,
    recursive_subproblem_diagnostic,
)
from scm_parts.id_status import ID_ALGORITHM_VERSION


def test_step17_observed_dag_has_subproblem_plan() -> None:
    g = admg_from_edges(["X", "M", "Y"], [("X", "M"), ("M", "Y")])
    result = identify_effect(g, "X", "Y").to_dict()

    assert result["identifiable"] is True
    assert result["recursive_blocker_class"] == "none"
    assert result["recursive_pending_operator"] == "observed_dag_truncated_factorization"
    assert result["recursive_subproblem_count"] == 3
    assert result["recursive_formula_source"].startswith("identified_")

    plan = json.loads(result["recursive_subproblem_plan_json"])
    assert "subproblems" in plan
    assert all(sp["status"] == "observed_singleton_factor" for sp in plan["subproblems"])

    tree = json.loads(result["formula_tree_json"])
    assert tree["recursive_subproblem_plan"]["subproblems"]
    assert tree["recursive_expression"]["type"] == "truncated_factorization"
    assert tree["pending_operator"] == "observed_dag_truncated_factorization"


def test_step22_recursive_id_identifies_confounding_on_parent_covariate() -> None:
    # X <-> Z, X -> Y, Z -> Y is identifiable by recursive district
    # decomposition: sum_z P(Y | X,Z) P(Z). The older skeleton blocked this
    # before trying the district-decomposition branch.
    g = admg_from_edges(
        ["X", "Z", "Y"],
        [("X", "Y"), ("Z", "Y")],
        [("X", "Z")],
    )
    expr = recursive_id_expression_diagnostic(g, "X", "Y")
    result = identify_effect(g, "X", "Y").to_dict()

    assert expr.expression_identified is True
    assert expr.expression_status == "identified_recursive_district_decomposition"
    assert "P(Y | X,Z)" in expr.formula
    assert "P(Z)" in expr.formula

    assert result["identifiable"] is True
    assert result["id_strategy"] == "full_recursive_id_step2"
    assert result["id_algorithm_level"] == "recursive_id_step2_expression_and_hedge_diagnostic"
    assert result["recursive_status"] == "identified_full_recursive_id_step2"
    assert result["recursive_formula_source"] == "identified_recursive_district_decomposition"
    assert result["symbolic_formula_kind"] == "recursive_id_expression"

    tree = json.loads(result["formula_tree_json"])
    assert tree["recursive_expression"]["type"] == "recursive_district_decomposition"
    assert tree["recursive_expression"]["subexpressions"]

    summary = id_algorithm_summary(g, [result])
    assert summary["id_algorithm_version"] == ID_ALGORITHM_VERSION
    assert summary["full_recursive_id_step2_implemented"] == 1
    assert summary["n_full_recursive_step2_identified"] == 1


def test_step27_direct_latent_confounding_has_formal_hedge_certificate() -> None:
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    expr = recursive_id_expression_diagnostic(g, "X", "Y")
    result = identify_effect(g, "X", "Y").to_dict()

    assert expr.expression_identified is False
    assert expr.expression_status == "blocked_formal_hedge_certificate"
    assert expr.blocker_class == "formal_hedge_certificate"

    assert result["identifiable"] is False
    assert result["id_strategy"] == "blocked_formal_hedge_certificate"
    assert result["recursive_status"] == "blocked_formal_hedge_certificate"
    assert result["recursive_formula_source"] == "blocked_formal_hedge_certificate"
    assert result["recursive_blocker_class"] == "formal_hedge_certificate"
    assert result["recursive_pending_operator"] == "fail_id_or_construct_full_hedge_certificate"

    payload = json.loads(result["recursive_expression_json"])
    hedge = payload["formal_hedge_candidate"]
    assert hedge["certificate_status"] == "valid_limited_formal_hedge_certificate"
    assert hedge["F"] == ["X", "Y"]
    assert hedge["F_prime"] == ["Y"]
    assert hedge["treatment_in_F_minus_F_prime"] == ["X"]
    assert hedge["checks"]["F_prime_disjoint_from_treatment"] is True


def test_step17_direct_subproblem_diagnostic_is_json_stable() -> None:
    g = admg_from_edges(["X", "Y"], [("X", "Y")])
    diag = recursive_subproblem_diagnostic(g, "X", "Y")
    payload = json.loads(diag.subproblem_plan_json)
    chain = json.loads(diag.reduction_chain_json)

    assert diag.pending_operator == "observed_dag_truncated_factorization"
    assert len(payload["subproblems"]) == diag.subproblem_count
    assert chain["chain"][-1]["step"] == "subproblem_classification"


def test_step23_recursive_id_derives_frontdoor_without_supplied_mediator() -> None:
    g = admg_from_edges(
        ["X", "Z", "Y"],
        [("X", "Z"), ("Z", "Y")],
        [("X", "Y")],
    )
    expr = recursive_id_expression_diagnostic(g, "X", "Y")
    result = identify_effect(g, "X", "Y").to_dict()

    assert expr.expression_identified is True
    assert expr.expression_status == "identified_recursive_district_decomposition"
    assert "P(Z | X)" in expr.formula
    assert "sum_{X'}" in expr.formula
    assert "P(Y | X',Z)" in expr.formula

    assert result["identifiable"] is True
    assert result["id_strategy"] == "full_recursive_id_step3"
    assert result["id_algorithm_level"] == "recursive_id_step3_q_input_subdistrict_expression"
    assert result["recursive_status"] == "identified_full_recursive_id_step3"
    assert result["recursive_formula_source"] == "identified_recursive_district_decomposition"

    tree = json.loads(result["formula_tree_json"])
    assert "q_input_subdistrict_recursion" in json.dumps(tree["recursive_expression"])

    summary = id_algorithm_summary(g, [result])
    assert summary["id_algorithm_version"] == ID_ALGORITHM_VERSION
    assert summary["full_recursive_id_step3_implemented"] == 1
    assert summary["n_full_recursive_step3_identified"] == 1


def test_step24_public_set_valued_recursive_id_expression_api() -> None:
    # Full ID is set-valued. This checks the public set wrapper on the same
    # kind of latent district decomposition used by the single-edge route.
    g = admg_from_edges(
        ["X", "Z", "Y"],
        [("X", "Y"), ("Z", "Y")],
        [("X", "Z")],
    )
    expr = recursive_id_set_expression_diagnostic(g, treatments=["X"], outcomes=["Y", "Z"])

    assert expr.expression_identified is True
    assert expr.expression_status == "identified_recursive_district_decomposition"
    assert "P(Y | X,Z)" in expr.formula
    assert "P(Z)" in expr.formula
    assert "sum_{X'}" not in expr.formula

    payload = json.loads(expr.expression_json)
    assert payload["estimand"]["outcome"] == ["Y", "Z"]
    assert payload["estimand"]["intervention"] == ["X"]
    assert payload["type"] == "recursive_district_decomposition"


def test_step24_set_valued_recursive_id_rejects_overlap_and_missing_nodes() -> None:
    g = admg_from_edges(["X", "Y"], [("X", "Y")])

    overlap = recursive_id_set_expression_diagnostic(g, treatments=["X"], outcomes=["X"])
    assert overlap.expression_identified is False
    assert overlap.expression_status == "invalid_set_query"
    assert overlap.blocker_class == "invalid_set_query"
    assert "TREATMENT_OUTCOME_OVERLAP:X" in overlap.reason_codes

    missing = recursive_id_set_expression_diagnostic(g, treatments=["X"], outcomes=["Y", "MISSING"])
    assert missing.expression_identified is False
    assert missing.expression_status == "invalid_set_query"
    assert "QUERY_NODE_NOT_IN_GRAPH:MISSING" in missing.reason_codes


def test_step24_summary_reports_set_api_and_formula_hygiene() -> None:
    g = admg_from_edges(["X", "Y"], [("X", "Y")])
    summary = id_algorithm_summary(g, [])

    assert summary["id_algorithm_version"] == ID_ALGORITHM_VERSION
    assert summary["set_valued_recursive_expression_api_step24_implemented"] == 1
    assert summary["q_input_formula_alpha_renaming_step24_implemented"] == 1



def test_step27_q_factor_full_district_is_public_step4() -> None:
    # X is outside the latent district {Y,Z}. The remaining district in
    # G[V\X] is already a full district of G, so the q-factor can be read
    # safely from the observational chain rule.
    g = admg_from_edges(
        ["X", "Z", "Y"],
        [("X", "Z"), ("Z", "Y")],
        [("Z", "Y")],
    )
    expr = recursive_id_expression_diagnostic(g, "X", "Y")
    result = identify_effect(g, "X", "Y").to_dict()

    assert expr.expression_identified is True
    assert expr.expression_status == "identified_q_factor_full_district"
    assert "P(Z | X)" in expr.formula
    assert "P(Y | X,Z)" in expr.formula

    assert result["identifiable"] is True
    assert result["id_strategy"] == "full_recursive_id_step4"
    assert result["id_algorithm_level"] == "recursive_id_step4_full_district_q_factor"
    assert result["recursive_status"] == "identified_full_recursive_id_step4"
    assert result["recursive_formula_source"] == "identified_q_factor_full_district"

    summary = id_algorithm_summary(g, [result])
    assert summary["full_recursive_id_step4_implemented"] == 1
    assert summary["n_full_recursive_step4_identified"] == 1


def test_step27_identify_effect_set_uses_recursive_branch_metadata() -> None:
    g = admg_from_edges(
        ["X", "Z", "Y"],
        [("X", "Z"), ("Z", "Y")],
        [("Z", "Y")],
    )
    result = identify_effect_set(g, treatments=["X"], outcomes=["Y"]).to_dict()

    assert result["identifiable"] is True
    assert result["id_strategy"] == "full_recursive_id_step4"
    assert result["id_algorithm_level"] == "recursive_id_step4_full_district_q_factor"
    assert "P_{do(X)}(Y)" in result["estimand_formula"]
    assert result["recursive_formula_source"] == "identified_q_factor_full_district"


def test_step28_localized_formal_hedge_certificate_inside_district_decomposition() -> None:
    # W is a separate observed parent of Y. The full graph is not one district,
    # but the recursive subproblem for {Y} fails inside the local district
    # F={X,Y}, F'={Y}. Step 28 should certify that hedge instead of returning
    # only a generic recursive-subproblem block.
    g = admg_from_edges(["W", "X", "Y"], [("W", "Y"), ("X", "Y")], [("X", "Y")])
    expr = recursive_id_expression_diagnostic(g, "X", "Y")
    result = identify_effect(g, "X", "Y").to_dict()

    assert expr.expression_identified is False
    assert expr.expression_status == "blocked_formal_hedge_certificate"
    assert expr.blocker_class == "formal_hedge_certificate"
    assert expr.pending_operator == "fail_id_or_construct_full_hedge_certificate"

    payload = json.loads(expr.expression_json)
    hedge = payload["formal_hedge_candidate"]
    assert hedge["F"] == ["X", "Y"]
    assert hedge["F_prime"] == ["Y"]
    assert hedge["scope"] == "localized_full_district_strict_g_without_x_district"
    assert hedge["checks"]["localized_certificate"] is True
    assert hedge["treatment_in_F_minus_F_prime"] == ["X"]

    assert result["identifiable"] is False
    assert result["recursive_status"] == "blocked_formal_hedge_certificate"
    assert result["recursive_blocker_class"] == "formal_hedge_certificate"
    assert result["recursive_formula_source"] == "blocked_formal_hedge_certificate"

    summary = id_algorithm_summary(g, [result])
    assert summary["id_algorithm_version"] == ID_ALGORITHM_VERSION
    assert summary["localized_hedge_certificate_step28_implemented"] == 1
    assert summary["n_formal_hedge_candidates"] == 1


def test_step29_multi_intervention_q_input_recursion_is_auditable() -> None:
    # Full ID is set-valued in both X and Y. Step 29 makes the existing safe
    # q-input recursion explicit for a treatment set: both X1 and X2 are
    # observational copies summed inside Q[X1,X2,Y], while the fixed do-values
    # remain in the mediator factor P(Z | X1,X2).
    g = admg_from_edges(
        ["X1", "X2", "Z", "Y"],
        [("X1", "Z"), ("X2", "Z"), ("Z", "Y")],
        [("X1", "Y"), ("X2", "Y"), ("X1", "X2")],
    )

    expr = recursive_id_set_expression_diagnostic(g, treatments=["X1", "X2"], outcomes=["Y"])
    result = identify_effect_set(g, treatments=["X1", "X2"], outcomes=["Y"]).to_dict()

    assert expr.expression_identified is True
    assert expr.expression_status == "identified_recursive_district_decomposition"
    assert "sum_{X1',X2'}" in expr.formula
    assert "P(Y | X1',X2',Z)" in expr.formula
    assert "P(Z | X1,X2)" in expr.formula
    assert "Q_INPUT_MULTI_INTERVENTION_SUBDISTRICT_RECURSION_IDENTIFIED_STEP29" in expr.expression_json

    payload = json.loads(expr.expression_json)
    q_payload = [sp for sp in payload["subexpressions"] if "q_input_subdistrict_recursion" in json.dumps(sp)][0]
    inner = q_payload["expression"]["subexpressions"][0]
    assert inner["multi_intervention_q_input"] is True
    assert inner["alpha_renamed_interventions"] == ["X1'", "X2'"]

    assert result["identifiable"] is True
    assert result["id_strategy"] == "full_recursive_id_step3"
    assert result["id_algorithm_level"] == "recursive_id_step3_q_input_subdistrict_expression"

    summary = id_algorithm_summary(g, [result])
    assert summary["id_algorithm_version"] == ID_ALGORITHM_VERSION
    assert summary["set_valued_q_input_recursion_step29_implemented"] == 1
    assert summary["n_q_input_multi_intervention_step29"] == 1
