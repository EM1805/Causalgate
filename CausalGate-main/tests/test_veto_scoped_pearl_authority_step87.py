import json
from pathlib import Path

import pytest

from runtime.causal_authority import (
    PEARL_COMPLETE_VETO_READINESS_MATRIX,
    PEARL_SCOPED_VETO_READINESS_MATRIX,
    PEARL_SCOPED_FORMULA_AUTHORITIES,
    assert_pearl_complete_veto_claim_allowed,
    assert_pearl_scoped_veto_claim_allowed,
    attach_causal_authority,
    build_veto_authority_readiness,
)
from scm_parts.id_scoped_pearl_promotion import (
    ID_SCOPED_PEARL_PROMOTION_GATE_VERSION,
    ID_SCOPED_PEARL_PROMOTION_SCOPE,
)
from scm_parts.id_full_recursive_trace_authority import FULL_RECURSIVE_TRACE_FORMULA_AUTHORITY
from scm_parts.id_scoped_pearl_scope_manifest import build_current_scoped_pearl_manifest
from scm_parts.id_scoped_pearl_release_manifest import build_current_scoped_pearl_release_manifest


def _write_cards(path: Path, cards):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(card, sort_keys=True) for card in cards), encoding="utf-8")


def _scoped_bundle(*, gate_passed=1, formula_authority=FULL_RECURSIVE_TRACE_FORMULA_AUTHORITY, manifest=None, release=None):
    if manifest is None and gate_passed:
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
        "id_scoped_pearl_promotion_gate_passed": gate_passed,
        "scope": ID_SCOPED_PEARL_PROMOTION_SCOPE,
        "primary_formula_authority": formula_authority,
        "scoped_pearl_manifest": manifest or {},
        "scoped_pearl_release_manifest": release or {},
    }


def _causal_card(scoped_bundle):
    return {
        "path_id": "p1",
        "authority_level": "identified_runtime_path",
        "runtime_use": "causal_veto_allowed",
        "authority_reason": "specific_runtime_path_matches_identified_offline_contract",
        "contract_authority_level": "identified_estimable",
        "pearl_scoped_veto_authority": scoped_bundle,
    }


def test_step87_scoped_pearl_veto_claim_is_allowed_for_step86_trace_authority(tmp_path):
    cards = tmp_path / "cards.jsonl"
    _write_cards(cards, [_causal_card(_scoped_bundle())])

    paths = attach_causal_authority([{"path_id": "p1"}], cards_path=str(cards))
    readiness = assert_pearl_scoped_veto_claim_allowed(paths, {"decision": "HARD_BLOCK"})

    assert PEARL_SCOPED_VETO_READINESS_MATRIX in readiness["readiness_matrices"]
    assert readiness["pearl_scoped_readiness_matrix"] == PEARL_SCOPED_VETO_READINESS_MATRIX
    assert readiness["pearl_readiness_matrix"] == PEARL_COMPLETE_VETO_READINESS_MATRIX
    assert paths[0]["pearl_scoped_veto_claim_allowed"] is True
    assert readiness["pearl_scoped_veto_claim_allowed"] is True
    assert readiness["top_pearl_scoped_veto_authority_class"] == "pearl_scoped_veto_authorized"
    assert FULL_RECURSIVE_TRACE_FORMULA_AUTHORITY in PEARL_SCOPED_FORMULA_AUTHORITIES

    # Scoped Pearl is not the same as global Pearl-complete.
    assert paths[0]["pearl_complete_veto_claim_allowed"] is False
    with pytest.raises(ValueError, match="pearl_complete"):
        assert_pearl_complete_veto_claim_allowed(paths, {"decision": "HARD_BLOCK"})


def test_step87_scoped_pearl_veto_blocks_without_scoped_gate(tmp_path):
    cards = tmp_path / "cards.jsonl"
    _write_cards(cards, [_causal_card(_scoped_bundle(gate_passed=0))])

    paths = attach_causal_authority([{"path_id": "p1"}], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": "HARD_BLOCK"})

    assert readiness["pearl_scoped_veto_claim_allowed"] is False
    assert "id_scoped_pearl_promotion_gate_passed" in readiness["pearl_scoped_veto_claim_reason"]
    with pytest.raises(ValueError, match="id_scoped_pearl_promotion_gate_passed"):
        assert_pearl_scoped_veto_claim_allowed(paths, {"decision": "HARD_BLOCK"})


def test_step87_scoped_pearl_requires_causal_veto_authorized_first(tmp_path):
    cards = tmp_path / "cards.jsonl"
    card = _causal_card(_scoped_bundle())
    card["runtime_use"] = "policy_or_structural_veto_only"
    _write_cards(cards, [card])

    paths = attach_causal_authority([{"path_id": "p1"}], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": "HARD_BLOCK"})

    assert readiness["pearl_scoped_veto_claim_allowed"] is False
    assert readiness["top_pearl_scoped_veto_authority_class"] == "not_causal_veto"
    assert readiness["pearl_scoped_veto_claim_reason"] == "pearl_scoped_veto_requires_causal_veto_authorized_top_path_first"
