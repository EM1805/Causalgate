from scm_parts.do_contract import authorize_do, has_canonical_id_authority
from scm_parts.legacy_boundary import (
    annotate_legacy_identifier_row,
    annotate_legacy_identifier_rows,
    is_canonical_id_provenance,
    is_legacy_identification_provenance,
    legacy_boundary_reason,
)


def _contract_row(**overrides):
    row = {
        "treatment_col": "X",
        "outcome_col": "Y",
        "authority_level": "identified_estimable",
        "identification_strategy": "backdoor_adjustment",
        "adjustment_set": "Z",
        "adjustment_set_status": "valid_nonempty",
        "estimation_enabled": 1,
        "symbolic_formula_status": "identified_symbolic_formula",
    }
    row.update(overrides)
    return row


def test_legacy_identifier_provenance_is_reporting_only():
    row = _contract_row(
        source_artifacts="identification/identified_effects.csv|adjustment_sets_csv",
        source_authority="scm_parts.identifier",
    )

    assert is_legacy_identification_provenance(row)
    assert not is_canonical_id_provenance(row)
    assert legacy_boundary_reason(row) == "legacy_identification_reporting_only"
    assert not has_canonical_id_authority(row)


def test_canonical_id_algorithm_provenance_is_authority():
    row = _contract_row(
        source_artifacts="id_algorithm_audit",
        source_authority="scm_id_algorithm",
        id_algorithm_level="limited_id_supported_backdoor_dsep_verified",
    )

    assert not is_legacy_identification_provenance(row)
    assert is_canonical_id_provenance(row)
    assert legacy_boundary_reason(row) == "canonical_id_authority"
    assert has_canonical_id_authority(row)


def test_do_authorization_blocks_legacy_only_backdoor_contract():
    import pandas as pd

    legacy_contract = pd.DataFrame([
        _contract_row(
            source_artifacts="identification/identified_effects.csv",
            source_authority="scm_parts.identifier",
        )
    ])

    auth = authorize_do("X", "Y", contract_df=legacy_contract)

    assert not auth.do_authorized
    assert auth.do_mode == "blocked"
    assert auth.canonical_id_authority == 0
    assert "MISSING_CANONICAL_ID_AUTHORITY" in auth.reason_codes


def test_do_authorization_allows_canonical_backdoor_contract():
    import pandas as pd

    canonical_contract = pd.DataFrame([
        _contract_row(
            source_artifacts="id_algorithm_audit",
            source_authority="scm_id_algorithm",
            id_algorithm_level="limited_id_supported_backdoor_dsep_verified",
        )
    ])

    auth = authorize_do("X", "Y", contract_df=canonical_contract)

    assert auth.do_authorized
    assert auth.do_mode == "identified_backdoor"
    assert auth.canonical_id_authority == 1


def test_annotate_legacy_identifier_row_marks_reporting_only_without_canonical_authority():
    row = _contract_row(source_artifacts="existing_artifact")

    annotated = annotate_legacy_identifier_row(row, artifact="identification/identified_effects.csv")

    assert annotated is not row
    assert annotated["source_artifacts"] == "existing_artifact|identification/identified_effects.csv"
    assert annotated["source_authority"] == "legacy_identifier_report"
    assert annotated["audit_source"] == "scm_parts.identifier"
    assert annotated["legacy_identifier_authority"] == "legacy_reporting_only"
    assert annotated["legacy_boundary_reason"] == "legacy_identification_reporting_only"
    assert annotated["canonical_id_available"] == 0
    assert is_legacy_identification_provenance(annotated)
    assert not is_canonical_id_provenance(annotated)
    assert not has_canonical_id_authority(annotated)


def test_annotate_legacy_identifier_rows_handles_sequences():
    rows = [_contract_row(treatment_col="X1"), _contract_row(treatment_col="X2")]

    annotated = annotate_legacy_identifier_rows(rows, artifact="identification/adjustment_sets.csv")

    assert len(annotated) == 2
    assert all(row["source_artifacts"].endswith("identification/adjustment_sets.csv") for row in annotated)
    assert all(row["legacy_identifier_authority"] == "legacy_reporting_only" for row in annotated)
