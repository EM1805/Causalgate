import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_algorithm import identify_effect, id_algorithm_summary
from scm_parts.id_status import id_capability_flags


def _roles(row):
    return json.loads(row["diagnostic_roles_json"])


def test_frontdoor_formula_is_shortcut_but_recursive_id_is_authority():
    g = admg_from_edges(
        ["X", "Z", "Y"],
        [("X", "Z"), ("Z", "Y")],
        [("X", "Y")],
    )
    row = identify_effect(g, "X", "Y", mediators=["Z"]).to_dict()

    assert row["identifiable"] is True
    assert row["id_strategy"] == "frontdoor_limited"
    assert row["recursive_identified"] == 1
    assert row["identification_authority"] == "recursive_id"
    assert row["authority_status"] == "identified_authoritative"
    assert row["authority_basis"].startswith("recursive_id_confirmed_frontdoor_limited:")

    roles = _roles(row)
    assert any(r["component"] == "frontdoor_criterion" and r["role"] == "diagnostic_shortcut" for r in roles)
    assert any(r["component"] == "recursive_id" and r["role"] == "authority" for r in roles)

    cert = json.loads(row["identification_certificate_json"])
    assert cert["identification_authority"] == "recursive_id"
    assert cert["authority_status"] == "identified_authoritative"


def test_backdoor_shortcut_is_authorized_by_recursive_base_case_when_available():
    g = admg_from_edges(
        ["Z", "X", "Y"],
        [("Z", "X"), ("Z", "Y"), ("X", "Y")],
        [],
    )
    row = identify_effect(g, "X", "Y", adjustment_set=["Z"], strategy_hint="backdoor").to_dict()

    assert row["identifiable"] is True
    assert row["id_strategy"] == "backdoor_adjustment"
    assert row["recursive_identified"] == 1
    assert row["identification_authority"] == "recursive_id"
    assert row["authority_status"] == "identified_authoritative"
    assert row["authority_basis"].startswith("recursive_id_confirmed_backdoor_adjustment:")

    roles = _roles(row)
    assert any(r["component"] == "backdoor_criterion" and r["role"] == "diagnostic_shortcut" for r in roles)
    assert any(r["component"] == "recursive_id" and r["role"] == "authority" for r in roles)


def test_formal_hedge_nonidentification_authority_is_explicit():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    row = identify_effect(g, "X", "Y").to_dict()

    assert row["identifiable"] is False
    assert row["formal_hedge_certified"] == 1
    assert row["identification_authority"] == "recursive_id_fail_branch"
    assert row["authority_status"] == "nonidentified_authoritative_formal_hedge"
    assert row["authority_basis"] == "formal_hedge_certificate"

    roles = _roles(row)
    assert any(r["component"] == "formal_hedge" and r["role"] == "nonidentification_authority" for r in roles)

    cert = json.loads(row["nonidentification_certificate_json"])
    assert cert["identification_authority"] == "recursive_id_fail_branch"
    assert cert["authority_status"] == "nonidentified_authoritative_formal_hedge"


def test_summary_exposes_authority_separation_capability_flag():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [])
    summary = id_algorithm_summary(g, [identify_effect(g, "X", "Y").to_dict()])
    flags = id_capability_flags()

    assert flags["diagnostic_authority_separation_step41_implemented"] == 1
    assert summary["diagnostic_authority_separation_step41_implemented"] == 1
    assert summary["id_authority_layer_level"] == "recursive_id_preferred_authority_with_backdoor_frontdoor_as_diagnostic_shortcuts"
