# CausalGate API Server

CausalGate exposes a small product HTTP API for integrating the causal firewall into AI-agent runtimes, dashboards, workflow engines, and enterprise review systems.

The API is intentionally focused on the commercial product path:

```text
agent action package
→ POST /v1/guard
→ policy + causal authority check
→ PASS / REVIEW / HARD_BLOCK
→ JSON or Markdown audit report
```

## Run locally

Install server dependencies:

```bash
python -m pip install -e .[server]
```

Run through the CLI:

```bash
causalgate api --host 0.0.0.0 --port 8000
```

Or run directly with uvicorn:

```bash
uvicorn causalgate.api.server:app --host 0.0.0.0 --port 8000
```

Open the generated OpenAPI docs at:

```text
http://localhost:8000/docs
```

## Health check

```bash
curl http://localhost:8000/v1/health
```

Returns service metadata, decision labels and authority score bands.

## Guard an agent action

```bash
curl -X POST http://localhost:8000/v1/guard \
  -H 'content-type: application/json' \
  -d '{
    "action": "increase_ad_spend",
    "tool_name": "marketing_budget.write",
    "environment": "production",
    "risk_level": "high",
    "action_type": "mutation",
    "target_resource": "campaign_budget",
    "approval_present": true,
    "rollback_available": true,
    "treatment": "ad_spend",
    "outcome": "revenue",
    "require_causal_evidence": true,
    "causal_evidence": {
      "identified": true,
      "effect_estimated": true,
      "estimate": 0.18,
      "confidence": "medium",
      "confidence_interval": [0.04, 0.31],
      "diagnostics_passed": 4,
      "diagnostics_total": 6,
      "sensitivity_risk": "medium",
      "hidden_confounding_risk": "medium",
      "sample_size": 1200,
      "scm_available": true,
      "discovery_graph_available": true
    }
  }'
```

Expected response shape:

```json
{
  "firewall_decision": "REVIEW",
  "execution_action": "ask_user",
  "authority_score": 64,
  "summary": "CausalGate routed tool 'marketing_budget.write' to human/approval review before execution. Causal authority score: 64/100 (partial_for_high_impact)."
}
```

The real response contains the full policy evaluation, causal authority evaluation, audit event, digest and evidence package.

## Markdown audit report

```bash
curl -X POST http://localhost:8000/v1/guard/markdown \
  -H 'content-type: application/json' \
  -d @examples/actions/marketing_spend_increase.json
```

This returns the same decision rendered as a Markdown audit report.

## Demo endpoint

```bash
curl -X POST http://localhost:8000/v1/demo \
  -H 'content-type: application/json' \
  -d '{"out_dir":"out/api-demo"}'
```

The endpoint writes the 60-second demo reports and returns their paths plus summary metadata.

## Production notes

The API is a **pre-execution decision service**. It does not execute tools. Callers should execute their own tool only after a `PASS`, and route `REVIEW` or `HARD_BLOCK` according to their enterprise policy.

By default, the API runs in policy-only/decision-service mode with ToolGuard disabled. Enable deeper ToolGuard checks by passing:

```json
{"enable_tool_guard": true}
```

For audit logging, set:

```bash
export CAUSALGATE_API_AUDIT_LOG=out/audit/agent_decisions.jsonl
```
