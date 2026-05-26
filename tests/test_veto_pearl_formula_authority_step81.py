import csv
import json
from pathlib import Path

import pytest

from common.pearl_global_veto_attestation import (
    PEARL_GLOBAL_REQUIRED_ORACLE_PARITY_MATRIX,
    PEARL_GLOBAL_REQUIRED_PROMOTION_GATE,
    PEARL_GLOBAL_REQUIRED_READINESS_MATRIX,
)
from contracts.causal_authority_for_veto import AUTHORITY_CARD_VERSION, build_causal_authority_cards
from runtime.causal_authority import (
    PEARL_COMPLETE_FORMULA_AUTHORITIES,
    PEARL_COMPLETE_VETO_READINESS_MATRIX,
    assert_pearl_complete_veto_claim_allowed,
    attach_causal_authority,
    build_veto_authority_readiness,
)
from scm_parts.id_step80_audited_fuzz import ID_STEP80_AUDITED_FUZZ_AUTHORITY
from scm_parts.id_global_full_id_controlled_flip import ID_GLOBAL_FULL_ID_CONTROLLED_FLIP_VERSION


def _write_cards(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _path(path_id="destructive_mutation"):
    return {
        "path_id": path_id,
        "severity": "critical",
        "evidence_strength": "structural_plus_graph",
        "graph_supported": True,
        "risk_score": 0.97,
        "hard_block_hits": ["rollback_unavailable"],
    }


def _causal_card(pearl):
    return {
        "path_id": "destructive_mutation",
        "authority_level": "identified_runtime_path",
        "runtime_use": "causal_veto_allowed",
        "authority_reason": "specific_runtime_path_matches_identified_offline_contract",
        "contract_identification_status": "identified",
        "pearl_veto_authority": pearl,
    }


def _pearl_bundle(primary_formula_authority):
    return {
        "full_recursive_id_implemented": 1,
        "full_id_claim_allowed": 1,
        "id_full_readiness_matrix": PEARL_GLOBAL_REQUIRED_READINESS_MATRIX,
        "id_full_readiness_matrix_passed": 1,
        "id_oracle_parity_matrix": PEARL_GLOBAL_REQUIRED_ORACLE_PARITY_MATRIX,
        "id_oracle_parity_fuzz_passed": 1,
        "id_full_promotion_gate": PEARL_GLOBAL_REQUIRED_PROMOTION_GATE,
        "id_full_promotion_gate_passed": 1,
        "id_global_full_id_controlled_flip": ID_GLOBAL_FULL_ID_CONTROLLED_FLIP_VERSION,
        "id_global_full_id_controlled_flip_passed": 1,
        "global_full_id_controlled_flip_allowed": 1,
        "formal_failure_certificate_coverage_complete": 1,
        "formal_failure_certificate_coverage": "complete",
        "primary_formula_authority": primary_formula_authority,
        "identification_status": "identified",
    }


def test_step81_blocks_pearl_complete_when_only_finite_audited_formula_authority(tmp_path):
    cards = tmp_path / "causal_authority_cards.jsonl"
    _write_cards(cards, [_causal_card(_pearl_bundle(ID_STEP80_AUDITED_FUZZ_AUTHORITY))])

    paths = attach_causal_authority([_path()], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": "HARD_BLOCK"})
    pearl = paths[0]["pearl_veto_authority"]

    assert readiness["pearl_readiness_matrix"] == PEARL_COMPLETE_VETO_READINESS_MATRIX
    assert readiness["causal_veto_claim_allowed"] is True
    assert readiness["pearl_complete_veto_claim_allowed"] is False
    assert pearl["pearl_complete_formula_authority_allowed"] == 0
    assert "pearl_complete_formula_authority_allowed" in pearl["missing_required_flags"]
    assert ID_STEP80_AUDITED_FUZZ_AUTHORITY not in PEARL_COMPLETE_FORMULA_AUTHORITIES
    with pytest.raises(ValueError, match="pearl_complete_formula_authority_allowed"):
        assert_pearl_complete_veto_claim_allowed(paths, {"decision": "HARD_BLOCK"})


def test_step81_all_flags_plus_full_recursive_formula_authority_allows_future_pearl_claim(tmp_path):
    cards = tmp_path / "causal_authority_cards.jsonl"
    _write_cards(cards, [_causal_card(_pearl_bundle("full_recursive_id_canonical_formula_authority"))])

    paths = attach_causal_authority([_path()], cards_path=str(cards))
    readiness = assert_pearl_complete_veto_claim_allowed(paths, {"decision": "HARD_BLOCK"})

    assert paths[0]["pearl_veto_authority"]["pearl_complete_formula_authority_allowed"] == 1
    assert paths[0]["pearl_complete_veto_claim_allowed"] is True
    assert readiness["pearl_complete_veto_claim_allowed"] is True
    assert "full_recursive_id_canonical_formula_authority" in readiness["pearl_complete_allowed_formula_authorities"]


def test_step81_contract_card_builder_blocks_canonical_or_audited_authority_even_when_flags_are_green(tmp_path):
    graph = tmp_path / "operational_graph.json"
    graph.write_text(json.dumps({
        "nodes": [
            {"id": "action", "aliases": ["delete_resource"]},
            {"id": "harm", "aliases": ["customer_table_loss"]},
            {"id": "harm_event", "aliases": ["customer_table_loss"]},
        ],
        "path_hints": {
            "harm": {
                "path_id": "destructive_mutation",
                "treatment_node": "action",
                "outcome_node": "harm",
            }
        },
    }), encoding="utf-8")
    paths = tmp_path / "dangerous_paths.json"
    paths.write_text(json.dumps({
        "paths": {
            "destructive_mutation": {
                "graph_harm": "harm",
                "severity": "critical",
                "reversibility": "irreversible",
            }
        }
    }), encoding="utf-8")
    contract = tmp_path / "causal_contract.csv"
    with contract.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "insight_id", "source", "target", "identification_status", "authority_level", "identified",
            "full_recursive_id_implemented", "full_id_claim_allowed", "id_full_readiness_matrix_passed",
            "id_oracle_parity_fuzz_passed", "formal_failure_certificate_coverage_complete", "primary_formula_authority",
        ])
        writer.writeheader()
        writer.writerow({
            "insight_id": "i1",
            "source": "action",
            "target": "harm",
            "identification_status": "identified",
            "authority_level": "identified_estimable",
            "identified": "1",
            "full_recursive_id_implemented": "1",
            "full_id_claim_allowed": "1",
            "id_full_readiness_matrix_passed": "1",
            "id_oracle_parity_fuzz_passed": "1",
            "formal_failure_certificate_coverage_complete": "1",
            "primary_formula_authority": "id_canonical_formula_step60",
        })

    cards = build_causal_authority_cards(
        operational_graph_path=graph,
        path_library_path=paths,
        causal_contract_path=contract,
    )

    pearl = cards[0]["pearl_veto_authority"]
    assert cards[0]["authority_card_version"] == AUTHORITY_CARD_VERSION
    assert cards[0]["runtime_use"] == "causal_veto_allowed"
    assert pearl["pearl_complete_formula_authority_allowed"] == 0
    assert pearl["pearl_complete_evidence_bundle_present"] == 0
    assert "pearl_complete_formula_authority_allowed" in pearl["missing_required_flags"]
