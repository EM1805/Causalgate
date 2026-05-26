from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from causalgate import AgentCausalFirewall, run_product_demo


def test_policy_only_pass_remains_pass_when_tool_guard_disabled() -> None:
    firewall = AgentCausalFirewall(enable_tool_guard=False)
    result = firewall.evaluate(
        action="summarize_dashboard",
        environment="staging",
        risk_level="low",
        action_type="read",
        target_resource="metrics-dashboard",
    )

    assert result.firewall_decision == "PASS"
    assert result.execution_action == "execute"
    assert result.blocked is False
    assert result.needs_approval is False


def test_product_demo_writes_pass_block_review_reports(tmp_path: Path) -> None:
    demo = run_product_demo(out_dir=tmp_path)
    decisions = {case.case_id: case.decision for case in demo.cases}

    assert decisions == {
        "01_read_only_pass": "PASS",
        "02_weak_causal_claim_block": "HARD_BLOCK",
        "03_strong_evidence_review": "REVIEW",
    }
    assert Path(demo.summary_json).exists()
    assert Path(demo.summary_md).exists()
    assert "60-second product demo" in Path(demo.summary_md).read_text(encoding="utf-8")

    for case in demo.cases:
        assert Path(case.report_json).exists()
        assert Path(case.report_md).exists()
        payload = json.loads(Path(case.report_json).read_text(encoding="utf-8"))
        assert payload["firewall_decision"] == case.decision


def test_cli_demo_command_writes_summary(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, "cli.py", "demo", "--out-dir", str(tmp_path)],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert proc.returncode == 0, proc.stderr
    assert "CausalGate demo complete" in proc.stdout
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "summary.md").exists()
