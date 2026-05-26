from causalgate.integrations.claude import (
    ClaudeAPIClient,
    build_scientific_research_prompt,
    build_scientific_system_prompt,
    extract_first_json_object,
    run_claude_research_cycle,
)
from causalgate.mcp.tools import call_tool


def test_claude_prompt_mentions_required_scientific_fields():
    text = build_scientific_system_prompt() + "\n" + build_scientific_research_prompt({"goal": "test X and Y"})
    assert "hypothesis candidate" in text
    assert "measurable" in text
    assert "negative control" in text
    assert "placebo" in text
    assert "claim_level" in text


def test_extract_first_json_object_from_fenced_text():
    decoded = extract_first_json_object('before ```json\n{"hypothesis": {"claim": "X may affect Y"}}\n``` after')
    assert decoded["hypothesis"]["claim"] == "X may affect Y"


def test_dry_run_client_returns_hypothesis_without_api_key():
    client = ClaudeAPIClient(api_key=None, dry_run=True)
    hypothesis = client.propose_hypothesis({"goal": "dry run", "treatment": "X", "outcome": "Y", "confounder": "Z"})
    assert hypothesis["claim_level"] == "hypothesis_only"
    assert hypothesis["variables"]["treatment"] == "X"
    assert "negative control outcome" in hypothesis["falsification_tests"]


def test_run_claude_research_cycle_dry_run(tmp_path):
    result = run_claude_research_cycle({
        "goal": "Generate a conservative testable candidate",
        "max_steps": 2,
        "dry_run": True,
        "enable_identification": False,
        "ledger_path": str(tmp_path / "ledger.jsonl"),
    })
    assert result["dry_run"] is True
    assert result["steps_completed"] >= 1
    assert result["final_decision"] in {"FINAL_CANDIDATE", "REVISE", "TEST_MORE", "BLOCK", "ABSTAIN"}
    assert result["step_results"]


def test_mcp_claude_research_cycle_tool_dry_run(tmp_path):
    result = call_tool("causalgate_run_claude_research_cycle", {
        "goal": "Generate a conservative testable candidate",
        "max_steps": 1,
        "dry_run": True,
        "enable_identification": False,
        "ledger_path": str(tmp_path / "ledger.jsonl"),
    })
    assert result["ok"] is True
    assert result["tool"] == "causalgate_run_claude_research_cycle"
    assert result["result"]["dry_run"] is True
