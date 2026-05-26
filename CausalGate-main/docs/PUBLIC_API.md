# CausalGate public API

The public API is designed for product use, not research notebooks.

## Main class

```python
from causalgate import AgentCausalFirewall

firewall = AgentCausalFirewall()
result = firewall.evaluate(
    action="increase_ad_spend",
    tool_name="marketing_budget_api.update_budget",
    environment="production",
    risk_level="high",
    action_type="mutation",
    approval_present=False,
    rollback_available=True,
)
```

`result` is a `CausalGateResult` / `AgentFirewallResult` dataclass with:

```text
firewall_decision: PASS | REVIEW | HARD_BLOCK
execution_action:  execute | execute_with_warning | ask_user | block
blocked:           boolean
needs_approval:    boolean
reason_codes:      list[str]
summary:           human-readable summary
decision_digest:   stable audit digest
audit_event:       JSON-serializable audit record
```

## Trusted vs untrusted context

Runtime-sensitive facts must come from trusted code, not from LLM text.

Use `trusted_runtime_context` for facts such as:

```text
environment
risk_level
action_type
approval_present
rollback_available
recipient_external
target_resource
```

Use `untrusted_llm_context` only for the agent's explanation, hypothesis, or rationale.

## CLI

```bash
causalgate guard --action deploy_config_change --environment production --risk-level high
```

For policy-only demos:

```bash
causalgate guard --action delete_resource --environment production --disable-tool-guard
```


## Causal authority API

Step 3 adds a first-class evidence package:

```python
from causalgate import AgentCausalFirewall, CausalEvidence, score_causal_authority

evidence = CausalEvidence.from_file("examples/evidence/marketing_strong_evidence.json")
authority = score_causal_authority(evidence, risk_level="high")

firewall = AgentCausalFirewall()
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
```

The result now includes:

```text
authority_evaluation.authority_score
authority_evaluation.authority_decision
authority_evaluation.reasons
authority_evaluation.required_next_steps
causal_evidence
```

Reports:

```python
result.to_markdown()
```

or via CLI:

```bash
causalgate guard --input action.json --evidence evidence.json --report-md report.md
```
