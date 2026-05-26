import csv
import json
from pathlib import Path

import pytest

from common.pearl_global_veto_attestation import (
    PEARL_GLOBAL_REQUIRED_ORACLE_PARITY_MATRIX,
    PEARL_GLOBAL_REQUIRED_READINESS_MATRIX,
)
from contracts.causal_authority_for_veto import AUTHORITY_CARD_VERSION, build_causal_authority_cards
from runtime.causal_authority import (
    PEARL_COMPLETE_VETO_READINESS_MATRIX,
    assert_pearl_complete_veto_claim_allowed,
    attach_causal_authority,
    build_veto_authority_readiness,
)
from scm_parts.id_full_promotion_gate import ID_FULL_PROMOTION_GATE_VERSION
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


def _full_pearl_bundle(*, promotion_gate_passed=0):
    return {
        "full_recursive_id_implemented": 1,
        "full_id_claim_allowed": 1,
        "id_full_readiness_matrix": PEARL_GLOBAL_REQUIRED_READINESS_MATRIX,
        "id_full_readiness_matrix_passed": 1,
        "id_oracle_parity_matrix": PEARL_GLOBAL_REQUIRED_ORACLE_PARITY_MATRIX,
        "id_oracle_parity_fuzz_passed": 1,
        "formal_failure_certificate_coverage_complete": 1,
        "formal_failure_certificate_coverage": "complete",
        "primary_formula_authority": "full_recursive_id_canonical_formula_authority",
        "identification_status": "identified",
        "id_full_promotion_gate": ID_FULL_PROMOTION_GATE_VERSION,
        "id_full_promotion_gate_passed": promotion_gate_passed,
        "id_global_full_id_controlled_flip": ID_GLOBAL_FULL_ID_CONTROLLED_FLIP_VERSION,
        "id_global_full_id_controlled_flip_passed": 1,
        "global_full_id_controlled_flip_allowed": 1,
    }


def test_step82_pearl_complete_veto_requires_full_id_promotion_gate_even_when_other_flags_green(tmp_path):
    cards = tmp_path / "causal_authority_cards.jsonl"
    _write_cards(cards, [_causal_card(_full_pearl_bundle(promotion_gate_passed=0))])

    paths = attach_causal_authority([_path()], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": "HARD_BLOCK"})

    assert readiness["pearl_readiness_matrix"] == PEARL_COMPLETE_VETO_READINESS_MATRIX
    assert readiness["pearl_complete_veto_claim_allowed"] is False
    assert paths[0]["pearl_veto_authority"]["id_full_promotion_gate_passed"] == 0
    assert "id_full_promotion_gate_passed" in paths[0]["pearl_veto_authority"]["missing_required_flags"]
    assert "id_full_promotion_gate_passed" in readiness["pearl_complete_veto_claim_reason"]
    assert readiness["pearl_complete_promotion_gate_guard"] == "no_pearl_complete_veto_claim_without_step82_full_id_promotion_gate_and_step94_controlled_global_full_id_flip"
    with pytest.raises(ValueError, match="id_full_promotion_gate_passed"):
        assert_pearl_complete_veto_claim_allowed(paths, {"decision": "HARD_BLOCK"})


def test_step82_pearl_complete_veto_future_fixture_allows_only_when_promotion_gate_passes(tmp_path):
    cards = tmp_path / "causal_authority_cards.jsonl"
    _write_cards(cards, [_causal_card(_full_pearl_bundle(promotion_gate_passed=1))])

    paths = attach_causal_authority([_path()], cards_path=str(cards))
    readiness = assert_pearl_complete_veto_claim_allowed(paths, {"decision": "HARD_BLOCK"})

    assert paths[0]["pearl_complete_veto_claim_allowed"] is True
    assert readiness["pearl_complete_veto_claim_allowed"] is True
    assert paths[0]["pearl_veto_authority"]["id_full_promotion_gate"] == ID_FULL_PROMOTION_GATE_VERSION


def test_step82_contract_card_builder_writes_promotion_gate_field_and_keeps_current_backend_blocked(tmp_path):
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
            "id_oracle_parity_fuzz_passed", "formal_failure_certificate_coverage_complete",
            "primary_formula_authority", "id_full_promotion_gate", "id_full_promotion_gate_passed",
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
            "primary_formula_authority": "full_recursive_id_canonical_formula_authority",
            "id_full_promotion_gate": ID_FULL_PROMOTION_GATE_VERSION,
            "id_full_promotion_gate_passed": "0",
        })

    cards = build_causal_authority_cards(
        operational_graph_path=graph,
        path_library_path=paths,
        causal_contract_path=contract,
    )

    pearl = cards[0]["pearl_veto_authority"]
    assert cards[0]["authority_card_version"] == AUTHORITY_CARD_VERSION
    assert cards[0]["runtime_use"] == "causal_veto_allowed"
    assert pearl["id_full_promotion_gate"] == ID_FULL_PROMOTION_GATE_VERSION
    assert pearl["id_full_promotion_gate_passed"] == 0
    assert pearl["pearl_complete_evidence_bundle_present"] == 0
    assert "id_full_promotion_gate_passed" in pearl["missing_required_flags"]
