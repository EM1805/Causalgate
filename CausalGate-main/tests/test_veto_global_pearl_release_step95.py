import json
from pathlib import Path

import pytest

from common.pearl_global_veto_attestation import (
    PEARL_GLOBAL_VETO_ATTESTATION_VERSION,
    global_pearl_veto_attestation_digest,
    verify_global_pearl_veto_attestation,
)
from runtime.causal_authority import (
    PEARL_COMPLETE_VETO_READINESS_MATRIX,
    assert_pearl_complete_veto_claim_allowed,
    attach_causal_authority,
    build_veto_authority_readiness,
)
from scm_parts.id_global_full_id_controlled_flip import ID_GLOBAL_FULL_ID_CONTROLLED_FLIP_VERSION
from scm_parts.id_global_pearl_veto_release import (
    build_current_global_pearl_authority_card,
    run_global_pearl_veto_release_matrix,
)
from scm_parts.id_status import id_capability_flags


def _write_card(path: Path, card):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(card, sort_keys=True), encoding="utf-8")


def test_step95_runtime_emits_verified_global_pearl_veto_attestation(tmp_path):
    card = build_current_global_pearl_authority_card("p1")
    cards = tmp_path / "cards.jsonl"
    _write_card(cards, card)

    paths = attach_causal_authority([{"path_id": "p1"}], cards_path=str(cards))
    readiness = assert_pearl_complete_veto_claim_allowed(paths, {"decision": "HARD_BLOCK"})

    attestation = readiness["pearl_complete_veto_attestation"]
    verification = readiness["pearl_complete_veto_attestation_verification"]
    assert readiness["pearl_readiness_matrix"] == PEARL_COMPLETE_VETO_READINESS_MATRIX
    assert readiness["pearl_complete_veto_claim_allowed"] is True
    assert readiness["pearl_complete_veto_attestation_verified"] is True
    assert attestation["attestation_version"] == PEARL_GLOBAL_VETO_ATTESTATION_VERSION
    assert attestation["decision"] == "HARD_BLOCK"
    assert attestation["top_path_id"] == "p1"
    assert attestation["id_global_full_id_controlled_flip"] == ID_GLOBAL_FULL_ID_CONTROLLED_FLIP_VERSION
    assert attestation["id_global_full_id_controlled_flip_passed"] == 1
    assert attestation["full_recursive_id_implemented"] == 1
    assert attestation["full_id_claim_allowed"] == 1
    assert verification["global_pearl_veto_attestation_verified"] == 1


def test_step95_blocks_global_pearl_without_step94_controlled_flip_evidence(tmp_path):
    card = build_current_global_pearl_authority_card("p1")
    card["pearl_veto_authority"] = dict(card["pearl_veto_authority"])
    card["pearl_veto_authority"].pop("id_global_full_id_controlled_flip_passed")
    card["pearl_veto_authority"].pop("global_full_id_controlled_flip_allowed")
    cards = tmp_path / "cards.jsonl"
    _write_card(cards, card)

    paths = attach_causal_authority([{"path_id": "p1"}], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": "HARD_BLOCK"})

    assert readiness["causal_veto_claim_allowed"] is True
    assert readiness["pearl_complete_veto_claim_allowed"] is False
    assert "id_global_full_id_controlled_flip_passed" in readiness["pearl_complete_veto_claim_reason"]
    with pytest.raises(ValueError, match="id_global_full_id_controlled_flip_passed"):
        assert_pearl_complete_veto_claim_allowed(paths, {"decision": "HARD_BLOCK"})


def test_step95_global_attestation_digest_blocks_decision_tampering(tmp_path):
    card = build_current_global_pearl_authority_card("p1")
    cards = tmp_path / "cards.jsonl"
    _write_card(cards, card)

    paths = attach_causal_authority([{"path_id": "p1"}], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": "HARD_BLOCK"})
    tampered = dict(readiness["pearl_complete_veto_attestation"])
    tampered["decision"] = "PASS"

    verification = verify_global_pearl_veto_attestation(tampered)
    assert verification["global_pearl_veto_attestation_verified"] == 0
    assert verification["global_pearl_veto_attestation_digest_valid"] == 0
    assert "decision" in verification["global_pearl_veto_attestation_mismatched_fields"]
    assert "attestation_digest" in verification["global_pearl_veto_attestation_mismatched_fields"]


def test_step95_global_attestation_rehash_still_blocks_non_veto_claim(tmp_path):
    card = build_current_global_pearl_authority_card("p1")
    cards = tmp_path / "cards.jsonl"
    _write_card(cards, card)

    paths = attach_causal_authority([{"path_id": "p1"}], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": "HARD_BLOCK"})
    rehashed = dict(readiness["pearl_complete_veto_attestation"])
    rehashed["decision"] = "PASS"
    rehashed["attestation_digest"] = global_pearl_veto_attestation_digest(rehashed)

    verification = verify_global_pearl_veto_attestation(rehashed)
    assert verification["global_pearl_veto_attestation_verified"] == 0
    assert verification["global_pearl_veto_attestation_digest_valid"] == 1
    assert "decision" in verification["global_pearl_veto_attestation_mismatched_fields"]


def test_step95_non_veto_decision_does_not_emit_global_pearl_attestation(tmp_path):
    card = build_current_global_pearl_authority_card("p1")
    cards = tmp_path / "cards.jsonl"
    _write_card(cards, card)

    paths = attach_causal_authority([{"path_id": "p1"}], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": "PASS"})

    assert readiness["pearl_complete_veto_claim_allowed"] is False
    assert readiness["pearl_complete_veto_attestation"] == {}
    assert readiness["pearl_complete_veto_attestation_verified"] is False


def test_step95_release_matrix_is_green():
    matrix = run_global_pearl_veto_release_matrix()

    assert matrix["matrix_version"] == PEARL_GLOBAL_VETO_ATTESTATION_VERSION
    assert matrix["global_pearl_veto_release_allowed"] == 1
    assert matrix["pearl_complete_veto_claim_allowed"] == 1
    assert matrix["attestation_verified"] == 1
    assert matrix["id_global_full_id_controlled_flip_passed"] == 1
    assert matrix["full_recursive_id_implemented"] == 1
    assert matrix["full_id_claim_allowed"] == 1


def test_step95_status_flags_are_exposed():
    flags = id_capability_flags()

    assert flags["id_global_pearl_veto_runtime_release_step95_implemented"] == 1
    assert flags["id_global_pearl_veto_runtime_attestation_version"] == PEARL_GLOBAL_VETO_ATTESTATION_VERSION
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1
