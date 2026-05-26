import json
from pathlib import Path

import pytest

from common.pearl_scope_manifest import scoped_pearl_manifest_digest
from runtime.causal_authority import (
    PEARL_SCOPED_VETO_READINESS_MATRIX,
    assert_pearl_scoped_veto_claim_allowed,
    attach_causal_authority,
    build_veto_authority_readiness,
)
from scm_parts.id_full_recursive_trace_authority import FULL_RECURSIVE_TRACE_FORMULA_AUTHORITY
from scm_parts.id_scoped_pearl_promotion import (
    ID_SCOPED_PEARL_PROMOTION_GATE_VERSION,
    ID_SCOPED_PEARL_PROMOTION_SCOPE,
)
from scm_parts.id_scoped_pearl_scope_manifest import build_current_scoped_pearl_manifest
from scm_parts.id_scoped_pearl_release_manifest import build_current_scoped_pearl_release_manifest


def _write_cards(path: Path, cards):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(card, sort_keys=True) for card in cards), encoding="utf-8")


def _bundle(*, manifest=None, release=None):
    if manifest is None:
        manifest = build_current_scoped_pearl_manifest()
    if release is None and manifest:
        release = build_current_scoped_pearl_release_manifest(scoped_manifest=manifest)
    return {
        "scoped_full_recursive_id_implemented": 1,
        "scoped_full_id_claim_allowed": 1,
        "global_full_recursive_id_implemented": 1,
        "global_full_id_claim_allowed": 1,
        "id_full_readiness_matrix": "id_full_readiness_matrix_v11_step80",
        "id_full_readiness_matrix_passed": 1,
        "id_oracle_parity_matrix": "id_oracle_parity_matrix_v3_step80",
        "id_oracle_parity_fuzz_passed": 1,
        "formal_failure_certificate_coverage_complete": 1,
        "formal_failure_certificate_coverage": "complete",
        "id_scoped_pearl_promotion_gate": ID_SCOPED_PEARL_PROMOTION_GATE_VERSION,
        "id_scoped_pearl_promotion_gate_passed": 1,
        "scope": ID_SCOPED_PEARL_PROMOTION_SCOPE,
        "primary_formula_authority": FULL_RECURSIVE_TRACE_FORMULA_AUTHORITY,
        "scoped_pearl_manifest": manifest,
        "scoped_pearl_release_manifest": release or {},
    }


def _card(bundle):
    return {
        "path_id": "p1",
        "authority_level": "identified_runtime_path",
        "runtime_use": "causal_veto_allowed",
        "authority_reason": "specific_runtime_path_matches_identified_offline_contract",
        "contract_authority_level": "identified_estimable",
        "pearl_scoped_veto_authority": bundle,
    }


def test_step88_runtime_allows_scoped_pearl_only_with_verified_manifest(tmp_path):
    cards = tmp_path / "cards.jsonl"
    _write_cards(cards, [_card(_bundle())])

    paths = attach_causal_authority([{"path_id": "p1"}], cards_path=str(cards))
    readiness = assert_pearl_scoped_veto_claim_allowed(paths, {"decision": "HARD_BLOCK"})

    assert readiness["pearl_scoped_readiness_matrix"] == PEARL_SCOPED_VETO_READINESS_MATRIX
    assert readiness["pearl_scoped_veto_claim_allowed"] is True
    assert paths[0]["pearl_scoped_veto_authority"]["scoped_pearl_manifest_verified"] == 1
    assert paths[0]["pearl_scoped_veto_claim_reason"] == "scoped_pearl_readiness_recursive_trace_scope_manifest_and_release_manifest_allow_pearl_veto_claim_step89"


def test_step88_runtime_blocks_scoped_pearl_without_manifest(tmp_path):
    cards = tmp_path / "cards.jsonl"
    _write_cards(cards, [_card(_bundle(manifest={}))])

    paths = attach_causal_authority([{"path_id": "p1"}], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": "HARD_BLOCK"})

    assert readiness["pearl_scoped_veto_claim_allowed"] is False
    assert "scoped_pearl_manifest_verified" in readiness["pearl_scoped_veto_claim_reason"]
    with pytest.raises(ValueError, match="scoped_pearl_manifest_verified"):
        assert_pearl_scoped_veto_claim_allowed(paths, {"decision": "HARD_BLOCK"})


def test_step88_runtime_blocks_stale_or_tampered_manifest_even_when_flags_are_green(tmp_path):
    cards = tmp_path / "cards.jsonl"
    manifest = build_current_scoped_pearl_manifest()
    tampered = dict(manifest)
    tampered["n_full_recursive_formula_authority"] = 77
    tampered["manifest_digest"] = scoped_pearl_manifest_digest(tampered)
    _write_cards(cards, [_card(_bundle(manifest=tampered))])

    paths = attach_causal_authority([{"path_id": "p1"}], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": "HARD_BLOCK"})

    assert readiness["pearl_scoped_veto_claim_allowed"] is False
    authority = paths[0]["pearl_scoped_veto_authority"]
    assert authority["scoped_pearl_manifest_verified"] == 0
    assert authority["scoped_pearl_manifest_digest_valid"] == 1
    assert authority["scoped_pearl_manifest_mismatched_fields"] == "n_full_recursive_formula_authority"
    assert "scoped_pearl_manifest_verified" in readiness["pearl_scoped_veto_claim_reason"]
