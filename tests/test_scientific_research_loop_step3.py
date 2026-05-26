from __future__ import annotations

import json
from pathlib import Path

from causalgate.scientific.research_loop import run_research_step
from causalgate.scientific.scientific_ledger import read_scientific_ledger
from causalgate.mcp.tools import call_tool, list_tools


def _valid_hypothesis():
    return {
        "hypothesis_id": "hyp_step3",
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


def test_research_step_writes_ledger(tmp_path: Path):
    ledger_path = tmp_path / "ledger.jsonl"
    result = run_research_step({
        "run_id": "run_step3",
        "step": 1,
        "goal": "Create a conservative hypothesis.",
        "hypothesis": _valid_hypothesis(),
        "ledger_path": str(ledger_path),
        "write_ledger": True,
        "enable_identification": False,
    })

    assert result["run_id"] == "run_step3"
    assert result["step"] == 1
    assert result["verdict"]["decision"] in {"FINAL_CANDIDATE", "TEST_MORE", "REVISE", "BLOCK", "ABSTAIN"}
    assert ledger_path.exists()

    ledger = read_scientific_ledger(path=str(ledger_path), run_id="run_step3", limit=10)
    assert ledger["summary"]["events"] == 1
    assert ledger["events"][0]["event_type"] == "research_step"


def test_research_step_skeleton_requests_revision(tmp_path: Path):
    ledger_path = tmp_path / "ledger.jsonl"
    result = run_research_step({
        "run_id": "run_skeleton",
        "step": 1,
        "goal": "X may affect Y",
        "ledger_path": str(ledger_path),
        "write_ledger": True,
        "enable_identification": False,
    })

    assert result["verdict"]["decision"] in {"REVISE", "BLOCK"}
    assert "missing" in result["verdict"]["reason"].lower() or result["verdict"]["missing_items"]


def test_mcp_tools_include_research_step(tmp_path: Path):
    tool_names = [t["name"] for t in list_tools()["tools"]]
    assert "causalgate_run_research_step" in tool_names
    assert "causalgate_read_scientific_ledger" in tool_names

    ledger_path = tmp_path / "mcp_ledger.jsonl"
    result = call_tool("causalgate_run_research_step", {
        "run_id": "mcp_run_step3",
        "step": 1,
        "hypothesis": _valid_hypothesis(),
        "ledger_path": str(ledger_path),
        "write_ledger": True,
        "enable_identification": False,
    })
    assert result["run_id"] == "mcp_run_step3"
    assert ledger_path.exists()

    read_back = call_tool("causalgate_read_scientific_ledger", {
        "ledger_path": str(ledger_path),
        "run_id": "mcp_run_step3",
        "limit": 5,
    })
    assert read_back["summary"]["events"] == 1
