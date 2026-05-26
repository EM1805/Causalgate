# Buyer Due Diligence Notes

## Product summary

CausalGate is a source-available causal firewall for AI agents. It checks whether a proposed agent action has enough policy clearance and causal authority before allowing execution.

## Current product surface

- Python API: `AgentCausalFirewall`
- CLI: `causalgate guard`, `causalgate demo`, `causalgate api`
- API server: FastAPI under `causalgate/api/server.py`
- Reports: JSON and Markdown
- Demo: three product cases covering PASS, REVIEW, and HARD_BLOCK

## Key directories

```text
causalgate/                  product API, authority, evidence, reports, server
causalgate/agent_firewall/   agent action firewall
causalgate/agent_guard/      pre-execution tool guard
causalgate/gate/             decision gate
causalgate/causal_core/      causal identification/estimation/counterfactual core
pcmci_discovery_parts/       PCMCI-style discovery components
scm_parts/                   SCM and ID logic
estimation_parts/            estimation and diagnostics
runtime/                     runtime causal authority and policy layers
contracts/                   causal contracts and reports
docs/                        technical documentation
site/                        landing page
sales/                       sale and transfer materials
```

## Verification commands

```bash
python -m pip install -e .[server,test]
python -m compileall .
causalgate demo --out-dir out/demo
causalgate api --host 127.0.0.1 --port 8000
```

In another shell:

```bash
curl http://127.0.0.1:8000/v1/health
curl -X POST http://127.0.0.1:8000/v1/demo
```

## Known limits

- No hosted SaaS dashboard yet.
- No license-key server yet.
- No payment integration yet.
- No full legal review of licenses has been performed inside this package.
- The software enforces causal evidence requirements; it does not prove causality.

## Recommended buyer roadmap

1. Run license audit.
2. Deploy the API server.
3. Publish landing page.
4. Add authentication and license keys.
5. Add dashboard and project history.
6. Create integrations with agent frameworks.
7. Start beta with 5–10 AI-agent builders.
