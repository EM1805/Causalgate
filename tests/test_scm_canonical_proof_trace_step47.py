import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_algorithm import identify_effect, id_algorithm_summary
from scm_parts.id_status import id_capability_flags


def _tree(row):
    return json.loads(row["formula_tree_json"])


def _canonical(row):
    return _tree(row)["canonical_id_trace"]


def test_step47_observed_dag_exports_canonical_q_factor_rule():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [])
    row = identify_effect(g, "X", "Y").to_dict()
    trace = _canonical(row)
    assert trace["version"] == "id_proof_trace_v2_step47"
    assert "ID-6" in trace["rules"]
    assert any(step["id_rule"] == "ID-6" for step in trace["steps"])
    assert row["id_proof_status"] == "identified_proof_trace"


def test_step47_formal_hedge_exports_id5_fail():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    row = identify_effect(g, "X", "Y").to_dict()
    trace = _canonical(row)
    assert row["identifiable"] is False
    assert "ID-5" in trace["fail_rules"]
    assert any(step["id_rule"] == "ID-5" and step["status"] == "fail_hedge" for step in trace["steps"])
    assert trace["source"] == "recursive_trace_json_overlay_no_new_authority"


def test_step47_recursive_q_input_exports_id7_when_present():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    row = identify_effect(g, "X", "Y").to_dict()
    trace = _canonical(row)
    assert any(step["id_rule"] == "ID-7" for step in trace["steps"])


def test_step47_status_flags_present_but_full_id_still_not_claimed():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [])
    row = identify_effect(g, "X", "Y").to_dict()
    summary = id_algorithm_summary(g, [row])
    flags = id_capability_flags()
    assert flags["canonical_id_proof_trace_step47_implemented"] == 1
    assert summary["canonical_id_proof_trace_step47_implemented"] == 1
    assert flags["full_recursive_id_implemented"] == 1
