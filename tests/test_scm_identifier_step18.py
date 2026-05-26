from pathlib import Path

from runtime_env import configure_scientific_runtime
configure_scientific_runtime()

import pandas as pd

from scm_parts.identifier import build_identification_assets
from contracts.causal_contract import build_causal_contract


def test_identifier_declares_legacy_reporting_role():
    text = Path("scm_parts/identifier.py").read_text(encoding="utf-8")
    assert "Legacy SCM identification reporting layer" in text
    assert "legacy_identifier_reporting_wrapper" in text
    assert "legacy_reporting_only" in text
    assert "_apply_canonical_id_authority" in text


def test_identifier_delegates_graph_criteria_and_exposes_canonical_id_fields():
    text = Path("scm_parts/identifier.py").read_text(encoding="utf-8")
    assert "from scm_parts import graph_criteria as _gc" in text
    assert "return _gc.valid_adjustment_sets_for_backdoor" in text
    assert "return _gc.dsep_query_report" in text
    assert "canonical_id_strategy" in text
    assert "canonical_id_proof_steps_json" in text
    assert "canonical_formula_tree_json" in text
    assert "id_algorithm_is_authority" in text


def test_identifier_public_status_is_overwritten_by_canonical_id_block():
    # Legacy Pearl-lite reporting would be tempted to describe X->Y as directly
    # simulable/identified.  Canonical ID must block because X <-> Y is an
    # explicit latent-confounding/bidirected hedge witness.
    scm_graph = {
        "nodes": [
            {"node_id": "X", "node_role": "action", "observed": True},
            {"node_id": "Y", "node_role": "outcome", "observed": True},
        ],
        "edges": [
            {"source": "X", "target": "Y", "edge_kind": "directed"},
            {"source": "X", "target": "Y", "edge_kind": "bidirected"},
        ],
    }
    bridge = pd.DataFrame([{"insight_id": "xy", "treatment_col": "X", "outcome_col": "Y"}])

    assets = build_identification_assets(scm_graph, bridge=bridge)
    effects = assets["identified_effects"]
    assert len(effects) == 1
    row = effects.iloc[0].to_dict()

    assert row["legacy_identifier_authority"] == "legacy_reporting_only"
    assert row["id_algorithm_is_authority"] == 1
    assert row["canonical_id_status"] == "blocked"
    assert row["identified"] == 0
    assert row["identification_status"] == "blocked_by_id_algorithm"
    assert row["effect_claim_authority"] == "no_effect_claim_id_algorithm_blocked"
    assert row["estimation_enabled"] == 0
    assert "blocked_by_canonical_id_algorithm" in row["blocked_by"]

    adj = assets["identified_effects"]
    assert "legacy_identifier_identified" in adj.columns


def test_causal_contract_uses_canonical_fields_from_legacy_identifier_when_id_audit_is_absent(tmp_path):
    out = tmp_path / "out"
    ident_dir = out / "identification"
    ident_dir.mkdir(parents=True)
    pd.DataFrame([
        {
            "insight_id": "xy",
            "source": "X",
            "target": "Y",
            "treatment_col": "X",
            "outcome_col": "Y",
            "identified": 0,
            "identification_status": "blocked_by_id_algorithm",
            "canonical_id_available": 1,
            "canonical_id_status": "blocked",
            "canonical_id_identified": 0,
            "canonical_id_strategy": "blocked_possible_hedge",
            "canonical_id_level": "blocked_unobserved_confounding",
            "canonical_id_reason_codes": "POSSIBLE_HEDGE_OR_LATENT_CONFOUNDING",
            "id_status": "blocked_possible_hedge",
            "id_identified": 0,
            "hedge_detected": 1,
            "hedge_status": "possible_hedge_detected",
            "estimation_enabled": 0,
        }
    ]).to_csv(ident_dir / "identified_effects.csv", index=False)

    rows, manifest = build_causal_contract(out_dir=str(out))
    assert manifest["source_counts"]["identified_effects"] == 1
    assert len(rows) == 0
    assert manifest["n_audit_rows"] == 1
    row = manifest["_audit_rows"][0]
    assert row["authority_level"] == "blocked_id_algorithm"
    assert row["estimation_enabled"] == "0"
    assert row["id_status"] == "blocked_possible_hedge"
    assert "ID_HEDGE_DETECTED" in row["authority_reason"]
