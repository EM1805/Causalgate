from __future__ import annotations

import hashlib
from pathlib import Path

from causalgate.pr_verification import canonical_digest, verify_pr_contract


BASE_SHA = "1" * 40
HEAD_SHA = "2" * 40


def _write_artifact(root: Path, name: str, content: str = "passed\n") -> tuple[str, str]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return name, hashlib.sha256(path.read_bytes()).hexdigest()


def _policy() -> dict:
    return {
        "schema_version": "causalgate.pr-policy/v1",
        "version": "test-policy-v1",
        "fail_closed": True,
        "require_expected_policy_digest": True,
        "allowed_repositories": ["EM1805/Causalgate"],
        "require_distinct_roles": True,
        "trusted_verifiers": ["github-actions/causalgate-pr-verifier"],
        "require_independent_evidence": True,
        "trusted_evidence_producers": ["github-actions/causalgate-ci"],
        "required_evidence_types": ["unit-tests", "policy-audit"],
        "max_evidence_bytes": 4096,
    }


def _contract(root: Path) -> dict:
    test_path, test_digest = _write_artifact(root, "unit-tests.json")
    policy_path, policy_digest = _write_artifact(root, "policy-audit.json")
    return {
        "contract_version": "causalgate.pr-verification/v1",
        "repository": "EM1805/Causalgate",
        "pull_request": 12,
        "base_sha": BASE_SHA,
        "head_sha": HEAD_SHA,
        "proposer": {"id": "github/alice", "kind": "human"},
        "verifier": {"id": "github-actions/causalgate-pr-verifier", "kind": "service"},
        "evidence": [
            {
                "type": "unit-tests",
                "path": test_path,
                "sha256": test_digest,
                "subject_sha": HEAD_SHA,
                "status": "passed",
                "producer": {"id": "github-actions/causalgate-ci", "kind": "service"},
            },
            {
                "type": "policy-audit",
                "path": policy_path,
                "sha256": policy_digest,
                "subject_sha": HEAD_SHA,
                "status": "passed",
                "producer": {"id": "github-actions/causalgate-ci", "kind": "service"},
            },
        ],
    }


def _verify(contract: dict, policy: dict, root: Path):
    return verify_pr_contract(
        contract,
        policy=policy,
        evidence_root=root,
        expected_policy_digest=canonical_digest(policy),
    )


def test_pass_requires_distinct_trusted_roles_and_authentic_evidence(tmp_path: Path) -> None:
    policy = _policy()
    result = _verify(_contract(tmp_path), policy, tmp_path)

    assert not result.reason_codes, result.evidence
    assert result.decision == "PASS", result.to_dict()
    assert result.allowed is True
    assert result.reason_codes == []
    assert result.checks["roles_separated"] is True
    assert result.checks["evidence_authentic"] is True
    assert all(row["verified"] for row in result.evidence)
    assert all("content" not in row for row in result.evidence)


def test_same_proposer_and_verifier_fails_closed(tmp_path: Path) -> None:
    policy = _policy()
    contract = _contract(tmp_path)
    contract["proposer"] = dict(contract["verifier"])

    result = _verify(contract, policy, tmp_path)

    assert result.decision == "HARD_BLOCK"
    assert result.allowed is False
    assert "PRV_PROPOSER_VERIFIER_NOT_SEPARATED" in result.reason_codes


def test_tampered_evidence_fails_closed_without_leaking_content(tmp_path: Path) -> None:
    policy = _policy()
    contract = _contract(tmp_path)
    (tmp_path / "unit-tests.json").write_text("sensitive-value=redacted\n", encoding="utf-8")

    result = _verify(contract, policy, tmp_path)

    assert result.decision == "HARD_BLOCK"
    assert "PRV_EVIDENCE_DIGEST_MISMATCH" in result.reason_codes
    assert "sensitive-value" not in str(result.to_dict())


def test_evidence_must_be_bound_to_head_commit(tmp_path: Path) -> None:
    policy = _policy()
    contract = _contract(tmp_path)
    contract["evidence"][0]["subject_sha"] = BASE_SHA

    result = _verify(contract, policy, tmp_path)

    assert result.decision == "HARD_BLOCK"
    assert "PRV_EVIDENCE_SUBJECT_MISMATCH" in result.reason_codes


def test_missing_required_evidence_fails_closed(tmp_path: Path) -> None:
    policy = _policy()
    contract = _contract(tmp_path)
    contract["evidence"] = contract["evidence"][:1]

    result = _verify(contract, policy, tmp_path)

    assert result.decision == "HARD_BLOCK"
    assert "PRV_REQUIRED_EVIDENCE_MISSING" in result.reason_codes


def test_policy_must_be_fail_closed_and_digest_anchored(tmp_path: Path) -> None:
    policy = _policy()
    policy["fail_closed"] = False
    contract = _contract(tmp_path)

    result = verify_pr_contract(
        contract,
        policy=policy,
        evidence_root=tmp_path,
        expected_policy_digest="0" * 64,
    )

    assert result.decision == "HARD_BLOCK"
    assert "PRV_POLICY_NOT_FAIL_CLOSED" in result.reason_codes
    assert "PRV_POLICY_DIGEST_UNTRUSTED" in result.reason_codes


def test_untrusted_verifier_or_producer_fails_closed(tmp_path: Path) -> None:
    policy = _policy()
    contract = _contract(tmp_path)
    contract["verifier"]["id"] = "github/alice"
    contract["evidence"][0]["producer"]["id"] = "github/alice"

    result = _verify(contract, policy, tmp_path)

    assert result.decision == "HARD_BLOCK"
    assert "PRV_UNTRUSTED_VERIFIER" in result.reason_codes
    assert "PRV_UNTRUSTED_EVIDENCE_PRODUCER" in result.reason_codes
    assert "PRV_EVIDENCE_NOT_INDEPENDENT" in result.reason_codes


def test_evidence_path_cannot_escape_trusted_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("passed\n", encoding="utf-8")
    policy = _policy()
    contract = _contract(root)
    contract["evidence"][0]["path"] = "../outside.json"
    contract["evidence"][0]["sha256"] = hashlib.sha256(b"passed\n").hexdigest()

    result = _verify(contract, policy, root)

    assert result.decision == "HARD_BLOCK"
    assert "PRV_EVIDENCE_FILE_UNAVAILABLE" in result.reason_codes


def test_audit_digest_is_deterministic_and_timestamp_is_not_bound(tmp_path: Path) -> None:
    policy = _policy()
    contract = _contract(tmp_path)

    first = _verify(contract, policy, tmp_path)
    second = _verify(contract, policy, tmp_path)

    assert first.audit_digest == second.audit_digest
    assert first.contract_digest == canonical_digest(contract)
    assert len(first.audit_digest) == 64
