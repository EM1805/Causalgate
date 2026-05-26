from __future__ import annotations

from pathlib import Path

from causalgate.gate import DecisionGate
from causalgate.mcp.tools import call_tool


class _IdentifiedEngine:
    def identify(self, query):
        return {
            "identified": True,
            "treatment": query.get("treatment", "agent_action"),
            "outcome": query.get("outcome", "task_success"),
            "identification_tier": "identified_canonical",
            "identification_strategy": "identified_observed_dag_truncated_factorization_set_case",
            "formula": "P(Y | X)",
            "full_id_claim_allowed": 1,
            "reason_codes": ["TEST_ID_IDENTIFIED"],
        }


class _RecordingEstimationEngine:
    def __init__(self):
        self.last_query = None

    def estimate(self, query):
        self.last_query = dict(query)
        return {
            "estimated": True,
            "estimation_status": "estimated_with_recording_stub",
            "causal_estimate_available": True,
            "allowed_for_decision": True,
            "estimate_type": "causal_effect_estimate",
            "effect_estimate": 0.42,
            "treatment": query.get("treatment"),
            "outcome": query.get("outcome"),
            "authority_level": query.get("authority_level"),
            "identification_status": query.get("identification_status"),
            "reason_codes": ["TEST_ESTIMATION_AVAILABLE"],
        }


def _base_payload(tmp_path: Path):
    data_path = tmp_path / "panel.csv"
    data_path.write_text("agent_action,task_success\n0,0.1\n1,0.8\n0,0.2\n1,0.9\n", encoding="utf-8")
    return {
        "request_id": "step85-e2e",
        "user_message": "Evaluate whether the agent action improves task success.",
        "candidate_action": "agent_action",
        "action_name": "agent_action",
        "action_type": "analysis_only",
        "treatment": "agent_action",
        "outcome": "task_success",
        "risk_level": "low",
        "reversibility": "reversible",
        "requires_tool": False,
        "scm_graph": {
            "nodes": ["agent_action", "task_success"],
            "edges": [["agent_action", "task_success"]],
        },
        "estimation_query": {
            "data_path": str(data_path),
            "treatment": "agent_action",
            "outcome": "task_success",
        },
    }


def test_decision_gate_chains_identification_into_estimation(tmp_path):
    estimator = _RecordingEstimationEngine()
    result = DecisionGate(
        identification_engine=_IdentifiedEngine(),
        estimation_engine=estimator,
        enable_counterfactual=False,
        enable_risk_policy=False,
        enable_recommender=False,
    ).evaluate(_base_payload(tmp_path)).to_dict()

    assert result["causal_identification"]["identified"] is True
    assert result["causal_estimation"]["estimated"] is True
    assert "SCM_ID_IDENTIFIED" in result["reason_codes"]
    assert "ESTIMATION_AVAILABLE" in result["reason_codes"]

    assert estimator.last_query is not None
    assert estimator.last_query["identification_result"]["identified"] is True
    assert estimator.last_query["identified"] is True
    assert estimator.last_query["allowed_for_estimation"] is True
    assert estimator.last_query["authority_level"] == "identified_estimable"
    assert estimator.last_query["identification_result"]["full_id_claim_allowed"] == 1


def test_mcp_claude_tool_contract_survives_e2e_boundary(tmp_path):
    result = call_tool("causalgate_run_claude_research_cycle", {
        "goal": "Generate a conservative testable causal hypothesis candidate",
        "max_steps": 1,
        "dry_run": True,
        "enable_identification": True,
        "ledger_path": str(tmp_path / "ledger.jsonl"),
        "treatment": "X",
        "outcome": "Y",
        "confounder": "Z",
    })
    assert result["ok"] is True
    assert result["tool"] == "causalgate_run_claude_research_cycle"
    assert result["result"]["dry_run"] is True
    assert result["result"]["steps_completed"] >= 1
    assert result["result"]["step_results"][0]["verdict"]["decision"] in {
        "FINAL_CANDIDATE",
        "REVISE",
        "TEST_MORE",
        "BLOCK",
        "ABSTAIN",
    }
