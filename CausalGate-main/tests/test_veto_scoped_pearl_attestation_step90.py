import json
from pathlib import Path

from common.pearl_veto_attestation import (
    PEARL_SCOPED_VETO_ATTESTATION_VERSION,
    scoped_pearl_veto_attestation_digest,
    verify_scoped_pearl_veto_attestation,
)
from runtime.causal_authority import (
    PEARL_SCOPED_VETO_READINESS_MATRIX,
    attach_causal_authority,
    build_veto_authority_readiness,
    assert_pearl_scoped_veto_claim_allowed,
)
from scm_parts.id_scoped_pearl_veto_attestation import (
    build_current_scoped_pearl_authority_card,
    run_scoped_pearl_veto_attestation_matrix,
)
from scm_parts.id_status import id_capability_flags


def _write_card(path: Path, card):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(card, sort_keys=True), encoding="utf-8")


def test_step90_runtime_emits_verified_scoped_pearl_veto_attestation(tmp_path):
    card = build_current_scoped_pearl_authority_card("p1")
    cards = tmp_path / "cards.jsonl"
    _write_card(cards, card)

    paths = attach_causal_authority([{"path_id": "p1"}], cards_path=str(cards))
    readiness = assert_pearl_scoped_veto_claim_allowed(paths, {"decision": "HARD_BLOCK"})

    attestation = readiness["pearl_scoped_veto_attestation"]
    verification = readiness["pearl_scoped_veto_attestation_verification"]
    assert readiness["pearl_scoped_readiness_matrix"] == PEARL_SCOPED_VETO_READINESS_MATRIX
    assert readiness["pearl_scoped_veto_claim_allowed"] is True
    assert readiness["pearl_scoped_veto_attestation_verified"] is True
    assert attestation["attestation_version"] == PEARL_SCOPED_VETO_ATTESTATION_VERSION
    assert attestation["decision"] == "HARD_BLOCK"
    assert attestation["top_path_id"] == "p1"
    assert attestation["scoped_pearl_manifest_digest"] == paths[0]["pearl_scoped_veto_authority"]["scoped_pearl_manifest_digest"]
    assert attestation["scoped_pearl_release_manifest_digest"] == paths[0]["pearl_scoped_veto_authority"]["scoped_pearl_release_manifest_digest"]
    assert attestation["global_full_recursive_id_implemented"] == 1
    assert attestation["global_full_id_claim_allowed"] == 1
    assert verification["scoped_pearl_veto_attestation_verified"] == 1


def test_step90_attestation_digest_blocks_runtime_decision_tampering(tmp_path):
    card = build_current_scoped_pearl_authority_card("p1")
    cards = tmp_path / "cards.jsonl"
    _write_card(cards, card)

    paths = attach_causal_authority([{"path_id": "p1"}], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": "HARD_BLOCK"})
    tampered = dict(readiness["pearl_scoped_veto_attestation"])
    tampered["decision"] = "PASS"

    verification = verify_scoped_pearl_veto_attestation(tampered)
    assert verification["scoped_pearl_veto_attestation_verified"] == 0
    assert verification["scoped_pearl_veto_attestation_digest_valid"] == 0
    assert "decision" in verification["scoped_pearl_veto_attestation_mismatched_fields"]
    assert "attestation_digest" in verification["scoped_pearl_veto_attestation_mismatched_fields"]


def test_step90_attestation_rehash_still_blocks_non_veto_claim(tmp_path):
    card = build_current_scoped_pearl_authority_card("p1")
    cards = tmp_path / "cards.jsonl"
    _write_card(cards, card)

    paths = attach_causal_authority([{"path_id": "p1"}], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": "HARD_BLOCK"})
    rehashed = dict(readiness["pearl_scoped_veto_attestation"])
    rehashed["decision"] = "PASS"
    rehashed["attestation_digest"] = scoped_pearl_veto_attestation_digest(rehashed)

    verification = verify_scoped_pearl_veto_attestation(rehashed)
    assert verification["scoped_pearl_veto_attestation_verified"] == 0
    assert verification["scoped_pearl_veto_attestation_digest_valid"] == 1
    assert "decision" in verification["scoped_pearl_veto_attestation_mismatched_fields"]


def test_step90_non_veto_decision_does_not_emit_scoped_pearl_attestation(tmp_path):
    card = build_current_scoped_pearl_authority_card("p1")
    cards = tmp_path / "cards.jsonl"
    _write_card(cards, card)

    paths = attach_causal_authority([{"path_id": "p1"}], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": "PASS"})

    assert readiness["pearl_scoped_veto_claim_allowed"] is False
    assert readiness["pearl_scoped_veto_attestation"] == {}
    assert readiness["pearl_scoped_veto_attestation_verified"] is False


def test_step90_attestation_matrix_is_green_but_global_full_id_stays_off():
    matrix = run_scoped_pearl_veto_attestation_matrix()

    assert matrix["matrix_version"] == PEARL_SCOPED_VETO_ATTESTATION_VERSION
    assert matrix["attestation_verified"] == 1
    assert matrix["pearl_scoped_veto_claim_allowed"] == 1
    assert matrix["pearl_complete_veto_claim_allowed"] == 0
    assert matrix["global_full_recursive_id_implemented"] == 1
    assert matrix["global_full_id_claim_allowed"] == 1


def test_step90_status_flags_are_exposed():
    flags = id_capability_flags()

    assert flags["id_scoped_pearl_veto_runtime_attestation_step90_implemented"] == 1
    assert flags["id_scoped_pearl_veto_runtime_attestation_version"] == PEARL_SCOPED_VETO_ATTESTATION_VERSION
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1
