from __future__ import annotations

import csv
from pathlib import Path

from scm_parts.do_authority_audit import build_do_authority_audit, write_do_authority_audit


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def test_step32_audit_marks_authorized_do_only_when_contract_and_estimate_are_authorized(tmp_path):
    out = tmp_path / "out"
    _write_csv(out / "causal_contract.csv", [{
        "source": "X",
        "target": "Y",
        "treatment_col": "X",
        "outcome_col": "Y",
        "authority_level": "identified_estimable",
        "authority_reason": "id_algorithm_backdoor_verified_symbolic_formula",
        "canonical_id_authority": "1",
        "source_artifacts": "id_algorithm_audit",
        "source_authority": "scm_id_algorithm",
        "id_status": "backdoor_adjustment",
        "id_identified": "1",
        "symbolic_formula_status": "identified_symbolic_formula",
        "identification_strategy": "backdoor_adjustment",
        "estimation_enabled": "1",
    }])
    _write_csv(out / "scm" / "do_estimates.csv", [{
        "treatment": "X",
        "outcome": "Y",
        "do_authorized": "1",
        "do_mode": "identified_backdoor",
        "effect_semantics": "backdoor_adjusted_do_estimand_contract_authorized",
        "effect_estimate": "2.0",
        "reason_codes": "DO_AUTHORIZED_BY_BACKDOOR_CONTRACT",
    }])
    _write_csv(out / "scm" / "do_diagnostics.csv", [{
        "treatment": "X",
        "outcome": "Y",
        "do_authorized": "1",
        "do_mode": "identified_backdoor",
    }])

    rows, manifest = build_do_authority_audit(out_dir=str(out))
    assert manifest["decision_counts"]["authorized_do_estimate"] == 1
    assert rows[0]["final_decision"] == "authorized_do_estimate"
    assert rows[0]["causal_estimate_authorized"] == 1
    assert rows[0]["canonical_id_authority"] == 1


def test_step32_audit_blocks_missing_canonical_id_authority_even_with_estimate_row(tmp_path):
    out = tmp_path / "out"
    _write_csv(out / "causal_contract.csv", [{
        "source": "X",
        "target": "Y",
        "treatment_col": "X",
        "outcome_col": "Y",
        "authority_level": "identified_estimable",
        "canonical_id_authority": "0",
        "id_status": "backdoor_adjustment",
        "id_identified": "1",
        "symbolic_formula_status": "identified_symbolic_formula",
        "identification_strategy": "backdoor_adjustment",
        "estimation_enabled": "1",
    }])
    _write_csv(out / "scm" / "do_estimates.csv", [{
        "treatment": "X",
        "outcome": "Y",
        "do_authorized": "0",
        "do_mode": "blocked",
        "reason_codes": "MISSING_CANONICAL_ID_AUTHORITY",
    }])

    rows, _ = build_do_authority_audit(out_dir=str(out))
    assert rows[0]["final_decision"] == "blocked_missing_canonical_id_authority"
    assert rows[0]["causal_estimate_authorized"] == 0
    assert "MISSING_CANONICAL_ID_AUTHORITY" in rows[0]["audit_reason_codes"]


def test_step32_audit_writes_manifest_and_surfaces_id_hedge_blocks(tmp_path):
    out = tmp_path / "out"
    _write_csv(out / "causal_contract.csv", [{
        "source": "X",
        "target": "Y",
        "treatment_col": "X",
        "outcome_col": "Y",
        "authority_level": "blocked_id_algorithm",
        "canonical_id_authority": "1",
        "source_artifacts": "id_algorithm_audit",
        "source_authority": "scm_id_algorithm",
        "id_status": "blocked_possible_hedge",
        "id_identified": "0",
        "hedge_detected": "1",
        "hedge_status": "possible_hedge",
        "estimation_enabled": "0",
    }])

    paths = write_do_authority_audit(out_dir=str(out))
    assert Path(paths["do_authority_audit"]).exists()
    assert Path(paths["do_authority_manifest"]).exists()

    with Path(paths["do_authority_audit"]).open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["final_decision"] == "blocked_by_id_algorithm"
    assert "ID_HEDGE_DETECTED" in rows[0]["audit_reason_codes"]
