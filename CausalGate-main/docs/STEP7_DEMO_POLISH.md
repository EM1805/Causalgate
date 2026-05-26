# Step 7 — Demo polish fixes

This polish pass makes the buyer-facing demo more credible and easier to show.

Changes:

- Adjusted the strong-evidence demo from a perfect `100/100` score to a more realistic `83/100`.
- Added standalone HTML audit reports next to JSON and Markdown reports.
- Added `causalgate demo --pretty` for a buyer-friendly CLI table.
- Corrected the demo video script to point at `out/demo/<case>/report.md`.
- Updated API health/version metadata to `0.6.1.demo-polish`.

The demo still returns:

```text
01_read_only_pass                PASS       authority=n/a
02_weak_causal_claim_block       HARD_BLOCK authority=2/100
03_strong_evidence_review        REVIEW     authority=83/100
```
