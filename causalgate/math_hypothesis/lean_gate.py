from __future__ import annotations

"""Conservative Lean/proof-checker gate for mathematical claims.

The gate does not run Lean internally.  It verifies whether a caller supplied a
trusted external checker attestation and downgrades everything else to proof
obligation or proof-sketch status.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Mapping

from .claim_schema import MathClaimPackage, normalize_math_claim


TRUSTED_CHECKER_STATUSES = {"accepted", "verified", "success", "proved"}
TRUSTED_FORMAL_SYSTEMS = {"lean", "lean4", "coq", "isabelle", "agda"}


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _stable_digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class LeanGateResult:
    gate_version: str = "math_lean_gate_v1_step99"
    proof_status: str = "not_run"
    formal_system: str = ""
    checker_status: str = ""
    trusted_external_attestation: bool = False
    formal_statement_present: bool = False
    proof_code_present: bool = False
    proof_digest: str = ""
    reason_codes: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def evaluate_lean_gate(payload: Mapping[str, Any] | MathClaimPackage) -> Dict[str, Any]:
    claim = normalize_math_claim(payload)
    checker = _as_dict(claim.proof_checker_result)
    formal_system = _clean_str(claim.formal_system or checker.get("formal_system")).lower()
    checker_status = _clean_str(checker.get("status") or checker.get("result")).lower()
    trusted_attestation = bool(checker.get("trusted") or checker.get("trusted_external_attestation"))
    statement_present = bool(_clean_str(claim.formal_statement))
    code_present = bool(_clean_str(claim.lean_code) or _clean_str(checker.get("proof_artifact_digest")))
    reason_codes: list[str] = []

    if not statement_present:
        reason_codes.append("MISSING_FORMAL_STATEMENT")
    if not code_present:
        reason_codes.append("MISSING_FORMAL_PROOF_ARTIFACT")
    if formal_system and formal_system not in TRUSTED_FORMAL_SYSTEMS:
        reason_codes.append("UNRECOGNIZED_FORMAL_SYSTEM")
    if checker_status and checker_status not in TRUSTED_CHECKER_STATUSES:
        reason_codes.append("CHECKER_STATUS_NOT_ACCEPTED")
    if checker_status in TRUSTED_CHECKER_STATUSES and not trusted_attestation:
        reason_codes.append("CHECKER_ATTESTATION_NOT_TRUSTED")

    accepted = (
        statement_present
        and code_present
        and formal_system in TRUSTED_FORMAL_SYSTEMS
        and checker_status in TRUSTED_CHECKER_STATUSES
        and trusted_attestation
    )
    if accepted:
        proof_status = "accepted_by_trusted_external_checker"
        summary = "Formal proof claim may be treated as verified within the supplied trusted checker attestation."
    elif statement_present and code_present:
        proof_status = "formal_artifact_unverified"
        summary = "Formal artifacts are present but the checker attestation is missing or not accepted."
    elif statement_present:
        proof_status = "proof_obligation_candidate"
        summary = "A formal statement exists, but a verified proof artifact is still required."
    else:
        proof_status = "needs_formalization"
        summary = "The mathematical claim must be converted into a formal statement before proof authority can be discussed."

    digest_payload = {
        "gate_version": "math_lean_gate_v1_step99",
        "claim": claim.claim,
        "formal_system": formal_system,
        "formal_statement": claim.formal_statement,
        "lean_code": claim.lean_code,
        "checker_status": checker_status,
        "trusted_external_attestation": int(trusted_attestation),
        "proof_status": proof_status,
    }
    return LeanGateResult(
        proof_status=proof_status,
        formal_system=formal_system,
        checker_status=checker_status,
        trusted_external_attestation=trusted_attestation,
        formal_statement_present=statement_present,
        proof_code_present=code_present,
        proof_digest=_stable_digest(digest_payload),
        reason_codes=reason_codes,
        summary=summary,
    ).to_dict()


__all__ = ["evaluate_lean_gate", "LeanGateResult"]
