from __future__ import annotations

import csv
import json
from pathlib import Path

from scm_parts.do_authority_audit import write_do_authority_audit
from scm_parts.do_authority_validator import build_do_authority_validation, write_do_authority_validation


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


def test_step33_validator_passes_consistent_authorized_do_chain(tmp_path):
    out = tmp_path / "out"
    _write_csv(out / "causal_contract.csv", [{
        "source": "X",
        "target": "Y",
        "treatment_col": "X",
        "outcome_col": "Y",
        "authority_level": "identified_estimable",
        "canonical_id_authority": "1",
        "source_artifacts": "id_algorithm_audit",
        "source_authority": "scm_id_algorithm",
        "id_status": "backdoor_adjustment",
        "id_identified": "1",
        "symbolic_formula_status": "identified_symbolic_formula",
        "estimation_enabled": "1",
    }])
    _write_csv(out / "scm" / "do_estimates.csv", [{
        "treatment": "X",
        "outcome": "Y",
        "do_authorized": "1",
        "do_mode": "identified_backdoor",
        "effect_estimate": "1.5",
    }])
    write_do_authority_audit(out_dir=str(out))

    rows, manifest = build_do_authority_validation(out_dir=str(out))
    assert manifest["validation_status"] == "pass"
    assert rows[0]["check_name"] == "all_authority_outputs_consistent"


def test_step33_validator_fails_authorized_estimate_without_canonical_id(tmp_path):
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
        "estimation_enabled": "1",
    }])
    _write_csv(out / "scm" / "do_estimates.csv", [{
        "treatment": "X",
        "outcome": "Y",
        "do_authorized": "1",
        "do_mode": "identified_backdoor",
    }])
    write_do_authority_audit(out_dir=str(out))

    rows, manifest = build_do_authority_validation(out_dir=str(out))
    assert manifest["validation_status"] == "fail"
    names = {row["check_name"] for row in rows}
    assert "authorized_estimate_missing_canonical_id" in names
    assert "estimate_authorized_but_audit_not_authorized" in names


def test_step33_validator_writes_manifest_and_flags_orphan_estimate(tmp_path):
    out = tmp_path / "out"
    _write_csv(out / "scm" / "do_estimates.csv", [{
        "treatment": "X",
        "outcome": "Y",
        "do_authorized": "1",
    }])
    write_do_authority_audit(out_dir=str(out))
    paths = write_do_authority_validation(out_dir=str(out))

    assert Path(paths["do_authority_validation"]).exists()
    assert Path(paths["do_authority_validation_manifest"]).exists()
    with Path(paths["do_authority_validation"]).open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["check_name"] == "orphan_estimate_without_contract"
    with Path(paths["do_authority_validation_manifest"]).open("r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["validation_status"] == "fail"


def test_step33_audit_and_validator_block_authorized_estimate_despite_id_block(tmp_path):
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
        "symbolic_formula_status": "blocked_possible_hedge",
        "estimation_enabled": "0",
    }])
    _write_csv(out / "scm" / "do_estimates.csv", [{
        "treatment": "X",
        "outcome": "Y",
        "do_authorized": "1",
        "do_mode": "identified_backdoor",
    }])

    write_do_authority_audit(out_dir=str(out))
    rows, manifest = build_do_authority_validation(out_dir=str(out))
    names = {row["check_name"] for row in rows}
    assert manifest["validation_status"] == "fail"
    assert "authorized_estimate_despite_id_block" in names

    with (out / "scm" / "do_authority_audit.csv").open("r", encoding="utf-8") as f:
        audit_rows = list(csv.DictReader(f))
    assert audit_rows[0]["final_decision"] == "blocked_by_id_algorithm"
    assert audit_rows[0]["causal_estimate_authorized"] == "0"
