from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from causalgate.api.server import app, guard_action, health_payload


def _strong_evidence() -> dict:
    return json.loads(Path("examples/evidence/marketing_strong_evidence.json").read_text(encoding="utf-8"))


def test_product_api_health_payload() -> None:
    payload = health_payload()
    assert payload["status"] == "ok"
    assert payload["service"] == "causalgate-api"
    assert payload["endpoints"]["guard"] == "/v1/guard"
    assert "PASS" in payload["decisions"]


def test_guard_action_returns_authority_decision() -> None:
    result = guard_action(
        {
            "action": "increase_ad_spend",
            "tool_name": "marketing_budget.write",
            "environment": "production",
            "risk_level": "high",
            "action_type": "mutation",
            "target_resource": "paid-search-budget",
            "approval_present": True,
            "rollback_available": True,
            "treatment": "ad_spend",
            "outcome": "revenue",
            "require_causal_evidence": True,
            "causal_evidence": _strong_evidence(),
        }
    )

    payload = result.to_dict()
    assert payload["firewall_decision"] in {"REVIEW", "PASS"}
    assert payload["authority_evaluation"]["authority_score"] >= 55
    assert payload["authority_evaluation"]["authority_decision"] in {"REVIEW", "PASS"}
    assert payload["decision_digest"]


def test_fastapi_guard_endpoint_blocks_missing_required_evidence() -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/guard",
        json={
            "action": "increase_ad_spend",
            "risk_level": "high",
            "environment": "production",
            "action_type": "mutation",
            "approval_present": True,
            "rollback_available": True,
            "treatment": "ad_spend",
            "outcome": "revenue",
            "require_causal_evidence": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["firewall_decision"] == "HARD_BLOCK"
    assert payload["authority_evaluation"]["authority_score"] < 40
    assert "CAUSAL_AUTHORITY_WEAK" in payload["reason_codes"]


def test_fastapi_guard_markdown_endpoint() -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/guard/markdown",
        json={
            "action": "summarize_dashboard",
            "tool_name": "summarize_dashboard",
            "risk_level": "low",
            "environment": "staging",
            "action_type": "read",
        },
    )

    assert response.status_code == 200
    assert "# CausalGate Agent Action Report" in response.text
    assert "summarize_dashboard" in response.text


def test_fastapi_demo_endpoint_writes_reports(tmp_path: Path) -> None:
    client = TestClient(app)
    response = client.post("/v1/demo", json={"out_dir": str(tmp_path)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["output_dir"] == str(tmp_path)
    assert len(payload["cases"]) == 3
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "summary.md").exists()
