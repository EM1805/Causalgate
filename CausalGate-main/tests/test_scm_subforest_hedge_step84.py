import json

from scm_parts.admg import admg_from_edges
from scm_parts.hedge import formal_hedge_diagnostic
from scm_parts.id_failure_certificate import failure_certificate_for_query
from scm_parts.id_oracle_parity import run_id_oracle_parity_matrix


def _case_045_graph():
    return admg_from_edges(
        ("X", "A", "B", "Y"),
        (("X", "A"), ("X", "B"), ("A", "Y"), ("B", "Y")),
        (("X", "A"), ("A", "B"), ("B", "Y")),
    )


def _case_054_graph():
    return admg_from_edges(
        ("X", "A", "B", "Y"),
        (("A", "X"), ("X", "B"), ("B", "Y")),
        (("X", "A"), ("A", "B"), ("B", "Y")),
    )


def test_step84_subforest_hedge_certifies_previous_pending_fuzz_045():
    hedge = formal_hedge_diagnostic(_case_045_graph(), ["X"], ["Y"])

    assert hedge.formal_hedge_certified is True
    assert hedge.hedge_F == "{A,X}"
    assert hedge.hedge_F_prime == "{A}"
    assert hedge.hedge_roots_F == "A"
    assert "SUBFOREST_HEDGE_CERTIFIED_STEP84" in hedge.hedge_reason_codes
    checks = json.loads(hedge.hedge_checks_json)
    assert checks["search_scope"] == "audited_subforest_step84"
    assert checks["same_roots"] is True


def test_step84_subforest_hedge_certifies_previous_pending_fuzz_054():
    hedge = formal_hedge_diagnostic(_case_054_graph(), ["X"], ["Y"])

    assert hedge.formal_hedge_certified is True
    assert hedge.hedge_F == "{A,B,X}"
    assert hedge.hedge_F_prime == "{B}"
    assert hedge.hedge_roots_F == "B"
    assert "SUBFOREST_HEDGE_CERTIFIED_STEP84" in hedge.hedge_reason_codes
    checks = json.loads(hedge.hedge_checks_json)
    assert checks["search_scope"] == "audited_subforest_step84"
    assert checks["F_prime_in_G_without_X"] is True


def test_step84_failure_certificate_for_previous_pending_graphs_is_formal():
    for graph in (_case_045_graph(), _case_054_graph()):
        cert = failure_certificate_for_query(graph, ["X"], ["Y"])
        assert cert.certificate_status == "formal_hedge_certified_step68"
        assert cert.certified is True
        payload = json.loads(cert.certificate_json)
        assert payload["formal_hedge_certified"] == 1
        assert "SUBFOREST_HEDGE_CERTIFIED_STEP84" in payload["reason_codes"]


def test_step84_fuzz_rows_045_and_054_are_no_longer_pending():
    fuzz_rows = {row["fuzz_id"]: row for row in run_id_oracle_parity_matrix()["fuzz"]["rows"]}

    assert fuzz_rows["fuzz_step76_045"]["failure_certificate_status"] == "formal_hedge_certified_step68"
    assert fuzz_rows["fuzz_step76_054"]["failure_certificate_status"] == "formal_hedge_certified_step68"
    assert fuzz_rows["fuzz_step76_045"]["identified"] is False
    assert fuzz_rows["fuzz_step76_054"]["identified"] is False
