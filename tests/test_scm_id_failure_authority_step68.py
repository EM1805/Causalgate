from __future__ import annotations

import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_full import full_id, identify_conditional_effect
from scm_parts.id_full_readiness import run_full_id_readiness_matrix
from scm_parts.id_status import id_capability_flags


def test_step68_full_id_failures_use_certificate_authority_not_delegate():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    row = full_id(g, ["X"], ["Y"]).to_dict()
    assert row["identified"] is False
    assert row["identification_status"] == "blocked_formal_hedge_certificate"
    assert row["primary_formula_authority"] == "id_failure_certificate_step68"
    assert row["failure_certificate_status"] == "formal_hedge_certified_step68"
    assert row["failure_certified"] == 1
    assert row["formula_ast_json"]
    ast = json.loads(row["formula_ast_json"])
    assert ast["node_type"] == "hedge_fail"


def test_step68_invalid_and_cyclic_queries_use_rejection_authority():
    cyclic = admg_from_edges(["X", "Y"], [("X", "Y"), ("Y", "X")])
    row = full_id(cyclic, ["X"], ["Y"]).to_dict()
    assert row["identified"] is False
    assert row["primary_formula_authority"] == "id_failure_certificate_step68"
    assert row["failure_certificate_status"] == "rejected_directed_cycle_step68"

    valid = admg_from_edges(["X", "Y"], [("X", "Y")])
    bad = full_id(valid, ["X"], ["X"]).to_dict()
    assert bad["identified"] is False
    assert bad["primary_formula_authority"] == "id_failure_certificate_step68"
    assert bad["failure_certificate_status"] == "rejected_invalid_query_step68"


def test_step68_idc_joint_block_uses_failure_authority_inside_joint_full_id_json():
    g = admg_from_edges(["X", "Y", "Z"], [("X", "Y"), ("Z", "Y")], [("X", "Y")])
    row = identify_conditional_effect(g, ["X"], ["Y"], ["Z"]).to_dict()
    assert row["identified"] is False
    assert row["identification_status"] == "blocked_idc_joint_not_identified_step57"
    joint = json.loads(row["joint_full_id_json"])
    assert joint["primary_formula_authority"] == "id_failure_certificate_step68"
    assert joint["failure_certificate_status"] == "formal_hedge_certified_step68"


def test_step68_readiness_counts_no_identified_delegate_formula_authority():
    matrix = run_full_id_readiness_matrix()
    assert matrix["matrix_version"] == "id_full_readiness_matrix_v11_step80"
    assert matrix["all_passed"] == 1
    assert matrix["n_cases"] == 26
    assert matrix["n_delegated_formula_authority"] == 0
    assert matrix["n_canonical_formula_authority"] == 17
    assert matrix["n_failure_certificate_authority"] >= 6
    assert matrix["full_id_claim_allowed"] == 1


def test_step68_status_flags_present_without_full_id_claim():
    flags = id_capability_flags()
    assert flags["id_full_failure_authority_separation_step68_implemented"] == 1
    assert flags["id_full_readiness_matrix_version"] == "id_full_readiness_matrix_v11_step80"
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1
