from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

import yaml

from causalgate.agent_firewall.policy import HARD_BLOCK, PASS


CONTRACT_VERSION = "causalgate.pr-verification/v1"
POLICY_SCHEMA_VERSION = "causalgate.pr-policy/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_IDENTITY_KINDS = {"human", "service", "bot"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_digest(value: object) -> str:
    """Return a deterministic SHA-256 digest for a JSON-compatible value."""

    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean(item) for item in value if _clean(item)]


def _identity(value: Any) -> Dict[str, str]:
    if not isinstance(value, Mapping):
        return {"id": "", "kind": ""}
    return {"id": _clean(value.get("id")), "kind": _clean(value.get("kind")).lower()}


def _sha256_file(path: Path, *, max_bytes: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise ValueError("evidence artifact exceeds policy size limit")
            digest.update(chunk)
    return digest.hexdigest(), size


def _resolve_evidence_path(root: Path, relative_path: str) -> Path:
    candidate = Path(relative_path)
    if not relative_path or candidate.is_absolute():
        raise ValueError("evidence path must be relative")
    resolved_root = root.resolve(strict=True)
    resolved = (resolved_root / candidate).resolve(strict=True)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("evidence path escapes the trusted root") from exc
    if not resolved.is_file():
        raise ValueError("evidence artifact is not a regular file")
    return resolved


def _append_reason(reasons: list[str], code: str) -> None:
    if code not in reasons:
        reasons.append(code)


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: yaml.Loader, node: yaml.Node, deep: bool = False) -> dict:
    output: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in output:
            raise ValueError("duplicate policy key")
        output[key] = loader.construct_object(value_node, deep=deep)
    return output


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _reject_duplicate_json_keys(pairs: Iterable[tuple[str, Any]]) -> dict:
    output: dict = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("duplicate contract key")
        output[key] = value
    return output


def load_json_contract(path: str | Path) -> Dict[str, Any]:
    payload = json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_json_keys,
    )
    if not isinstance(payload, dict):
        raise ValueError("PR verification contract must be a JSON object")
    return payload


def load_policy(path: str | Path) -> Dict[str, Any]:
    payload = yaml.load(Path(path).read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    if not isinstance(payload, dict):
        raise ValueError("PR verification policy must be a YAML mapping")
    return payload


@dataclass
class PRVerificationResult:
    contract_version: str = CONTRACT_VERSION
    timestamp: str = field(default_factory=_utc_now_iso)
    decision: str = HARD_BLOCK
    allowed: bool = False
    repository: str = ""
    pull_request: int = 0
    base_sha: str = ""
    head_sha: str = ""
    proposer: Dict[str, str] = field(default_factory=dict)
    verifier: Dict[str, str] = field(default_factory=dict)
    policy_version: str = ""
    policy_digest: str = ""
    contract_digest: str = ""
    evidence_manifest_digest: str = ""
    evidence: list[Dict[str, Any]] = field(default_factory=list)
    checks: Dict[str, bool] = field(default_factory=dict)
    reason_codes: list[str] = field(default_factory=list)
    audit_digest: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _blocked_for_invalid_input(code: str) -> PRVerificationResult:
    result = PRVerificationResult(
        reason_codes=[code],
        checks={"input_parseable": False},
        contract_digest=canonical_digest({"invalid": True, "reason_code": code}),
        evidence_manifest_digest=canonical_digest([]),
    )
    result.audit_digest = _audit_digest(result)
    return result


def _audit_digest(result: PRVerificationResult) -> str:
    """Bind the security decision while excluding the wall-clock timestamp."""

    return canonical_digest({
        "contract_version": result.contract_version,
        "decision": result.decision,
        "allowed": result.allowed,
        "repository": result.repository,
        "pull_request": result.pull_request,
        "base_sha": result.base_sha,
        "head_sha": result.head_sha,
        "proposer": result.proposer,
        "verifier": result.verifier,
        "policy_version": result.policy_version,
        "policy_digest": result.policy_digest,
        "contract_digest": result.contract_digest,
        "evidence_manifest_digest": result.evidence_manifest_digest,
        "evidence": result.evidence,
        "checks": result.checks,
        "reason_codes": result.reason_codes,
    })


def verify_pr_contract(
    contract: Mapping[str, Any] | None,
    *,
    policy: Mapping[str, Any] | None,
    evidence_root: str | Path,
    expected_policy_digest: str = "",
) -> PRVerificationResult:
    """Verify a PR contract without executing proposal-controlled code.

    Every validation error becomes ``HARD_BLOCK``.  ``PASS`` is possible only
    when the operator policy is fail-closed, the policy anchor matches, proposer
    and verifier are distinct, and every required artifact is hash- and
    commit-bound under ``evidence_root``.
    """

    if not isinstance(contract, Mapping) or not isinstance(policy, Mapping):
        return _blocked_for_invalid_input("PRV_INVALID_CONTRACT_OR_POLICY")

    contract_data = dict(contract)
    policy_data = dict(policy)
    reasons: list[str] = []
    checks: Dict[str, bool] = {}
    observed_evidence: list[Dict[str, Any]] = []

    repository = _clean(contract_data.get("repository"))
    try:
        pull_request = int(contract_data.get("pull_request", 0))
    except (TypeError, ValueError):
        pull_request = 0
    base_sha = _clean(contract_data.get("base_sha")).lower()
    head_sha = _clean(contract_data.get("head_sha")).lower()
    proposer = _identity(contract_data.get("proposer"))
    verifier = _identity(contract_data.get("verifier"))
    policy_digest = canonical_digest(policy_data)
    contract_digest = canonical_digest(contract_data)
    policy_version = _clean(policy_data.get("version"))

    checks["contract_version"] = contract_data.get("contract_version") == CONTRACT_VERSION
    if not checks["contract_version"]:
        _append_reason(reasons, "PRV_UNSUPPORTED_CONTRACT_VERSION")

    checks["policy_schema_version"] = policy_data.get("schema_version") == POLICY_SCHEMA_VERSION
    if not checks["policy_schema_version"]:
        _append_reason(reasons, "PRV_UNSUPPORTED_POLICY_SCHEMA")

    checks["policy_fail_closed"] = policy_data.get("fail_closed") is True
    if not checks["policy_fail_closed"]:
        _append_reason(reasons, "PRV_POLICY_NOT_FAIL_CLOSED")

    require_anchor = policy_data.get("require_expected_policy_digest") is not False
    normalized_expected = _clean(expected_policy_digest).lower()
    checks["policy_digest_anchored"] = (
        (not require_anchor and not normalized_expected)
        or bool(_SHA256_RE.fullmatch(normalized_expected) and normalized_expected == policy_digest)
    )
    if not checks["policy_digest_anchored"]:
        _append_reason(reasons, "PRV_POLICY_DIGEST_UNTRUSTED")

    allowed_repositories = _strings(policy_data.get("allowed_repositories"))
    checks["repository_allowed"] = bool(repository and repository in allowed_repositories)
    if not checks["repository_allowed"]:
        _append_reason(reasons, "PRV_REPOSITORY_NOT_ALLOWED")

    checks["pull_request_valid"] = pull_request > 0
    if not checks["pull_request_valid"]:
        _append_reason(reasons, "PRV_INVALID_PULL_REQUEST_NUMBER")

    checks["commit_binding_valid"] = bool(
        _GIT_SHA_RE.fullmatch(base_sha)
        and _GIT_SHA_RE.fullmatch(head_sha)
        and base_sha != head_sha
    )
    if not checks["commit_binding_valid"]:
        _append_reason(reasons, "PRV_INVALID_COMMIT_BINDING")

    identities_valid = bool(
        proposer["id"]
        and verifier["id"]
        and proposer["kind"] in _IDENTITY_KINDS
        and verifier["kind"] in _IDENTITY_KINDS
    )
    checks["identities_valid"] = identities_valid
    if not identities_valid:
        _append_reason(reasons, "PRV_INVALID_IDENTITY")

    require_distinct = policy_data.get("require_distinct_roles") is not False
    checks["roles_separated"] = bool(
        identities_valid
        and (not require_distinct or proposer["id"].casefold() != verifier["id"].casefold())
    )
    if not checks["roles_separated"]:
        _append_reason(reasons, "PRV_PROPOSER_VERIFIER_NOT_SEPARATED")

    trusted_verifiers = {item.casefold() for item in _strings(policy_data.get("trusted_verifiers"))}
    checks["verifier_trusted"] = bool(verifier["id"] and verifier["id"].casefold() in trusted_verifiers)
    if not checks["verifier_trusted"]:
        _append_reason(reasons, "PRV_UNTRUSTED_VERIFIER")

    required_types = _strings(policy_data.get("required_evidence_types"))
    checks["required_evidence_policy_valid"] = bool(required_types and len(required_types) == len(set(required_types)))
    if not checks["required_evidence_policy_valid"]:
        _append_reason(reasons, "PRV_INVALID_REQUIRED_EVIDENCE_POLICY")

    trusted_producers = {item.casefold() for item in _strings(policy_data.get("trusted_evidence_producers"))}
    checks["evidence_producer_policy_valid"] = bool(trusted_producers)
    if not checks["evidence_producer_policy_valid"]:
        _append_reason(reasons, "PRV_NO_TRUSTED_EVIDENCE_PRODUCERS")

    try:
        max_evidence_bytes = int(policy_data.get("max_evidence_bytes", 10 * 1024 * 1024))
    except (TypeError, ValueError):
        max_evidence_bytes = 0
    if max_evidence_bytes <= 0:
        _append_reason(reasons, "PRV_INVALID_EVIDENCE_SIZE_LIMIT")

    evidence_rows = contract_data.get("evidence")
    if not isinstance(evidence_rows, list):
        evidence_rows = []
        _append_reason(reasons, "PRV_EVIDENCE_MANIFEST_INVALID")

    seen_types: set[str] = set()
    independent_required = policy_data.get("require_independent_evidence") is not False
    for index, raw in enumerate(evidence_rows):
        if not isinstance(raw, Mapping):
            _append_reason(reasons, "PRV_EVIDENCE_ENTRY_INVALID")
            continue
        row = dict(raw)
        evidence_type = _clean(row.get("type"))
        relative_path = _clean(row.get("path"))
        declared_sha = _clean(row.get("sha256")).lower()
        subject_sha = _clean(row.get("subject_sha")).lower()
        status = _clean(row.get("status")).lower()
        producer = _identity(row.get("producer"))
        metadata = {
            "index": index,
            "type": evidence_type,
            "path": relative_path,
            "declared_sha256": declared_sha,
            "observed_sha256": "",
            "size_bytes": 0,
            "subject_sha": subject_sha,
            "status": status,
            "producer": producer,
            "verified": False,
        }
        row_valid = True
        if not evidence_type or evidence_type in seen_types:
            _append_reason(reasons, "PRV_DUPLICATE_OR_EMPTY_EVIDENCE_TYPE")
            row_valid = False
        seen_types.add(evidence_type)
        if status != "passed":
            _append_reason(reasons, "PRV_EVIDENCE_NOT_PASSED")
            row_valid = False
        if subject_sha != head_sha or not _GIT_SHA_RE.fullmatch(subject_sha):
            _append_reason(reasons, "PRV_EVIDENCE_SUBJECT_MISMATCH")
            row_valid = False
        if not _SHA256_RE.fullmatch(declared_sha):
            _append_reason(reasons, "PRV_EVIDENCE_DIGEST_INVALID")
            row_valid = False
        producer_valid = bool(
            producer["id"]
            and producer["kind"] in _IDENTITY_KINDS
            and producer["id"].casefold() in trusted_producers
        )
        if not producer_valid:
            _append_reason(reasons, "PRV_UNTRUSTED_EVIDENCE_PRODUCER")
            row_valid = False
        if independent_required and producer["id"].casefold() == proposer["id"].casefold():
            _append_reason(reasons, "PRV_EVIDENCE_NOT_INDEPENDENT")
            row_valid = False
        try:
            resolved = _resolve_evidence_path(Path(evidence_root), relative_path)
            observed_sha, size_bytes = _sha256_file(resolved, max_bytes=max_evidence_bytes)
            metadata["observed_sha256"] = observed_sha
            metadata["size_bytes"] = size_bytes
            if observed_sha != declared_sha:
                _append_reason(reasons, "PRV_EVIDENCE_DIGEST_MISMATCH")
                row_valid = False
        except (OSError, ValueError):
            _append_reason(reasons, "PRV_EVIDENCE_FILE_UNAVAILABLE")
            row_valid = False
        metadata["verified"] = row_valid
        observed_evidence.append(metadata)

    missing_types = sorted(set(required_types) - seen_types)
    checks["required_evidence_present"] = not missing_types
    if missing_types:
        _append_reason(reasons, "PRV_REQUIRED_EVIDENCE_MISSING")
    checks["evidence_authentic"] = bool(observed_evidence and all(row["verified"] for row in observed_evidence))
    if not checks["evidence_authentic"]:
        _append_reason(reasons, "PRV_EVIDENCE_AUTHENTICITY_FAILED")

    evidence_manifest_digest = canonical_digest(observed_evidence)
    allowed = not reasons and all(checks.values())
    result = PRVerificationResult(
        decision=PASS if allowed else HARD_BLOCK,
        allowed=allowed,
        repository=repository,
        pull_request=pull_request,
        base_sha=base_sha,
        head_sha=head_sha,
        proposer=proposer,
        verifier=verifier,
        policy_version=policy_version,
        policy_digest=policy_digest,
        contract_digest=contract_digest,
        evidence_manifest_digest=evidence_manifest_digest,
        evidence=observed_evidence,
        checks=checks,
        reason_codes=reasons,
    )
    result.audit_digest = _audit_digest(result)
    return result


__all__ = [
    "CONTRACT_VERSION",
    "POLICY_SCHEMA_VERSION",
    "PRVerificationResult",
    "canonical_digest",
    "load_json_contract",
    "load_policy",
    "verify_pr_contract",
]
