# Step 4 — 60-second product demo

The product demo turns CausalGate into something a buyer can understand quickly:

```text
AI agent proposes an action
→ CausalGate checks trusted runtime context
→ CausalGate scores causal authority when evidence is supplied
→ output is PASS, REVIEW or HARD_BLOCK
→ audit reports are written as Markdown and JSON
```

Run it:

```bash
causalgate demo --out-dir out/demo --pretty
```

Expected cases:

| Case | Expected decision | Why |
|---|---:|---|
| Low-risk read-only dashboard summary | `PASS` | No mutation, low risk, no causal evidence required. |
| Increase ad spend with weak evidence | `HARD_BLOCK` | High-impact action, causal evidence is correlation-only/unknown. |
| Increase ad spend with strong evidence | `REVIEW` | Strong causal authority, but high-impact production actions still require review. |

The generated `out/demo/summary.md` is suitable for a README screenshot, landing page, or sales demo.
