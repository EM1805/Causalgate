# Step 3 changelog — Causal Authority Layer

## Added

- `causalgate.evidence.CausalEvidence`
- `causalgate.authority.CausalAuthorityResult`
- `causalgate.authority.score_causal_authority(...)`
- `causalgate.reports.render_markdown_report(...)`
- `causalgate.reports.write_json_report(...)`
- `causalgate.reports.write_markdown_report(...)`
- `AgentCausalFirewall.evaluate(..., evidence=..., require_causal_evidence=...)`
- Result fields:
  - `authority_evaluation`
  - `causal_evidence`
  - `authority_score` property
  - `to_markdown()` helper
- CLI options:
  - `--evidence`
  - `--require-causal-evidence`
  - `--report-json`
  - `--report-md`
- Examples:
  - `examples/actions/marketing_spend_increase.json`
  - `examples/evidence/marketing_strong_evidence.json`
  - `examples/evidence/marketing_weak_evidence.json`
- Documentation:
  - `docs/CAUSAL_AUTHORITY.md`

## Cleaned

- Removed generated caches and transient outputs before packaging.
- Kept research/SCM/estimation/runtime internals because they still provide causal authority depth and test coverage.
- Did not remove scientific/math subpackages yet; they should be isolated in a future `legacy_research/` or optional extra after a full dependency/test map.

## Product behavior

CausalGate now merges the strictest decision from:

```text
policy decision + causal authority decision + ToolGuard decision
```

A high-risk action with weak causal evidence can be hard-blocked even when runtime approval exists.
Strong causal evidence can pass the authority gate, while policy can still require human review for high-impact production actions.
