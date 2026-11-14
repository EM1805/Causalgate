# Pull-request verification contract

CausalGate can verify a pull request through a boundary that is separate from
the action proposer and from the runtime causal engine. The verifier never
executes the proposed action. It accepts a versioned JSON contract, an
operator-owned policy, and already-produced evidence files.

The contract closes four gaps:

1. the proposer and verifier must have distinct identities;
2. the verifier and evidence producers must be trusted by policy;
3. every evidence file is SHA-256 checked and bound to the PR head commit;
4. every failure, missing field, unknown version, policy mismatch, path escape,
   or unavailable file produces `HARD_BLOCK`.

## Trust boundary

The policy must live outside proposer control in a protected branch, reusable
workflow, or verifier service. Its SHA-256 must be provided through protected
configuration as `--expected-policy-digest`. Running a verifier implementation
and policy taken only from the proposed branch does not establish independent
verification.

Version 1 authenticates artifact bytes, commit binding, and policy-authorized
identity claims. It does not provide a cryptographic signature or prove the
real-world identity of a named producer. Signed OIDC/Sigstore attestations can
be added later without weakening this fail-closed contract.

## Contract shape

```json
{
  "contract_version": "causalgate.pr-verification/v1",
  "repository": "EM1805/Causalgate",
  "pull_request": 12,
  "base_sha": "1111111111111111111111111111111111111111",
  "head_sha": "2222222222222222222222222222222222222222",
  "proposer": {"id": "github/alice", "kind": "human"},
  "verifier": {
    "id": "github-actions/causalgate-pr-verifier",
    "kind": "service"
  },
  "evidence": [
    {
      "type": "unit-tests",
      "path": "evidence/unit-tests.json",
      "sha256": "<64 lowercase hex characters>",
      "subject_sha": "2222222222222222222222222222222222222222",
      "status": "passed",
      "producer": {"id": "github-actions/causalgate-ci", "kind": "service"}
    }
  ]
}
```

The operator policy, not the proposal, decides which evidence types are
required. Duplicate evidence types are rejected to avoid ambiguity.

## Command line

```bash
python -m causalgate.pr_verification \
  --contract pr-contract.json \
  --policy /protected/causalgate-pr-policy.yaml \
  --expected-policy-digest "$CAUSALGATE_PR_POLICY_SHA256" \
  --evidence-root /trusted/evidence \
  --audit-out out/pr-verification.json
```

Exit code `0` means `PASS`; exit code `2` means `HARD_BLOCK`. The audit report
contains only metadata and digests, never artifact contents. Its
`audit_digest` is deterministic and excludes the wall-clock timestamp.

## Future integrations

- **Causal Safety Engine:** may add a safety evidence artifact and policy rule;
  it must not become the proposer or bypass CausalGate's decision.
- **Kernel:** may attest formal properties of the contract or policy; CausalGate
  remains the operational verifier and continues to fail closed if the
  attestation is absent or invalid.

Neither integration is required by this change, and neither repository is
modified here.
