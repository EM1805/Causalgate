# 60-Second Demo Video Script

## Goal

Show CausalGate as an AI-agent causal firewall in under one minute.

## Script

### 0–5 seconds

Narration:

> AI agents can recommend or execute actions, but many actions are justified with weak causal evidence.

Screen:

```bash
causalgate demo --out-dir out/demo --pretty
```

### 5–20 seconds

Narration:

> CausalGate reviews each action before execution and returns PASS, REVIEW, or HARD_BLOCK.

Screen:

```text
01_read_only_pass             -> PASS
02_weak_causal_claim_block    -> HARD_BLOCK
03_strong_evidence_review     -> REVIEW
```

### 20–40 seconds

Narration:

> For high-impact actions, it checks policy, approval, rollback, treatment, outcome, causal evidence, and authority score.

Screen:

```text
Authority score: 83/100
Decision: REVIEW
Reason: partial causal authority, high-impact production action
Required next steps: human approval, diagnostics and sensitivity review
```

### 40–55 seconds

Narration:

> Every decision produces a Markdown and JSON audit report, ready for review queues or enterprise logging.

Screen:

```bash
ls out/demo
cat out/demo/03_strong_evidence_review/report.md
```

### 55–60 seconds

Narration:

> CausalGate: stop agents from acting on weak causal claims.

Screen:

Landing page headline from `site/index.html`.
