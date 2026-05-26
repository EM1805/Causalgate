# Step 4 changelog — product demo

Added a buyer-friendly product demo for the CausalGate agent causal firewall.

## Added

- `causalgate.demo.run_product_demo(...)`
- CLI command: `causalgate demo --out-dir out/demo`
- `examples/demo/README.md`
- `examples/demo/run_demo.py`
- `examples/actions/read_only_dashboard_summary.json`
- `docs/DEMO.md`
- `tests/test_product_demo_step4.py`

## Fixed

- Policy-only/demo mode now preserves a policy `PASS` when ToolGuard is disabled. Before this step, a missing ToolGuard result could incorrectly fail closed even for low-risk read-only demo actions.

## Product outcome

The demo shows three outcomes:

1. `PASS` — low-risk read-only action.
2. `HARD_BLOCK` — high-impact action with weak/correlation-only evidence.
3. `REVIEW` — high-impact action with strong causal evidence that still requires human review.
