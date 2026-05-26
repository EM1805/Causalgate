from runtime_env import configure_scientific_runtime
configure_scientific_runtime()

import pandas as pd

from scm_parts.do_contract import authorize_do, has_canonical_id_authority
from scm_parts.symbolic_numeric import _gate_reasons


def _base_backdoor_row(**overrides):
    row = {
        "treatment_col": "X",
        "outcome_col": "Y",
        "authority_level": "identified_estimable",
        "identification_strategy": "backdoor_adjustment",
        "id_status": "backdoor_adjustment",
        "id_identified": 1,
        "symbolic_formula_status": "identified_symbolic_formula",
        "estimation_enabled": 1,
        "adjustment_set_status": "valid_empty",
        "adjustment_set": "",
    }
    row.update(overrides)
    return row


def test_step31_do_contract_blocks_legacy_backdoor_without_canonical_id_authority():
    row = _base_backdoor_row(source_artifacts="identified_effects", source_authority="formal_identification")
    auth = authorize_do("X", "Y", contract_df=pd.DataFrame([row]))

    assert has_canonical_id_authority(row) is False
    assert auth.do_authorized is False
    assert auth.canonical_id_authority == 0
    assert auth.do_mode == "blocked"
    assert "MISSING_CANONICAL_ID_AUTHORITY" in auth.reason_codes


def test_step31_do_contract_allows_backdoor_only_with_canonical_id_authority():
    row = _base_backdoor_row(
        source_artifacts="identified_effects|id_algorithm_audit",
        source_authority="formal_identification|scm_id_algorithm",
        id_algorithm_level="recursive_id_step2_expression_and_hedge_diagnostic",
    )
    auth = authorize_do("X", "Y", contract_df=pd.DataFrame([row]))

    assert has_canonical_id_authority(row) is True
    assert auth.do_authorized is True
    assert auth.canonical_id_authority == 1
    assert auth.do_mode == "identified_backdoor"
    assert "MISSING_CANONICAL_ID_AUTHORITY" not in auth.reason_codes


def test_step31_symbolic_numeric_requires_canonical_id_authority():
    row = {
        "treatment_col": "X",
        "outcome_col": "Y",
        "authority_level": "identified_estimable",
        "estimation_enabled": 1,
        "symbolic_formula_evaluable": 1,
        "symbolic_numeric_estimator_ready": 1,
        "symbolic_estimator_route": "symbolic_numeric_truncated_factorization",
        "symbolic_formula_status": "identified_symbolic_formula",
        "id_status": "observed_dag_truncated_factorization",
    }
    reasons = _gate_reasons(row)
    assert "MISSING_CANONICAL_ID_AUTHORITY" in reasons

    row["id_algorithm_level"] = "observed_dag_truncated_factorization"
    reasons = _gate_reasons(row)
    assert "MISSING_CANONICAL_ID_AUTHORITY" not in reasons


def test_step31_causal_contract_marks_legacy_identified_row_as_needs_canonical_id(tmp_path):
    from contracts.causal_contract import build_causal_contract

    out = tmp_path / "out"
    ident_dir = out / "identification"
    ident_dir.mkdir(parents=True)
    pd.DataFrame([
        {
            "insight_id": "legacy_xy",
            "source": "X",
            "target": "Y",
            "treatment_col": "X",
            "outcome_col": "Y",
            "identified": 1,
            "identification_status": "identified",
            "identification_strategy": "backdoor_adjustment",
            "estimation_enabled": 1,
            "adjustment_set_status": "valid_empty",
            "adjustment_set": "",
        }
    ]).to_csv(ident_dir / "identified_effects.csv", index=False)

    rows, manifest = build_causal_contract(out_dir=str(out))
    assert manifest["source_counts"]["identified_effects"] == 1
    assert len(rows) == 1
    row = rows[0]
    assert row["canonical_id_authority"] == "0"
    assert row["authority_level"] == "identified_needs_estimation"
    assert row["estimation_enabled"] == "0"
    assert row["effect_claim_authority"] == "no_numeric_do_without_canonical_id_authority"
    assert "missing_canonical_id_authority" in row["authority_reason"]
