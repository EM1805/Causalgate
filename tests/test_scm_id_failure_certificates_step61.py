import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_failure_certificate import failure_certificate_for_query
from scm_parts.id_full import full_id, identify_conditional_effect
from scm_parts.id_full_readiness import run_full_id_readiness_matrix
from scm_parts.id_status import id_capability_flags


def test_step61_formal_hedge_certificate_is_exposed_on_full_id_block():
    graph = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    row = full_id(graph, ["X"], ["Y"]).to_dict()
    certificate = json.loads(row["failure_certificate_json"])

    assert row["identified"] is False
    assert row["identification_status"] == "blocked_formal_hedge_certificate"
    assert row["blocker_class"] == "formal_hedge_certificate"
    assert row["failure_certificate_status"] == "formal_hedge_certified_step68"
    assert row["failure_certified"] == 1
    assert bool(row["formal_hedge_certificate_json"])
    assert certificate["formal_hedge_certified"] == 1
    assert certificate["failure_kind"] == "formal_hedge"
    assert row["full_id_claim_allowed"] == 1


def test_step61_invalid_and_cycle_rejections_have_failure_certificates():
    graph = admg_from_edges(["X", "Y"], [("X", "Y")])
    invalid = full_id(graph, ["X"], ["X"]).to_dict()
    assert invalid["identification_status"] == "invalid_full_id_query"
    assert invalid["failure_certificate_status"] == "rejected_invalid_query_step68"
    assert invalid["failure_certified"] == 0

    cyclic = admg_from_edges(["X", "Y"], [("X", "Y"), ("Y", "X")])
    cycle = full_id(cyclic, ["X"], ["Y"]).to_dict()
    assert cycle["identification_status"] == "blocked_directed_cycle"
    assert cycle["failure_certificate_status"] == "rejected_directed_cycle_step68"
    assert cycle["blocker_class"] == "directed_cycle"


def test_step61_idc_inherits_joint_failure_certificate():
    graph = admg_from_edges(["X", "Y", "Z"], [("X", "Y"), ("Z", "Y")], [("X", "Y")])
    row = identify_conditional_effect(graph, ["X"], ["Y"], ["Z"]).to_dict()
    cert = json.loads(row["failure_certificate_json"])

    assert row["identified"] is False
    assert row["identification_status"] == "blocked_idc_joint_not_identified_step57"
    assert row["blocker_class"] == "formal_hedge_certificate"
    assert row["failure_certificate_status"] == "formal_hedge_certified_step68"
    assert row["failure_certified"] == 1
    assert cert["failure_kind"] == "formal_hedge"


def test_step61_failure_certificate_module_marks_non_certified_pending():
    graph = admg_from_edges(["X", "Y", "Z"], [("X", "Z"), ("Z", "Y")], [])
    cert = failure_certificate_for_query(
        graph,
        ["X"],
        ["Y"],
        source_status="synthetic_pending_branch",
        source_blocker_class="canonical_id7_pending",
        source_pending_operator="complete_arbitrary_ID7_carried_Q_recursion",
        source_reason_codes="SYNTHETIC_PENDING_FOR_CERTIFICATE_TEST",
    )

    assert cert.certificate_status == "not_certified_pending_failure_step68"
    assert cert.certified is False
    assert cert.formal_hedge_certified == 0
    assert cert.blocker_class == "canonical_id7_pending"
    assert "FAILURE_NOT_CERTIFIED_AS_FORMAL_HEDGE_STEP68" in cert.reason_codes


def test_step61_readiness_matrix_requires_failure_certificates():
    matrix = run_full_id_readiness_matrix()
    rows = {row["case_id"]: row for row in matrix["rows"]}

    assert matrix["matrix_version"] == "id_full_readiness_matrix_v11_step80"
    assert matrix["all_passed"] == 1
    assert matrix["n_failure_certificates"] >= 7
    assert matrix["n_formal_hedge_certificates"] >= 3
    assert rows["id_direct_confounding_hedge_fail"]["failure_certificate_status"] == "formal_hedge_certified_step68"
    assert rows["id_directed_cycle_rejected"]["failure_certificate_status"] == "rejected_directed_cycle_step68"
    assert rows["id_invalid_overlap_rejected"]["failure_certificate_status"] == "rejected_invalid_query_step68"


def test_step61_status_flag_present_without_full_id_claim():
    flags = id_capability_flags()
    assert flags["id_full_failure_certificates_step61_implemented"] == 1
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1
