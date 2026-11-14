from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from .contract import load_json_contract, load_policy, verify_pr_contract


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a hash- and commit-bound pull-request evidence contract."
    )
    parser.add_argument("--contract", required=True, help="PR verification contract JSON")
    parser.add_argument("--policy", required=True, help="Operator-owned verification policy YAML")
    parser.add_argument("--evidence-root", required=True, help="Trusted root containing evidence artifacts")
    parser.add_argument(
        "--expected-policy-digest",
        default="",
        help="Trusted SHA-256 of the policy, normally supplied by protected configuration",
    )
    parser.add_argument("--audit-out", default="", help="Optional JSON audit report path")
    args = parser.parse_args(argv)

    try:
        contract = load_json_contract(args.contract)
        policy = load_policy(args.policy)
        result = verify_pr_contract(
            contract,
            policy=policy,
            evidence_root=args.evidence_root,
            expected_policy_digest=args.expected_policy_digest,
        )
        payload = result.to_dict()
    except Exception:
        # Parsing and local I/O failures are permission to do nothing.  Keep the
        # CLI response generic so exception details cannot disclose local paths
        # or evidence contents in CI logs.
        payload = {
            "contract_version": "causalgate.pr-verification/v1",
            "decision": "HARD_BLOCK",
            "allowed": False,
            "reason_codes": ["PRV_INPUT_LOAD_FAILED"],
        }

    if args.audit_out:
        _atomic_write_json(Path(args.audit_out), payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("allowed") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
