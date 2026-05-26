import json
import subprocess
import sys
from pathlib import Path

from causalgate import AgentCausalFirewall, CausalGateResult


def test_public_agent_causal_firewall_evaluate_blocks_unapproved_prod_mutation():
    firewall = AgentCausalFirewall(enable_tool_guard=True)
    result = firewall.evaluate(
        action="deploy_config_change",
        tool_name="deploy_config_change",
        environment="production",
        risk_level="high",
        action_type="mutation",
        target_resource="payments-service",
        approval_present=False,
        rollback_available=False,
    )

    assert isinstance(result, CausalGateResult)
    assert result.firewall_decision == "HARD_BLOCK"
    assert result.blocked is True
    assert "FIREWALL_BLOCK_DESTRUCTIVE_PROD_NO_APPROVAL" in result.reason_codes
    assert result.decision_digest


def test_public_guard_cli_writes_decision_json(tmp_path):
    out = tmp_path / "guard_result.json"
    subprocess.check_call([
        sys.executable,
        "cli.py",
        "guard",
        "--input",
        "examples/actions/destructive_prod_change.json",
        "--policy",
        "examples/policies/strict_agent_firewall.yaml",
        "--out",
        str(out),
    ])
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["firewall_decision"] == "HARD_BLOCK"
    assert payload["blocked"] is True
    assert payload["tool_name"] == "deploy_config_change"
