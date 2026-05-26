import json

from scm_parts.admg import admg_from_edges
from scm_parts.do_calculus import (
    SET_VALUED_DO_CALCULUS_VERSION,
    rule1_insertion_deletion_observation,
    rule2_action_observation_exchange,
)


def test_set_valued_rule2_accepts_lists_and_carries_ast_sets():
    g = admg_from_edges(["x1", "x2", "z1", "z2", "y"], [("x1", "z1"), ("x2", "z2"), ("z1", "y"), ("z2", "y")])
    diag = rule2_action_observation_exchange(g, y=["y"], x=["x1", "x2"], z=["z1", "z2"])
    assert diag.set_valued == 1
    assert diag.set_rule_version == SET_VALUED_DO_CALCULUS_VERSION
    assert diag.x_set == "x1|x2"
    assert diag.z_set == "z1|z2"
    payload = json.loads(diag.expression_before_ast_json)
    assert payload["outcomes"] == ["y"]
    assert payload["interventions"] == ["x1", "x2", "z1", "z2"]


def test_set_valued_rule_blocks_if_any_pair_has_open_path():
    g = admg_from_edges(["x", "z1", "z2", "y"], [("z1", "y")])
    diag = rule1_insertion_deletion_observation(g, y=["y"], x=["x"], z=["z1", "z2"])
    assert diag.set_valued == 1
    assert diag.applicable is False
    assert diag.status == "blocked"
    assert diag.reason_codes in {"OPEN_DCONNECTING_PATHS", "OPEN_PATHS"}
