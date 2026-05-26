# Causal Authority Layer

Step 3 adds the product layer that makes CausalGate more than a generic guardrail.
The firewall can now ask:

> Does this AI agent have enough causal authority to take or recommend this action?

The authority layer sits between the policy check and execution:

```text
agent action
→ trusted runtime context
→ optional CausalEvidence package
→ CausalAuthorityScore
→ policy + authority merge
→ PASS / REVIEW / HARD_BLOCK
→ JSON or Markdown audit report
```

## Public API

```python
from causalgate import AgentCausalFirewall, CausalEvidence

firewall = AgentCausalFirewall(enable_tool_guard=False)
evidence = CausalEvidence.from_file("examples/evidence/marketing_strong_evidence.json")

result = firewall.evaluate(
    action="increase_ad_spend",
    environment="production",
    risk_level="high",
    action_type="mutation",
    approval_present=True,
    rollback_available=True,
    treatment="ad_spend",
    outcome="revenue",
    evidence=evidence,
)

print(result.firewall_decision)
print(result.authority_score)
print(result.to_markdown())
```

## Evidence package

A `CausalEvidence` object describes the causal chain behind an action:

```json
{
  "identified": true,
  "identification_status": "identified",
  "estimand_type": "total_effect",
  "effect_estimated": true,
  "estimate": 0.18,
  "confidence_interval": [0.09, 0.27],
  "confidence": "high",
  "diagnostics_passed": 5,
  "diagnostics_total": 6,
  "sensitivity_risk": "low",
  "hidden_confounding_risk": "low",
  "sample_size": 1460,
  "scm_available": true,
  "discovery_graph_available": true,
  "placebo_passed": true,
  "negative_controls_passed": true,
  "stability_score": 0.86
}
```

## Score bands

```text
0–39   weak authority      → HARD_BLOCK
40–69  partial authority   → REVIEW
70–100 sufficient authority → PASS, unless policy/risk requires review
```

High-impact actions are stricter:

```text
high/critical risk with score < 55 → HARD_BLOCK
high/critical risk with score < 80 → REVIEW
```

This means strong evidence can satisfy the causal authority gate, while the policy layer may still route a high-risk production action to human approval.

## CLI

```bash
causalgate guard \
  --input examples/actions/marketing_spend_increase.json \
  --evidence examples/evidence/marketing_strong_evidence.json \
  --require-causal-evidence \
  --report-json out/marketing_guard_report.json \
  --report-md out/marketing_guard_report.md
```

Correlation-only evidence should fail closed:

```bash
causalgate guard \
  --input examples/actions/marketing_spend_increase.json \
  --evidence examples/evidence/marketing_weak_evidence.json \
  --require-causal-evidence
```

## Commercial meaning

The product claim is now sharper:

> CausalGate does not only ask whether an action is risky. It asks whether the agent has sufficient causal authority to act.

This is the defensible commercial layer on top of discovery, SCM identification, estimation and diagnostics.
