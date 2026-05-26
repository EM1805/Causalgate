# CausalGate product demo

Run:

```bash
causalgate demo --out-dir out/demo --pretty
```

The demo writes one JSON and one Markdown report per case:

1. `PASS` — low-risk read-only action.
2. `HARD_BLOCK` — high-impact action backed only by correlation/weak evidence.
3. `REVIEW` — high-impact action with strong causal evidence, still requiring human review.

This is the product story: CausalGate does not merely ask whether an action is risky; it asks whether the agent has enough causal authority to act.
