from scm_parts.id_scoped_pearl_promotion import (
    ID_SCOPED_PEARL_PROMOTION_GATE_VERSION,
    ID_SCOPED_PEARL_PROMOTION_SCOPE,
    run_scoped_pearl_promotion_gate,
)
from scm_parts.id_full_promotion_gate import run_id_full_promotion_gate
from scm_parts.id_status import id_capability_flags


def test_step87_scoped_pearl_gate_turns_green_for_audited_public_surface_only():
    gate = run_scoped_pearl_promotion_gate()

    assert gate["matrix_version"] == ID_SCOPED_PEARL_PROMOTION_GATE_VERSION
    assert gate["scope"] == ID_SCOPED_PEARL_PROMOTION_SCOPE
    assert gate["scoped_promotion_allowed"] == 1
    assert gate["scoped_pearl_veto_claim_allowed"] == 1
    assert gate["global_full_recursive_id_implemented"] == 1
    assert gate["global_full_id_claim_allowed"] == 1
    assert gate["global_full_id_claim_stays_blocked"] == 0
    assert gate["id_full_promotion_gate_passed"] == 1
    assert gate["id_full_promotion_gate_missing_required_flags"] == ""
    assert gate["n_identified_formula_rows_audited"] == 78
    assert gate["n_full_recursive_formula_authority"] == 78
    assert gate["n_finite_or_template_formula_authority"] == 0
    assert gate["n_technical_pending_not_certified"] == 0
    assert gate["missing_required_flags"] == ""
    assert all(row["passed"] for row in gate["requirements"])


def test_step87_global_full_id_promotion_stays_red_and_scoped_gate_are_green():
    global_gate = run_id_full_promotion_gate()
    scoped_gate = run_scoped_pearl_promotion_gate()

    assert global_gate["promotion_allowed"] == 1
    assert global_gate["missing_required_flags"] == ""
    assert scoped_gate["scoped_promotion_allowed"] == 1
    assert scoped_gate["global_claim_reason"] == "global_full_id_claim_observed_by_scoped_gate_step94"


def test_step87_status_flags_make_scope_bound_release_explicit():
    flags = id_capability_flags()

    assert flags["id_scoped_pearl_promotion_step87_implemented"] == 1
    assert flags["id_scoped_pearl_promotion_gate_version"] == ID_SCOPED_PEARL_PROMOTION_GATE_VERSION
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1
