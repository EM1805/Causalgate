from scm_parts.id_full_promotion_gate import ID_FULL_PROMOTION_GATE_VERSION
from scm_parts.id_global_full_id_promotion_dry_run import (
    GLOBAL_FULL_ID_FLIP_FLAGS,
    ID_GLOBAL_FULL_ID_PROMOTION_DRY_RUN_VERSION,
    run_global_full_id_promotion_dry_run,
)
from scm_parts.id_status import id_capability_flags


def _preflip_flags():
    flags = dict(id_capability_flags())
    flags["full_recursive_id_implemented"] = 0
    flags["full_id_claim_allowed"] = 0
    return flags


def test_step93_global_full_id_promotion_dry_run_is_green_without_mutating_flags():
    dry_run = run_global_full_id_promotion_dry_run(capability_flags=_preflip_flags())

    assert dry_run["matrix_version"] == ID_GLOBAL_FULL_ID_PROMOTION_DRY_RUN_VERSION
    assert dry_run["matrix_version"] == "id_global_full_id_promotion_dry_run_v1_step93"
    assert dry_run["global_promotion_dry_run_allowed"] == 1
    assert dry_run["current_full_recursive_id_implemented"] == 0
    assert dry_run["current_full_id_claim_allowed"] == 0
    assert dry_run["would_set_full_recursive_id_implemented"] == 1
    assert dry_run["would_set_full_id_claim_allowed"] == 1
    assert dry_run["global_full_id_flags_mutated"] == 0
    assert dry_run["missing_non_global_prerequisites"] == ""
    assert dry_run["current_promotion_gate_missing_required_flags"] == "full_recursive_id_implemented|full_id_claim_allowed"
    assert dry_run["simulated_promotion_gate_allowed"] == 1
    assert dry_run["simulated_promotion_gate_missing_required_flags"] == ""
    assert all(row["passed"] for row in dry_run["requirements"])

    flags = id_capability_flags()
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1


def test_step93_dry_run_uses_step92_promotion_gate_and_required_green_evidence():
    dry_run = run_global_full_id_promotion_dry_run(capability_flags=_preflip_flags())

    assert dry_run["current_promotion_gate_version"] == ID_FULL_PROMOTION_GATE_VERSION
    assert dry_run["simulated_promotion_gate_version"] == ID_FULL_PROMOTION_GATE_VERSION
    assert dry_run["current_promotion_gate"]["id_full_recursive_kernel_matrix_passed"] == 1
    assert dry_run["current_promotion_gate"]["id_full_recursive_oracle_expansion_passed"] == 1
    assert dry_run["current_promotion_gate"]["formal_failure_certificate_coverage_complete"] == 1
    assert dry_run["current_promotion_gate"]["pearl_formula_authority_coverage_complete"] == 1
    assert dry_run["current_promotion_gate"]["no_raw_delegated_formula_authority"] == 1
    assert dry_run["simulated_promotion_gate"]["full_id_claim_allowed_after_promotion_gate"] == 1
    assert tuple(GLOBAL_FULL_ID_FLIP_FLAGS) == ("full_recursive_id_implemented", "full_id_claim_allowed")


def test_step93_blocks_if_any_non_global_prerequisite_is_red():
    failing_expansion = {
        "matrix_version": "id_full_recursive_oracle_expansion_fixture_failed_step93",
        "all_passed": 0,
        "n_cases": 3,
        "n_passed": 2,
        "n_pending_kernel_blockers": 1,
    }

    dry_run = run_global_full_id_promotion_dry_run(capability_flags=_preflip_flags(), full_recursive_oracle_expansion=failing_expansion)

    assert dry_run["global_promotion_dry_run_allowed"] == 0
    assert dry_run["would_set_full_recursive_id_implemented"] == 0
    assert dry_run["would_set_full_id_claim_allowed"] == 0
    assert "id_full_recursive_oracle_expansion_passed" in dry_run["missing_non_global_prerequisites"]
    assert "non_global_prerequisite_missing" in dry_run["blocker_classes"]
    assert dry_run["simulated_promotion_gate_allowed"] == 0


def test_step93_blocks_if_global_flags_are_already_partially_set_before_dry_run():
    flags = dict(id_capability_flags())
    flags["full_recursive_id_implemented"] = 1
    flags["full_id_claim_allowed"] = 0

    dry_run = run_global_full_id_promotion_dry_run(capability_flags=flags)

    assert dry_run["global_promotion_dry_run_allowed"] == 0
    assert dry_run["current_full_recursive_id_implemented"] == 1
    assert dry_run["current_full_id_claim_allowed"] == 0
    assert "global_flags_already_mutated_or_partially_set" in dry_run["blocker_classes"]
    assert dry_run["simulated_promotion_gate_allowed"] == 1


def test_step93_status_flags_present_without_global_claim_flip():
    flags = id_capability_flags()

    assert flags["id_global_full_id_promotion_dry_run_step93_implemented"] == 1
    assert flags["id_global_full_id_promotion_dry_run_version"] == ID_GLOBAL_FULL_ID_PROMOTION_DRY_RUN_VERSION
    assert flags["id_full_promotion_gate_version"] == "id_full_promotion_gate_v7_step94"
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1
