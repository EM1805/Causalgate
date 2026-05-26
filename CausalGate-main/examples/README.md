# Examples

Product-facing examples for the current CausalGate direction:

```bash
causalgate guard --input examples/actions/destructive_prod_change.json
causalgate guard --input examples/actions/destructive_prod_change.json \
  --policy examples/policies/strict_agent_firewall.yaml
```

Useful files:

```text
examples/actions/destructive_prod_change.json     sample agent action package
examples/policies/strict_agent_firewall.yaml      policy-as-code example
examples/scm_templates/                           SCM-first templates for causal authority checks
```

`examples/inputs/` contains legacy compatibility fixtures used by tests and older demos. They are kept for now but are not the main product surface.
