# Product cleanup notes

This cleanup moves CausalGate toward the chosen product direction:

> Causal firewall for AI agents.

## Public product surface kept

- `causalgate.AgentCausalFirewall`
- `causalgate guard` CLI command
- agent firewall, tool guard, decision gate
- causal core, SCM/ID, estimation, diagnostics
- MCP/HTTP server as optional integration

## Removed from the public repo surface

- step-by-step package check notes
- Hugging Face sync workflow
- Hugging Face Space metadata README
- pytest/cache artifacts
- historical internal documentation under `estimation_parts/docs/`

## Kept for compatibility

Some internal modules still contain research/scientific names because tests and MCP compatibility depend on them. They are no longer the primary public positioning.
