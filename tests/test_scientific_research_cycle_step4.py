from __future__ import annotations

from pathlib import Path

from causalgate.scientific.research_cycle import run_research_cycle
from causalgate.scientific.scientific_ledger import read_scientific_ledger
from causalgate.mcp.tools import call_tool, list_tools


def _valid_hypothesis(hypothesis_id: str = "hyp_cycle_valid"):
    return {
        "hypothesis_id": hypothesis_id,
        "claim": "X may causally influence Y through M, controlling for Z.",
        "claim_level": "hypothesis_only",
        "variables": {
            "treatment": "X",
            "outcome": "Y",
            "mediators": ["M"],
            "confounders": ["Z"],
        },
        "dag": {"edges": [["Z", "X"], ["Z", "Y"], ["X", "M"], ["M", "Y"]]},
        "assumptions": ["Z is observed", "X occurs before Y"],
        "adjustment_set": ["Z"],
        "measurable_predictions": ["If X increases, Y should increase within a 7-day lag after controlling for Z."],
        "falsification_tests": ["negative control outcome", "future-X placebo test", "hidden confounding sensitivity check"],
        "negative_controls": ["Negative control outcome N should not change."],
        "placebo_tests": ["future-X placebo test"],
        "sensitivity_checks": ["hidden confounding sensitivity check"],
        "data_requirements": ["time ordered data", "observed Z"],
        "test_plan": "Estimate adjusted X->Y and compare with negative control and future-X placebo.",
    }


def test_research_cycle_runs_candidate_and_writes_summary(tmp_path: Path):
    ledger_path = tmp_path / "cycle_ledger.jsonl"
    result = run_research_cycle({
        "run_id": "cycle_step4",
        "goal": "Create a conservative hypothesis.",
        "max_steps": 3,
        "candidate_hypotheses": [_valid_hypothesis()],
        "ledger_path": str(ledger_path),
        "write_ledger": True,
        "enable_identification": False,
    })

    assert result["run_id"] == "cycle_step4"
    assert result["steps_completed"] == 1
    assert result["final_decision"] in {"FINAL_CANDIDATE", "TEST_MORE", "REVISE", "BLOCK", "ABSTAIN"}
    assert ledger_path.exists()

    ledger = read_scientific_ledger(path=str(ledger_path), run_id="cycle_step4", limit=10)
    assert ledger["summary"]["events"] >= 2
    assert ledger["events"][-1]["event_type"] == "research_cycle_summary"


def test_research_cycle_pauses_when_revision_needed_without_next_candidate(tmp_path: Path):
    ledger_path = tmp_path / "cycle_pause_ledger.jsonl"
    weak = {
        "hypothesis_id": "weak_cycle_hyp",
        "claim": "X may affect Y.",
        "claim_level": "hypothesis_only",
    }
    result = run_research_cycle({
        "run_id": "cycle_pause",
        "goal": "Create a conservative hypothesis.",
        "max_steps": 5,
        "candidate_hypotheses": [weak],
        "ledger_path": str(ledger_path),
        "write_ledger": True,
        "enable_identification": False,
    })

    assert result["status"] == "awaiting_llm_revision"
    assert result["should_continue"] is True
    assert result["steps_completed"] == 1
    assert result["next_instruction"]


def test_mcp_tools_include_research_cycle(tmp_path: Path):
    tool_names = [t["name"] for t in list_tools()["tools"]]
    assert "causalgate_run_research_cycle" in tool_names

    ledger_path = tmp_path / "mcp_cycle_ledger.jsonl"
    result = call_tool("causalgate_run_research_cycle", {
        "run_id": "mcp_cycle_step4",
        "max_steps": 2,
        "candidate_hypotheses": [_valid_hypothesis("mcp_cycle_hyp")],
        "ledger_path": str(ledger_path),
        "write_ledger": True,
        "enable_identification": False,
    })
    assert result["run_id"] == "mcp_cycle_step4"
    assert result["steps_completed"] == 1
    assert ledger_path.exists()
