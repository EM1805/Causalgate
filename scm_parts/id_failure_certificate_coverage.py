from __future__ import annotations

"""Step 84 failure-certificate coverage readiness for SCM Full-ID.

This module is a measurement/guardrail layer.  It does **not** claim arbitrary
Full-ID, and it does not turn technical-pending branches into mathematical
non-identifiability proofs.  Instead it makes the failure side of the Pearl
promotion gate auditable:

* every public non-identified readiness/oracle/fuzz row must carry an explicit
  certificate/rejection channel;
* formal ID-5 hedge failures are counted separately from invalid/cyclic
  rejections;
* any ``not_certified_pending_failure`` rows remain explicit promotion blockers.

The current backend is expected to have a green public failure-channel invariant
and green formal failure-certificate coverage for the audited matrices because
Step 84 certifies the two previously pending deterministic fuzz rows with
formal subforest hedge certificates.  Full-ID/Pearl promotion still requires
the separate full-recursive-ID gates.
"""

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Mapping, Sequence

from .id_algorithm_common import _s
from .id_full_readiness import run_full_id_readiness_matrix
from .id_oracle_parity import run_id_oracle_parity_matrix
from .id_status import id_capability_flags

ID_FAILURE_CERTIFICATE_COVERAGE_VERSION = "id_failure_certificate_coverage_v2_step84"
ID_FAILURE_CERTIFICATE_COVERAGE_LEVEL = (
    "public_nonidentified_outputs_have_explicit_failure_certificate_channels_"
    "and_step84_subforest_hedge_search_closes_current_not_certified_pending_id5_failures"
)


@dataclass(frozen=True)
class IDFailureCertificateCoverageRow:
    source_matrix: str
    case_id: str
    source_kind: str
    covered_public_failure_channel: int
    covered_formal_promotion: int
    identified: int
    identification_status: str
    failure_certificate_status: str
    failure_certified: int
    primary_formula_authority: str
    blocker_class: str = ""
    reason: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "pass", "passed", "complete", "green"}


def _is_rejection_status(status: str) -> bool:
    return status.startswith("rejected_")


def _is_formal_hedge_status(status: str) -> bool:
    return status == "formal_hedge_certified_step68"


def _is_pending_status(status: str) -> bool:
    return status == "not_certified_pending_failure_step68" or "not_certified" in status or "pending" in status


def _row_failure_certified(row: Mapping[str, object], status: str) -> int:
    # Some older fuzz rows do not expose failure_certified yet; derive the safe
    # value from the status when necessary.
    if "failure_certified" in row:
        return int(_truthy(row.get("failure_certified")))
    return int(_is_formal_hedge_status(status))


def _coverage_row(
    *,
    source_matrix: str,
    case_id: str,
    source_kind: str,
    row: Mapping[str, object],
) -> IDFailureCertificateCoverageRow | None:
    identified = int(_truthy(row.get("identified")))
    if identified:
        return None

    status = _s(row.get("failure_certificate_status"))
    identification_status = _s(row.get("identification_status"))
    primary = _s(row.get("primary_formula_authority"))
    blocker_class = _s(row.get("blocker_class"))
    certified = _row_failure_certified(row, status)

    has_channel = bool(status)
    is_rejection = _is_rejection_status(status)
    is_formal = _is_formal_hedge_status(status) and certified == 1
    is_pending = _is_pending_status(status)

    public_ok = int(has_channel)
    # Formal promotion coverage is intentionally stricter: invalid/cyclic
    # rejections are allowed because they are outside ID identifiability; ID-5
    # failures must be formal hedge certified, not merely pending.
    formal_ok = int(is_formal or is_rejection)

    reasons: List[str] = []
    if not has_channel:
        reasons.append("missing_failure_certificate_status")
    if is_pending:
        reasons.append("technical_pending_not_formal_hedge_certified")
    if has_channel and not (is_formal or is_rejection or is_pending):
        reasons.append("unclassified_failure_certificate_status")
    if primary and primary != "id_failure_certificate_step68" and source_kind != "idc_parent_row":
        # IDC parent rows can inherit the joint authority in joint_full_id_json;
        # keep this as a reason field only, not as public coverage failure.
        reasons.append(f"nonidentified_primary_authority={primary}")

    return IDFailureCertificateCoverageRow(
        source_matrix=source_matrix,
        case_id=case_id,
        source_kind=source_kind,
        covered_public_failure_channel=public_ok,
        covered_formal_promotion=formal_ok,
        identified=0,
        identification_status=identification_status,
        failure_certificate_status=status,
        failure_certified=certified,
        primary_formula_authority=primary,
        blocker_class=blocker_class,
        reason=";".join(reasons),
    )


def _collect_rows_from_readiness(readiness: Mapping[str, object]) -> List[IDFailureCertificateCoverageRow]:
    out: List[IDFailureCertificateCoverageRow] = []
    source = _s(readiness.get("matrix_version")) or "id_full_readiness_matrix"
    for row in readiness.get("rows", []) or []:
        if not isinstance(row, Mapping):
            continue
        cov = _coverage_row(
            source_matrix=source,
            case_id=_s(row.get("case_id")),
            source_kind="readiness",
            row=row,
        )
        if cov is not None:
            out.append(cov)
    return out


def _collect_rows_from_oracle(oracle: Mapping[str, object]) -> List[IDFailureCertificateCoverageRow]:
    out: List[IDFailureCertificateCoverageRow] = []
    source = _s(oracle.get("matrix_version")) or "id_oracle_parity_matrix"
    for row in oracle.get("rows", []) or []:
        if not isinstance(row, Mapping):
            continue
        cov = _coverage_row(
            source_matrix=source,
            case_id=_s(row.get("case_id")),
            source_kind="oracle",
            row=row,
        )
        if cov is not None:
            out.append(cov)

    fuzz = oracle.get("fuzz", {}) if isinstance(oracle.get("fuzz"), Mapping) else {}
    fuzz_source = _s(fuzz.get("matrix_version")) or source + ":fuzz"
    for row in fuzz.get("rows", []) or []:
        if not isinstance(row, Mapping):
            continue
        cov = _coverage_row(
            source_matrix=fuzz_source,
            case_id=_s(row.get("fuzz_id")) or _s(row.get("case_id")),
            source_kind="fuzz",
            row=row,
        )
        if cov is not None:
            out.append(cov)
    return out


def run_failure_certificate_coverage_matrix(
    *,
    readiness: Mapping[str, object] | None = None,
    oracle: Mapping[str, object] | None = None,
) -> Dict[str, object]:
    """Measure public and formal failure-certificate coverage.

    ``all_public_failure_channels_green`` answers the runtime invariant: no
    non-identified public output is silent.  ``formal_failure_certificate_coverage_complete``
    answers the stricter Pearl-promotion invariant: no ID-5 branch remains
    technical pending.  The latter is expected to be 1 for the current audited backend; Full-ID/Pearl promotion remains blocked by the separate full-recursive-ID gates.
    """
    readiness_payload = dict(readiness or run_full_id_readiness_matrix())
    oracle_payload = dict(oracle or run_id_oracle_parity_matrix())
    rows = _collect_rows_from_readiness(readiness_payload) + _collect_rows_from_oracle(oracle_payload)

    n_rows = len(rows)
    n_public = sum(r.covered_public_failure_channel for r in rows)
    n_formal = sum(r.covered_formal_promotion for r in rows)
    n_formal_hedge = sum(1 for r in rows if r.failure_certificate_status == "formal_hedge_certified_step68")
    n_rejection = sum(1 for r in rows if _is_rejection_status(r.failure_certificate_status))
    pending = [r for r in rows if _is_pending_status(r.failure_certificate_status) or not r.covered_formal_promotion]
    missing_channel = [r for r in rows if not r.covered_public_failure_channel]

    # Vacuous truth for fixture/future matrices with no non-identified rows: no
    # silent failure channel exists and no pending ID-5 certificate is present.
    public_green = int(n_public == n_rows)
    formal_complete = int(n_formal == n_rows and not pending)

    return {
        "matrix_version": ID_FAILURE_CERTIFICATE_COVERAGE_VERSION,
        "level": ID_FAILURE_CERTIFICATE_COVERAGE_LEVEL,
        "n_nonidentified_rows_audited": n_rows,
        "n_public_failure_channels_covered": n_public,
        "all_public_failure_channels_green": public_green,
        "n_formal_promotion_covered": n_formal,
        "formal_failure_certificate_coverage_complete": formal_complete,
        "n_formal_hedge_certified": n_formal_hedge,
        "n_explicit_rejections": n_rejection,
        "n_technical_pending_not_certified": len(pending),
        "n_missing_failure_certificate_status": len(missing_channel),
        "technical_pending_case_ids": "|".join(r.case_id for r in pending),
        "missing_failure_channel_case_ids": "|".join(r.case_id for r in missing_channel),
        "full_id_claim_allowed": int(id_capability_flags().get("full_recursive_id_implemented") == 1 and id_capability_flags().get("full_id_claim_allowed") == 1),
        "promotion_blocker_reason": (
            "no_failure_certificate_coverage_blocker_step84" if formal_complete else "blocked_not_certified_pending=" + "|".join(r.case_id for r in pending)
        ),
        "rows": [r.to_dict() for r in rows],
    }


__all__ = [
    "ID_FAILURE_CERTIFICATE_COVERAGE_VERSION",
    "ID_FAILURE_CERTIFICATE_COVERAGE_LEVEL",
    "IDFailureCertificateCoverageRow",
    "run_failure_certificate_coverage_matrix",
]
