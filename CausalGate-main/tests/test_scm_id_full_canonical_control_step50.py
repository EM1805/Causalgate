import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_full import ID_FULL_INTERFACE_VERSION, full_id
from scm_parts.id_status import id_capability_flags


def _control(result):
    return json.loads(result["canonical_control_json"])


def test_step50_observed_dag_exposes_id6_control_terminal():
    graph = admg_from_edges(["X", "Y"], [("X", "Y")], [])
    result = full_id(graph, "X", "Y").to_dict()
    control = _control(result)
    assert result["interface_version"] == ID_FULL_INTERFACE_VERSION
    assert result["identified"] is True
    assert result["canonical_terminal_rule"] == "ID-6"
    assert control["terminal_rule"] == "ID-6"
    assert "ID-6" in control["applied_rules"]
    assert result["full_id_claim_allowed"] == 1


def test_step50_frontdoor_shape_exposes_id4_and_id7_control_path():
    graph = admg_from_edges(["X", "Z", "Y"], [("X", "Z"), ("Z", "Y")], [("X", "Y")])
    result = full_id(graph, "X", "Y").to_dict()
    control = _control(result)
    assert result["identified"] is True
    assert "ID-4" in control["applied_rules"]
    assert "ID-7" in control["applied_rules"]
    assert "ID-7" in result["canonical_rules"]
    assert control["n_steps"] >= 2


def test_step50_direct_confounding_keeps_id5_terminal_and_hedge_delegate():
    graph = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    result = full_id(graph, "X", "Y").to_dict()
    control = _control(result)
    assert result["identified"] is False
    assert result["blocker_class"] == "formal_hedge_certificate"
    assert result["canonical_terminal_rule"] == "ID-5"
    assert control["terminal_rule"] == "ID-5"
    assert "ID-5" in result["canonical_rules"]


def test_step50_status_flags_are_set_without_full_id_claim():
    flags = id_capability_flags()
    assert flags["id_full_public_facade_step49_implemented"] == 1
    assert flags["id_full_canonical_control_flow_step50_implemented"] == 1
    assert flags["full_recursive_id_implemented"] == 1
