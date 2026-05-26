# CausalGate

**CausalGate is a source-available causal firewall for AI agents.**

It checks whether an agent recommendation, tool call, or high-impact action has enough causal authority before the action is allowed, warned, blocked, or routed to human review.

```text
agent proposes an action
→ CausalGate checks policy + causal authority
→ discovery / SCM / identification / estimation / diagnostics when evidence is supplied
→ decision: PASS / REVIEW / HARD_BLOCK
```

CausalGate does **not** prove causality or replace human review. It enforces a reproducible decision gate around causal evidence, trusted runtime context, audit trails, and explicit policy.

## Why this exists

AI agents increasingly recommend or execute actions. Many proposed actions are justified with correlations, weak evidence, or unsupported causal language. CausalGate adds an evidence boundary between the agent and the action.

Typical use cases:

```text
Marketing agent:     review spend increases unless effect evidence is strong enough
Ops agent:           block destructive production changes without approval + rollback
Product agent:       warn before acting on correlation-only feature claims
Finance/risk agent:  require review before high-impact external or real-money actions
```

## Quick start

Install locally:

```bash
python -m pip install -e .[server,test]
```

Use the product API:

```python
from causalgate import AgentCausalFirewall

firewall = AgentCausalFirewall()

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

print(result.firewall_decision)   # PASS, REVIEW, or HARD_BLOCK
print(result.execution_action)    # execute, execute_with_warning, ask_user, or block
print(result.summary)
```

Use the CLI:

```bash
causalgate guard \
  --action deploy_config_change \
  --environment production \
  --risk-level high \
  --action-type mutation \
  --target-resource payments-service
```

Evaluate a JSON action package:

```bash
causalgate guard --input examples/actions/destructive_prod_change.json --out out/guard_result.json
```



## 60-second product demo

Run the product demo to see all three outcomes in one place: `PASS`, `HARD_BLOCK`, and `REVIEW`.

```bash
causalgate demo --out-dir out/demo --pretty
```

The demo writes one Markdown and one JSON audit report per case:

```text
01_read_only_pass             -> PASS
02_weak_causal_claim_block    -> HARD_BLOCK
03_strong_evidence_review     -> REVIEW
```

This is the core sales story: CausalGate does not merely ask whether an agent action is risky. It asks whether the agent has enough causal authority to act.

See [`docs/DEMO.md`](docs/DEMO.md).



## Product API server

Run CausalGate as an HTTP decision service for agent runtimes, dashboards or enterprise review queues:

```bash
python -m pip install -e .[server]
causalgate api --host 0.0.0.0 --port 8000
```

Core endpoints:

```text
GET  /v1/health
POST /v1/guard
POST /v1/guard/markdown
POST /v1/demo
```

Example request:

```bash
curl -X POST http://localhost:8000/v1/guard \
  -H 'content-type: application/json' \
  -d @examples/actions/marketing_spend_increase.json
```

The API returns the same product decision package as the Python API and CLI: `PASS`, `REVIEW` or `HARD_BLOCK`, plus causal authority score, reasons, required next steps and a decision digest.

See [`docs/API_SERVER.md`](docs/API_SERVER.md).

## Step 3: causal authority layer

CausalGate now accepts a `CausalEvidence` package and computes a decision-grade causal authority score before an agent acts.

```python
from causalgate import AgentCausalFirewall, CausalEvidence

firewall = AgentCausalFirewall()
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
```

Score bands:

```text
0–39   weak authority      → HARD_BLOCK
40–69  partial authority   → REVIEW
70–100 sufficient authority → PASS, unless policy/risk requires review
```

See [`docs/CAUSAL_AUTHORITY.md`](docs/CAUSAL_AUTHORITY.md).

## Public API surface

The main public surface is intentionally small:

```python
from causalgate import AgentCausalFirewall, AgentActionFirewall, CausalGateResult
```

Core product flow:

```text
AgentCausalFirewall.evaluate(...)
→ policy-as-code check
→ ToolGuard / DecisionGate check
→ causal evidence gate when SCM/ID/estimation evidence is present
→ audit event + decision digest
```

See [`docs/PUBLIC_API.md`](docs/PUBLIC_API.md).

## Core pipeline underneath

CausalGate is built around these internal layers:

```text
causalgate/agent_firewall/       public agent action firewall
causalgate/agent_guard/          pre-execution tool guard
causalgate/gate/                 decision gate
causalgate/causal_core/          identification, estimation, counterfactual core
contracts/                       causal contracts, reports, bridge artifacts
pcmci_discovery_parts/           PCMCI-style discovery components
scm_parts/                       SCM, ID, do-calculus, adjustment logic
estimation_parts/                effect estimation and diagnostics
runtime/                         causal authority runtime and veto gateway
```

## Server mode

Run the product HTTP API:

```bash
python -m pip install -e .[server]
causalgate api --host 0.0.0.0 --port 8000
```

The legacy MCP bridge remains available internally, but the main product server is now:

```bash
uvicorn causalgate.api.server:app --host 0.0.0.0 --port 8000
```


## Sale-ready asset package

This package now includes first-pass materials for a complete software-asset sale:

```text
site/index.html                         static landing page
sales/SIDEPROJECTORS_LISTING.md         marketplace listing draft
sales/FLIPPA_LISTING.md                 marketplace listing draft
sales/TRANSFER_GUIDE.md                 handover guide
sales/BUYER_DUE_DILIGENCE.md            buyer verification notes
sales/IP_AND_LICENSE_DISCLOSURE.md      license/IP disclosure template
sales/DEMO_VIDEO_SCRIPT.md              60-second demo recording script
sales/PRICING_SUGGESTION.md             suggested listing price and floor
sales/ASSET_SALE_CHECKLIST.md           pre-listing and closing checklist
templates/ASSET_PURCHASE_AGREEMENT_OUTLINE.md
```

Suggested sales positioning:

> **CausalGate — AI Agent Causal Firewall with Causal Authority Scoring.**

Suggested initial listing price without users or revenue: **€14,900**, negotiable for serious buyers.

See [`docs/STEP6_CHANGELOG.md`](docs/STEP6_CHANGELOG.md) and [`sales/README.md`](sales/README.md).

## Commercial model

This repository is intended to be public and commercially sellable.

Default positioning:

```text
Free: evaluation, research, local testing, non-commercial experimentation.
Paid: commercial use, production use, SaaS hosting, enterprise deployment, resale, or commercial integration.
```

See `LICENSE.md` and `COMMERCIAL-LICENSE.md`. They are draft templates and should be reviewed before selling licenses.

## Testing

```bash
python -m pip install -e .[server,test]
python -m compileall -q .
python -m pytest --collect-only -q
bash run_tests.sh
```

## Product direction

CausalGate should be presented as:

> **A causal firewall for AI agents: block, warn, review, or allow high-impact actions using trusted runtime context, causal discovery, SCM identification, effect estimation, diagnostics, and audit reports.**
