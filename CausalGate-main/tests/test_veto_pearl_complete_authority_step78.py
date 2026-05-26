import csv
import json
from pathlib import Path

import pytest

from common.pearl_global_veto_attestation import (
    PEARL_GLOBAL_REQUIRED_ORACLE_PARITY_MATRIX,
    PEARL_GLOBAL_REQUIRED_PROMOTION_GATE,
    PEARL_GLOBAL_REQUIRED_READINESS_MATRIX,
)
from contracts.causal_authority_for_veto import build_causal_authority_cards
from runtime.causal_authority import (
    PEARL_COMPLETE_VETO_READINESS_MATRIX,
    assert_pearl_complete_veto_claim_allowed,
    attach_causal_authority,
    build_veto_authority_readiness,
)
from runtime.veto_gateway import evaluate_action_request
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


def _causal_card(path_id="destructive_mutation", pearl=None):
    row = {
        "path_id": path_id,
        "authority_level": "identified_runtime_path",
        "runtime_use": "causal_veto_allowed",
        "authority_reason": "specific_runtime_path_matches_identified_offline_contract",
        "contract_identification_status": "identified",
    }
    if pearl is not None:
        row["pearl_veto_authority"] = pearl
    return row


def _full_pearl_bundle():
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
        "primary_formula_authority": "full_recursive_id_canonical_formula_authority",
        "identification_status": "identified",
    }


def test_step78_causal_veto_is_not_pearl_complete_without_full_id_bundle(tmp_path):
    cards = tmp_path / "causal_authority_cards.jsonl"
    _write_cards(cards, [_causal_card()])

    paths = attach_causal_authority([_path()], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": "HARD_BLOCK"})

    assert readiness["causal_veto_claim_allowed"] is True
    assert readiness["pearl_readiness_matrix"] == PEARL_COMPLETE_VETO_READINESS_MATRIX
    assert readiness["top_pearl_veto_authority_class"] == "pearl_complete_veto_not_authorized"
    assert readiness["pearl_complete_veto_claim_allowed"] is False
    assert readiness["pearl_complete_veto_claim_blocked"] is True
    assert "full_recursive_id_implemented" in readiness["pearl_complete_veto_claim_reason"]
    with pytest.raises(ValueError, match="full_recursive_id_implemented"):
        assert_pearl_complete_veto_claim_allowed(paths, {"decision": "HARD_BLOCK"})


def test_step78_pearl_complete_veto_claim_allowed_only_with_full_evidence_bundle(tmp_path):
    cards = tmp_path / "causal_authority_cards.jsonl"
    _write_cards(cards, [_causal_card(pearl=_full_pearl_bundle())])

    paths = attach_causal_authority([_path()], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": "HARD_BLOCK"})

    assert paths[0]["causal_veto_claim_allowed"] is True
    assert paths[0]["pearl_complete_veto_claim_allowed"] is True
    assert paths[0]["pearl_veto_authority_class"] == "pearl_complete_veto_authorized"
    assert readiness["pearl_class_counts"]["pearl_complete_veto_authorized"] == 1
    assert readiness["pearl_complete_veto_claim_allowed"] is True
    assert_pearl_complete_veto_claim_allowed(paths, {"decision": "HARD_BLOCK"})


def test_step78_weak_causal_card_cannot_authorize_pearl_complete_veto(tmp_path):
    cards = tmp_path / "causal_authority_cards.jsonl"
    _write_cards(cards, [
        {
            "path_id": "destructive_mutation",
            "authority_level": "offline_support_weak_or_partial",
            "runtime_use": "policy_veto_with_causal_context",
            "authority_reason": "offline_contract_exists_but_is_not_strong_enough_for_causal_veto",
            "pearl_veto_authority": _full_pearl_bundle(),
        }
    ])

    paths = attach_causal_authority([_path()], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": "HARD_BLOCK"})

    assert readiness["causal_veto_claim_allowed"] is False
    assert readiness["top_pearl_veto_authority_class"] == "not_causal_veto"
    assert readiness["pearl_complete_veto_claim_allowed"] is False
    assert readiness["pearl_complete_veto_claim_reason"] == "pearl_complete_veto_requires_causal_veto_authorized_top_path_first"


def test_step78_gateway_exports_pearl_complete_guard_and_blocks_wording_without_full_id(tmp_path):
    cards = tmp_path / "causal_authority_cards.jsonl"
    _write_cards(cards, [_causal_card()])

    result = evaluate_action_request(
        {
            "action_name": "delete_resource",
            "action_type": "mutation",
            "target_resource": "customer_table",
            "environment": "production",
            "params": {
                "approval_present": True,
                "rollback_available": False,
                "resource_sensitivity": "high",
            },
        },
        authority_cards_path=str(cards),
    )

    readiness = result["veto_authority_readiness"]
    assert readiness["causal_veto_claim_allowed"] is True
    assert readiness["pearl_complete_enforcement_enabled"] is True
    assert readiness["pearl_complete_veto_claim_allowed"] is False
    assert readiness["pearl_complete_claim_guard"] == "no_pearl_complete_veto_claim_without_full_id_readiness_and_full_recursive_id_evidence"
    summary = result["explanations"]["path_explanations"][0]["causal_authority_summary"]
    assert summary["causal_veto_claim_allowed"] is True
    assert summary["pearl_complete_veto_claim_allowed"] is False


def test_step78_contract_card_builder_writes_pearl_bundle_and_keeps_missing_global_flags_blocked(tmp_path):
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
        ])
        writer.writeheader()
        writer.writerow({
            "insight_id": "i1",
            "source": "action",
            "target": "harm",
            "identification_status": "identified",
            "authority_level": "identified_estimable",
            "identified": "1",
            # These mirror the current backend no-overclaim posture.
            "full_recursive_id_implemented": "0",
            "full_id_claim_allowed": "0",
            "id_full_readiness_matrix_passed": "1",
            "id_oracle_parity_fuzz_passed": "1",
            "formal_failure_certificate_coverage_complete": "1",
        })

    cards = build_causal_authority_cards(
        operational_graph_path=graph,
        path_library_path=paths,
        causal_contract_path=contract,
    )

    assert len(cards) == 1
    assert cards[0]["runtime_use"] == "causal_veto_allowed"
    pearl = cards[0]["pearl_veto_authority"]
    assert pearl["full_recursive_id_implemented"] == 0
    assert pearl["full_id_claim_allowed"] == 0
    assert pearl["pearl_complete_evidence_bundle_present"] == 0
    assert "full_recursive_id_implemented" in pearl["missing_required_flags"]
    assert "full_id_claim_allowed" in pearl["missing_required_flags"]
