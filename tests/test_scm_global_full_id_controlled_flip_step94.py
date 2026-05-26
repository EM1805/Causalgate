from scm_parts.id_full_promotion_gate import ID_FULL_PROMOTION_GATE_VERSION, run_id_full_promotion_gate
from scm_parts.id_global_full_id_controlled_flip import (
    ID_GLOBAL_FULL_ID_CONTROLLED_FLIP_VERSION,
    run_global_full_id_controlled_flip,
)
from scm_parts.id_global_full_id_promotion_dry_run import run_global_full_id_promotion_dry_run
from scm_parts.id_status import id_capability_flags


def _preflip_flags():
    flags = dict(id_capability_flags())
    flags["full_recursive_id_implemented"] = 0
    flags["full_id_claim_allowed"] = 0
    return flags


def test_step94_controlled_flip_is_green_and_gate_backed():
    flip = run_global_full_id_controlled_flip()

    assert flip["matrix_version"] == ID_GLOBAL_FULL_ID_CONTROLLED_FLIP_VERSION
    assert flip["global_full_id_controlled_flip_allowed"] == 1
    assert flip["global_full_id_flags_mutated"] == 1
    assert flip["full_recursive_id_implemented"] == 1
    assert flip["full_id_claim_allowed"] == 1
    assert flip["id_full_promotion_gate_passed"] == 1
    assert flip["live_promotion_gate_allowed"] == 1
    assert flip["live_promotion_gate_missing_required_flags"] == ""
    assert flip["live_promotion_gate_claim_allowed_after_gate"] == 1
    assert all(row["passed"] for row in flip["requirements"])


def test_step94_live_promotion_gate_is_green_with_status_flags():
    gate = run_id_full_promotion_gate()

    assert gate["matrix_version"] == ID_FULL_PROMOTION_GATE_VERSION
    assert gate["matrix_version"] == "id_full_promotion_gate_v7_step94"
    assert gate["promotion_allowed"] == 1
    assert gate["missing_required_flags"] == ""
    assert gate["full_recursive_id_implemented"] == 1
    assert gate["full_id_claim_allowed"] == 1
    assert gate["id_full_recursive_kernel_matrix_passed"] == 1
    assert gate["id_full_recursive_oracle_expansion_passed"] == 1
    assert gate["formal_failure_certificate_coverage_complete"] == 1
    assert gate["pearl_formula_authority_coverage_complete"] == 1
    assert gate["full_id_claim_allowed_after_promotion_gate"] == 1


def test_step94_archived_step93_dry_run_still_green_with_explicit_preflip_flags():
    dry_run = run_global_full_id_promotion_dry_run(capability_flags=_preflip_flags())

    assert dry_run["global_promotion_dry_run_allowed"] == 1
    assert dry_run["current_full_recursive_id_implemented"] == 0
    assert dry_run["current_full_id_claim_allowed"] == 0
    assert dry_run["current_promotion_gate_missing_required_flags"] == "full_recursive_id_implemented|full_id_claim_allowed"
    assert dry_run["simulated_promotion_gate_allowed"] == 1


def test_step94_blocks_partial_flag_flip():
    flags = dict(id_capability_flags())
    flags["full_recursive_id_implemented"] = 1
    flags["full_id_claim_allowed"] = 0

    flip = run_global_full_id_controlled_flip(capability_flags=flags)

    assert flip["global_full_id_controlled_flip_allowed"] == 0
    assert flip["full_recursive_id_implemented"] == 1
    assert flip["full_id_claim_allowed"] == 0
    assert "global_flags_not_flipped_together" in flip["blocker_classes"]
    assert "live_promotion_gate_not_green" in flip["blocker_classes"]


def test_step94_blocks_if_non_global_prerequisite_regresses():
    failing_expansion = {
        "matrix_version": "id_full_recursive_oracle_expansion_fixture_failed_step94",
        "all_passed": 0,
        "n_cases": 4,
        "n_passed": 3,
        "n_pending_kernel_blockers": 1,
    }

    flip = run_global_full_id_controlled_flip(full_recursive_oracle_expansion=failing_expansion)

    assert flip["global_full_id_controlled_flip_allowed"] == 0
    assert "preflip_dry_run_not_green" in flip["blocker_classes"]
    assert "live_promotion_gate_not_green" in flip["blocker_classes"]


def test_step94_status_flags_expose_global_full_id_release():
    flags = id_capability_flags()

    assert flags["id_global_full_id_controlled_flip_step94_implemented"] == 1
    assert flags["id_global_full_id_controlled_flip_version"] == ID_GLOBAL_FULL_ID_CONTROLLED_FLIP_VERSION
    assert flags["id_full_promotion_gate_version"] == "id_full_promotion_gate_v7_step94"
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1
