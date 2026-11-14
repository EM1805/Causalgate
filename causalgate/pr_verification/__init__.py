"""Fail-closed verification contracts for pull requests.

This boundary is deliberately separate from the action proposer and from the
runtime causal decision path.  It verifies identities, commit binding, policy
anchoring, and evidence artifact integrity; it never executes a proposed
change.
"""

from .contract import (
    CONTRACT_VERSION,
    POLICY_SCHEMA_VERSION,
    PRVerificationResult,
    canonical_digest,
    load_json_contract,
    load_policy,
    verify_pr_contract,
)

__all__ = [
    "CONTRACT_VERSION",
    "POLICY_SCHEMA_VERSION",
    "PRVerificationResult",
    "canonical_digest",
    "load_json_contract",
    "load_policy",
    "verify_pr_contract",
]
