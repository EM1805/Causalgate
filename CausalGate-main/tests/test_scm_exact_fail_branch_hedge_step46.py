import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_algorithm import identify_effect
from scm_parts.id_status import id_capability_flags


def test_step46_formal_hedge_authority_comes_from_recursive_fail_branch():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    row = identify_effect(g, "X", "Y").to_dict()
    expr = json.loads(row["recursive_expression_json"])

    assert row["identifiable"] is False
    assert row["id_strategy"] == "blocked_formal_hedge_certificate"
    assert row["recursive_formula_source"] == "blocked_formal_hedge_certificate"
    assert row["recursive_blocker_class"] == "formal_hedge_certificate"
    assert row["formal_hedge_status"] == "formal_hedge_certified_recursive_fail_branch"
    assert row["formal_hedge_certified"] == 1
    assert row["identification_authority"] == "recursive_id_fail_branch"
    assert row["authority_status"] == "nonidentified_authoritative_formal_hedge"
    assert expr["formal_hedge_candidate"]["F"] == ["X", "Y"]
    assert expr["formal_hedge_candidate"]["F_prime"] == ["Y"]


def test_step46_identified_frontdoor_keeps_formal_hedge_neutral():
    g = admg_from_edges(
        ["X", "Z", "Y"],
        [("X", "Z"), ("Z", "Y")],
        [("X", "Y")],
    )
    row = identify_effect(g, "X", "Y", mediators=["Z"]).to_dict()

    assert row["identifiable"] is True
    assert row["id_strategy"] == "frontdoor_limited"
    assert row["recursive_identified"] == 1
    assert row["formal_hedge_certified"] == 0
    assert row["formal_hedge_status"] == "not_run_requires_recursive_id_fail_branch"
    assert row["identification_authority"] == "recursive_id"


def test_step46_identified_zero_effect_with_bidirected_noise_keeps_formal_hedge_neutral():
    g = admg_from_edges(
        ["X", "Z", "Y"],
        [("Z", "Y")],
        [("X", "Z")],
    )
    row = identify_effect(g, "X", "Y").to_dict()

    assert row["identifiable"] is True
    assert row["id_strategy"] == "no_directed_effect"
    assert row["formal_hedge_certified"] == 0
    assert row["formal_hedge_status"] == "not_run_requires_recursive_id_fail_branch"
    assert row["identification_authority"] == "recursive_id"


def test_step46_status_flags_present_but_full_id_still_not_claimed():
    flags = id_capability_flags()

    assert flags["exact_fail_branch_hedge_step46_implemented"] == 1
    assert flags["formal_hedge_authority_level"] == "certified_only_from_recursive_id_fail_branch_not_from_standalone_diagnostic"
    assert flags["formal_hedge_construction_implemented"] == 1
    assert flags["full_recursive_id_implemented"] == 1
