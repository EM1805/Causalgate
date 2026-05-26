import json
from pathlib import Path

import pytest

from runtime.causal_authority import (
    assert_causal_veto_claim_allowed,
    attach_causal_authority,
    build_veto_authority_readiness,
)
from runtime.veto_gateway import evaluate_action_request


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


def test_step77_authorized_card_allows_causal_veto_claim(tmp_path):
    cards = tmp_path / "causal_authority_cards.jsonl"
    _write_cards(cards, [
        {
            "path_id": "destructive_mutation",
            "authority_level": "identified_runtime_path",
            "runtime_use": "causal_veto_allowed",
            "authority_reason": "specific_runtime_path_matches_identified_offline_contract",
            "contract_identification_status": "identified",
        }
    ])

    paths = attach_causal_authority([_path()], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": "HARD_BLOCK"})

    assert paths[0]["veto_authority_class"] == "causal_veto_authorized"
    assert paths[0]["causal_veto_claim_allowed"] is True
    assert readiness["readiness_matrix"] == "veto_causal_authority_enforcement_readiness_v1_step77"
    assert readiness["class_counts"]["causal_veto_authorized"] == 1
    assert readiness["causal_veto_claim_allowed"] is True
    assert_causal_veto_claim_allowed(paths, {"decision": "HARD_BLOCK"})


def test_step77_weak_card_blocks_causal_veto_claim_but_preserves_context(tmp_path):
    cards = tmp_path / "causal_authority_cards.jsonl"
    _write_cards(cards, [
        {
            "path_id": "destructive_mutation",
            "authority_level": "offline_support_weak_or_partial",
            "runtime_use": "policy_veto_with_causal_context",
            "authority_reason": "offline_contract_exists_but_is_not_strong_enough_for_causal_veto",
            "contract_identification_status": "pending",
        }
    ])

    paths = attach_causal_authority([_path()], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": "HARD_BLOCK"})

    assert paths[0]["veto_authority_class"] == "causal_veto_not_authorized"
    assert paths[0]["causal_veto_claim_allowed"] is False
    assert readiness["class_counts"]["causal_veto_not_authorized"] == 1
    assert readiness["causal_veto_claim_allowed"] is False
    assert readiness["causal_veto_claim_blocked"] is True
    with pytest.raises(ValueError, match="not_strong_enough"):
        assert_causal_veto_claim_allowed(paths, {"decision": "HARD_BLOCK"})


def test_step77_missing_card_is_structural_veto_not_causal_veto(tmp_path):
    cards = tmp_path / "missing_cards.jsonl"
    paths = attach_causal_authority([_path()], cards_path=str(cards))
    readiness = build_veto_authority_readiness(paths, {"decision": "HARD_BLOCK"})

    assert paths[0]["causal_authority"]["runtime_use"] == "policy_or_structural_veto_only"
    assert paths[0]["veto_authority_class"] == "structural_veto"
    assert readiness["class_counts"]["structural_veto"] == 1
    assert readiness["causal_veto_claim_allowed"] is False
    assert readiness["claim_guard"] == "no_causal_veto_claim_without_explicit_authority_card"


def test_step77_gateway_exports_readiness_and_blocks_causal_language_without_authority(tmp_path):
    missing_cards = tmp_path / "no_cards.jsonl"
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
        authority_cards_path=str(missing_cards),
    )

    assert result["decision"]["decision"] == "HARD_BLOCK"
    readiness = result["veto_authority_readiness"]
    assert readiness["enforcement_enabled"] is True
    assert readiness["top_veto_authority_class"] == "structural_veto"
    assert readiness["causal_veto_claim_allowed"] is False
    assert readiness["causal_veto_claim_blocked"] is True
    assert result["activated_paths"][0]["causal_veto_claim_allowed"] is False
    assert result["explanations"]["path_explanations"][0]["causal_authority_summary"]["causal_veto_claim_allowed"] is False


def test_step77_gateway_authorizes_causal_veto_language_only_for_top_authorized_path(tmp_path):
    cards = tmp_path / "causal_authority_cards.jsonl"
    _write_cards(cards, [
        {
            "path_id": "destructive_mutation",
            "authority_level": "identified_runtime_path",
            "runtime_use": "causal_veto_allowed",
            "authority_reason": "specific_runtime_path_matches_identified_offline_contract",
            "contract_identification_status": "identified",
        }
    ])
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
    assert readiness["top_path_id"] == "destructive_mutation"
    assert readiness["top_veto_authority_class"] == "causal_veto_authorized"
    assert readiness["causal_veto_claim_allowed"] is True
    assert result["activated_paths"][0]["veto_authority_class"] == "causal_veto_authorized"
