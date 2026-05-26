import json
import subprocess
import sys
from pathlib import Path

from causalgate import AgentCausalFirewall, CausalEvidence, CausalGateResult, score_causal_authority
from causalgate.reports import render_markdown_report


STRONG = {
    "identified": True,
    "identification_status": "identified",
    "estimand_type": "total_effect",
    "effect_estimated": True,
    "estimate": 0.18,
    "confidence_interval": [0.09, 0.27],
    "confidence": "high",
    "diagnostics_passed": 5,
    "diagnostics_total": 6,
    "sensitivity_risk": "low",
    "hidden_confounding_risk": "low",
    "sample_size": 1460,
    "scm_available": True,
    "discovery_graph_available": True,
    "placebo_passed": True,
    "negative_controls_passed": True,
    "stability_score": 0.86,
}


WEAK = {
    "identified": False,
    "effect_estimated": False,
    "diagnostics_passed": 0,
    "diagnostics_total": 0,
    "confidence": "low",
    "sample_size": 60,
    "scm_available": False,
}


def test_causal_authority_scores_strong_and_weak_evidence():
    strong = score_causal_authority(CausalEvidence.from_mapping(STRONG), risk_level="high")
    weak = score_causal_authority(CausalEvidence.from_mapping(WEAK), risk_level="high")

    assert strong.authority_score >= 80
    assert strong.authority_decision == "PASS"
    assert weak.authority_score < 40
    assert weak.authority_decision == "HARD_BLOCK"
    assert weak.required_next_steps


def test_firewall_combines_policy_with_causal_authority():
    firewall = AgentCausalFirewall(enable_tool_guard=False)
    result = firewall.evaluate(
        action="increase_ad_spend",
        environment="production",
        risk_level="high",
        action_type="mutation",
        approval_present=True,
        rollback_available=True,
        treatment="ad_spend",
        outcome="revenue",
        evidence=STRONG,
    )

    assert isinstance(result, CausalGateResult)
    assert result.authority_score >= 80
    # Default policy still sends high-risk actions to review even when causal authority is sufficient.
    assert result.firewall_decision == "REVIEW"
    assert result.authority_evaluation["authority_decision"] == "PASS"
    assert "CAUSAL_AUTHORITY_SUFFICIENT" in result.reason_codes


def test_weak_evidence_blocks_even_when_runtime_approval_exists():
    firewall = AgentCausalFirewall(enable_tool_guard=False)
    result = firewall.evaluate(
        action="increase_ad_spend",
        environment="production",
        risk_level="high",
        action_type="mutation",
        approval_present=True,
        rollback_available=True,
        treatment="ad_spend",
        outcome="revenue",
        evidence=WEAK,
    )

    assert result.firewall_decision == "HARD_BLOCK"
    assert result.blocked is True
    assert result.authority_score < 40
    assert "CAUSAL_AUTHORITY_WEAK" in result.reason_codes


def test_markdown_report_includes_authority_score():
    firewall = AgentCausalFirewall(enable_tool_guard=False)
    result = firewall.evaluate(
        action="increase_ad_spend",
        environment="production",
        risk_level="high",
        action_type="mutation",
        approval_present=True,
        rollback_available=True,
        treatment="ad_spend",
        outcome="revenue",
        evidence=STRONG,
    )
    md = render_markdown_report(result)
    assert "Causal authority" in md
    assert "Score" in md
    assert "increase_ad_spend" in md


def test_guard_cli_accepts_evidence_and_writes_reports(tmp_path):
    action = tmp_path / "action.json"
    evidence = tmp_path / "evidence.json"
    out = tmp_path / "guard.json"
    report_json = tmp_path / "report.json"
    report_md = tmp_path / "report.md"

    action.write_text(json.dumps({
        "request_id": "test-cli-step3",
        "action_name": "increase_ad_spend",
        "tool_name": "increase_ad_spend",
        "environment": "production",
        "risk_level": "high",
        "action_type": "mutation",
        "approval_present": True,
        "rollback_available": True,
        "treatment": "ad_spend",
        "outcome": "revenue",
        "require_causal_evidence": True,
    }), encoding="utf-8")
    evidence.write_text(json.dumps(STRONG), encoding="utf-8")

    subprocess.check_call([
        sys.executable,
        "cli.py",
        "guard",
        "--input",
        str(action),
        "--evidence",
        str(evidence),
        "--require-causal-evidence",
        "--disable-tool-guard",
        "--out",
        str(out),
        "--report-json",
        str(report_json),
        "--report-md",
        str(report_md),
    ])

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["authority_evaluation"]["authority_score"] >= 80
    assert report_json.exists()
    assert "Causal authority" in report_md.read_text(encoding="utf-8")
