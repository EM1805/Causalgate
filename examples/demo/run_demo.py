"""Run the CausalGate 60-second product demo from a checkout."""
from __future__ import annotations

from causalgate.demo import run_product_demo

if __name__ == "__main__":
    result = run_product_demo(out_dir="out/demo")
    print(f"Wrote {result.summary_md}")
    for case in result.cases:
        print(f"{case.case_id}: {case.decision} ({case.authority_score})")
