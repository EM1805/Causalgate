from scm_parts.id_full_readiness import run_full_id_readiness_matrix
from scm_parts.id_status import id_capability_flags


def test_step58_full_id_readiness_matrix_passes_without_full_id_claim():
    matrix = run_full_id_readiness_matrix()
    assert matrix["matrix_version"] == "id_full_readiness_matrix_v11_step80"
    assert matrix["n_cases"] >= 18
    assert matrix["all_passed"] == 1
    assert matrix["n_failed"] == 0
    assert matrix["full_id_claim_allowed"] == 1
    assert matrix["n_idc_cases"] >= 5
    assert matrix["n_blocked"] >= 2
    assert matrix["n_invalid_rejected"] >= 2


def test_step58_matrix_contains_required_families():
    matrix = run_full_id_readiness_matrix()
    rows = {row["case_id"]: row for row in matrix["rows"]}

    assert rows["id_frontdoor_canonical_id7"]["canonical_id7_carried_q_formula_used"] == "1"
    assert rows["id_direct_confounding_hedge_fail"]["blocker_class"] == "formal_hedge_certificate"
    assert rows["id_canonical_district_decomposition_id4"]["primary_formula_authority"] == "id_canonical_formula_step60"
    assert rows["idc_observed_dag_single_condition"]["identification_status"] == "identified_idc_ratio_over_identified_joint_step57"
    assert rows["idc_joint_hedge_blocked"]["pending_operator"] == "identify_joint_yz_under_do_x_before_idc_ratio"


def test_step58_status_flags_are_conservative():
    flags = id_capability_flags()
    assert flags["id_full_readiness_matrix_step58_implemented"] == 1
    assert flags["full_recursive_id_implemented"] == 1
