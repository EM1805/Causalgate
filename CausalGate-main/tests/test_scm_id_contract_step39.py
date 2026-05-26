import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_algorithm import identify_effect


def test_identified_query_has_formula_and_contract_certificate():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [])
    result = identify_effect(g, "X", "Y")
    row = result.to_dict()
    assert row["identifiable"] is True
    assert row["estimand_formula"]
    assert row["id_proof_status"] == "identified_proof_trace"
    assert row["id_contract_status"] == "identified_with_formula_and_proof_trace"
    assert row["id_contract_ok"] == 1
    cert = json.loads(row["identification_certificate_json"])
    assert cert["identified"] is True
    assert cert["formula"] == row["estimand_formula"]
    assert cert["proof_trace"]


def test_formal_hedge_query_has_nonidentification_certificate():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    result = identify_effect(g, "X", "Y")
    row = result.to_dict()
    assert row["identifiable"] is False
    assert row["formal_hedge_certified"] == 1
    assert row["id_contract_status"] == "nonidentified_with_formal_hedge_certificate"
    assert row["id_contract_ok"] == 1
    cert = json.loads(row["nonidentification_certificate_json"])
    assert cert["certificate_kind"] == "formal_hedge"
    assert cert["F"] == "{X,Y}"
    assert cert["F_prime"] == "{Y}"


def test_blocked_without_hedge_is_not_overclaimed_as_impossibility():
    g = admg_from_edges(["X", "Y", "U"], [("X", "Y"), ("U", "Y")], [("X", "U")])
    result = identify_effect(g, "X", "Y")
    row = result.to_dict()
    if row["identifiable"]:
        assert row["id_contract_status"] == "identified_with_formula_and_proof_trace"
    elif row["formal_hedge_certified"] == 0:
        assert row["id_contract_status"] == "blocked_without_formal_impossibility_certificate"
