import json
from pathlib import Path

from common.pearl_global_veto_attestation import (
    PEARL_GLOBAL_REQUIRED_CONTROLLED_FLIP,
    PEARL_GLOBAL_REQUIRED_ORACLE_PARITY_MATRIX,
    PEARL_GLOBAL_REQUIRED_PROMOTION_GATE,
    PEARL_GLOBAL_REQUIRED_READINESS_MATRIX,
    PEARL_GLOBAL_REQUIRED_READINESS_MATRIX_VERSION,
    PEARL_GLOBAL_VETO_ATTESTATION_VERSION,
    global_pearl_veto_attestation_digest,
    verify_global_pearl_veto_attestation,
    verify_global_pearl_veto_attestation_against_context,
)
from runtime.causal_authority import attach_causal_authority, build_veto_authority_readiness
from scm_parts.id_global_pearl_no_overclaim import (
    ID_GLOBAL_PEARL_NO_OVERCLAIM_MATRIX_VERSION,
    run_global_pearl_no_overclaim_suite,
)
from scm_parts.id_global_pearl_veto_release import build_current_global_pearl_authority_card
from scm_parts.id_status import id_capability_flags


def _write_card(path: Path, card):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(card, sort_keys=True), encoding="utf-8")


def _readiness_for_card(tmp_path: Path, card, *, decision="HARD_BLOCK"):
    cards = tmp_path / "cards.jsonl"
    _write_card(cards, card)
    pid = str(card.get("path_id") or "p1")
    paths = attach_causal_authority([{"path_id": pid}], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": decision})
    return paths, readiness


def test_step96_global_pearl_no_overclaim_suite_is_green():
    matrix = run_global_pearl_no_overclaim_suite()

    assert matrix["matrix_version"] == ID_GLOBAL_PEARL_NO_OVERCLAIM_MATRIX_VERSION
    assert matrix["global_pearl_veto_attestation_version"] == PEARL_GLOBAL_VETO_ATTESTATION_VERSION
    assert matrix["all_passed"] == 1
    assert matrix["n_cases"] == 20
    assert matrix["n_passed"] == matrix["n_cases"]
    assert matrix["n_adversarial_cases"] == 19
    assert matrix["n_adversarial_cases_blocked"] == 19
    assert matrix["failed_case_ids"] == ""
    assert matrix["positive_control_allowed"] == 1
    assert matrix["required_readiness_matrix"] == PEARL_GLOBAL_REQUIRED_READINESS_MATRIX
    assert matrix["required_oracle_matrix"] == PEARL_GLOBAL_REQUIRED_ORACLE_PARITY_MATRIX
    assert matrix["required_promotion_gate"] == PEARL_GLOBAL_REQUIRED_PROMOTION_GATE
    assert matrix["required_controlled_flip"] == PEARL_GLOBAL_REQUIRED_CONTROLLED_FLIP


def test_step96_blocks_stale_global_pearl_authority_card_versions(tmp_path):
    stale_cases = {
        "id_full_readiness_matrix": "id_full_readiness_matrix_version_matches",
        "id_oracle_parity_matrix": "id_oracle_parity_matrix_version_matches",
        "id_full_promotion_gate": "id_full_promotion_gate_version_matches",
        "id_global_full_id_controlled_flip": "id_global_full_id_controlled_flip_version_matches",
    }
    for field, expected_blocker in stale_cases.items():
        card = build_current_global_pearl_authority_card("p1")
        card["pearl_veto_authority"][field] = f"{field}_stale"

        _, readiness = _readiness_for_card(tmp_path, card)

        assert readiness["causal_veto_claim_allowed"] is True
        assert readiness["pearl_complete_veto_claim_allowed"] is False
        assert expected_blocker in readiness["pearl_complete_veto_claim_reason"]
        assert readiness["pearl_complete_veto_attestation"] == {}


def test_step96_global_attestation_blocks_rehashed_stale_matrix_versions(tmp_path):
    card = build_current_global_pearl_authority_card("p1")
    _, readiness = _readiness_for_card(tmp_path, card)
    attestation = dict(readiness["pearl_complete_veto_attestation"])

    stale_cases = {
        "id_full_readiness_matrix": PEARL_GLOBAL_REQUIRED_READINESS_MATRIX,
        "id_oracle_parity_matrix": PEARL_GLOBAL_REQUIRED_ORACLE_PARITY_MATRIX,
        "id_full_promotion_gate": PEARL_GLOBAL_REQUIRED_PROMOTION_GATE,
        "id_global_full_id_controlled_flip": PEARL_GLOBAL_REQUIRED_CONTROLLED_FLIP,
        "pearl_complete_readiness_matrix": PEARL_GLOBAL_REQUIRED_READINESS_MATRIX_VERSION,
    }
    for field in stale_cases:
        tampered = dict(attestation)
        tampered[field] = f"{field}_stale"
        tampered["attestation_digest"] = global_pearl_veto_attestation_digest(tampered)

        verification = verify_global_pearl_veto_attestation(tampered)

        assert verification["global_pearl_veto_attestation_verified"] == 0
        assert verification["global_pearl_veto_attestation_digest_valid"] == 1
        assert field in verification["global_pearl_veto_attestation_mismatched_fields"]


def test_step96_contextual_verifier_blocks_rehashed_top_path_replay(tmp_path):
    card = build_current_global_pearl_authority_card("p1")
    paths, readiness = _readiness_for_card(tmp_path, card)
    attestation = dict(readiness["pearl_complete_veto_attestation"])
    top_source = next(p for p in paths if p.get("path_id") == readiness["top_path_id"])
    context = {
        "decision": readiness["decision"],
        "veto_like_decision": readiness["veto_like_decision"],
        "top_path_id": readiness["top_path_id"],
        "top_veto_authority_class": readiness["top_veto_authority_class"],
        "top_pearl_veto_authority_class": readiness["top_pearl_veto_authority_class"],
        "pearl_complete_veto_claim_allowed": readiness["pearl_complete_veto_claim_allowed"],
        "pearl_complete_veto_claim_reason": readiness["pearl_complete_veto_claim_reason"],
        "pearl_readiness_matrix": readiness["pearl_readiness_matrix"],
    }

    replayed = dict(attestation)
    replayed["top_path_id"] = "other_path"
    replayed["attestation_digest"] = global_pearl_veto_attestation_digest(replayed)

    verification = verify_global_pearl_veto_attestation_against_context(
        replayed,
        readiness=context,
        top_path=top_source,
    )

    assert verification["global_pearl_veto_attestation_verified"] == 1
    assert verification["global_pearl_veto_attestation_context_verified"] == 0
    assert "top_path_id" in verification["global_pearl_veto_attestation_context_mismatched_fields"]


def test_step96_status_flags_are_exposed():
    flags = id_capability_flags()

    assert flags["id_global_pearl_no_overclaim_adversarial_suite_step96_implemented"] == 1
    assert flags["id_global_pearl_no_overclaim_adversarial_suite_version"] == ID_GLOBAL_PEARL_NO_OVERCLAIM_MATRIX_VERSION
    assert flags["id_global_pearl_veto_runtime_attestation_version"] == PEARL_GLOBAL_VETO_ATTESTATION_VERSION
