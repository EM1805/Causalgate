from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scm_parts.scm_counterfactual import evaluate_counterfactual_audit_rows, write_scm_counterfactual_audit


def test_counterfactual_audit_rows_are_id_gated():
    graph = {
        "id_algorithm_audit": [
            {"treatment": "agent_action", "outcome": "risk", "identifiable": 1, "id_strategy": "observed_dag_truncated_factorization", "id_algorithm_level": "observed_dag", "estimand_formula": "P(risk|do(agent_action))", "reason_codes": "OBSERVED_DAG"},
            {"treatment": "latent_action", "outcome": "risk", "identifiable": 0, "id_strategy": "blocked", "id_algorithm_level": "recursive_id_skeleton_blocked", "reason_codes": "POSSIBLE_HEDGE"},
        ]
    }
    rows = evaluate_counterfactual_audit_rows(scm_graph=graph)
    assert len(rows) == 2
    assert rows[0]["counterfactual_authority"] == "authorized_interventional_estimand"
    assert rows[1]["counterfactual_authority"] == "blocked"
    assert "NO_ID_NO_COUNTERFACTUAL_AUTHORITY" in rows[1]["reason_codes"]


def test_write_counterfactual_audit_outputs(tmp_path):
    graph = {"id_algorithm_audit": [{"treatment": "a", "outcome": "y", "identifiable": 0}]}
    paths = write_scm_counterfactual_audit(scm_graph=graph, out_dir=str(tmp_path))
    assert "scm_counterfactual_authority_csv" in paths
    assert "scm_counterfactual_summary_json" in paths
    assert (tmp_path / "scm" / "scm_counterfactual_authority.csv").exists()
    assert (tmp_path / "scm" / "scm_counterfactual_summary.json").exists()
