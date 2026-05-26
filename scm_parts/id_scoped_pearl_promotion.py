from __future__ import annotations

"""Step 87 scoped Pearl promotion gate.

Step 87 added a narrower release gate for the currently audited public surface.
After Step 94 the global Full-ID flags may be on; this scoped gate remains useful
because it still binds authority cards to the audited surface and no longer acts
as evidence that the global claim must be off.
"""

from dataclasses import asdict, dataclass
from typing import Dict, Mapping, Sequence

from .id_algorithm_common import _s
from .id_full_promotion_gate import run_id_full_promotion_gate
from .id_full_readiness import run_full_id_readiness_matrix
from .id_oracle_parity import run_id_oracle_parity_matrix
from .id_failure_certificate_coverage import run_failure_certificate_coverage_matrix
from .id_full_recursive_authority_coverage import run_full_recursive_authority_coverage_matrix
from .id_status import id_capability_flags

ID_SCOPED_PEARL_PROMOTION_GATE_VERSION = "id_scoped_pearl_promotion_gate_v1_step87"
ID_SCOPED_PEARL_PROMOTION_SCOPE = "audited_public_readiness_oracle_fuzz_surface_step87"
ID_SCOPED_PEARL_PROMOTION_LEVEL = (
    "scope_bound_pearl_veto_release_gate_for_current_public_readiness_oracle_fuzz_"
    "surface_with_step84_failure_coverage_step86_recursive_trace_authority_step94_global_full_id_compatible"
)

SCOPED_PEARL_REQUIRED_GREEN_FLAGS = (
    "id_full_readiness_matrix_passed",
    "id_oracle_parity_fuzz_passed",
    "formal_failure_certificate_coverage_complete",
    "all_public_failure_channels_green",
    "full_recursive_formula_authority_present",
    "no_raw_delegated_formula_authority",
    "no_finite_or_template_only_formula_authority_for_promotion",
    "pearl_formula_authority_coverage_complete",
)

SCOPED_PEARL_GLOBAL_FLAGS_OBSERVED = (
    "global_full_recursive_id_implemented",
    "global_full_id_claim_allowed",
)


@dataclass(frozen=True)
class ScopedPearlPromotionGate:
    matrix_version: str
    scope: str
    level: str
    scoped_promotion_allowed: int
    scoped_pearl_veto_claim_allowed: int
    global_full_recursive_id_implemented: int
    global_full_id_claim_allowed: int
    global_full_id_claim_stays_blocked: int
    id_full_promotion_gate: str
    id_full_promotion_gate_passed: int
    id_full_promotion_gate_missing_required_flags: str
    id_full_readiness_matrix: str
    id_oracle_parity_matrix: str
    failure_certificate_coverage_matrix: str
    full_recursive_formula_authority_coverage_matrix: str
    n_identified_formula_rows_audited: int
    n_full_recursive_formula_authority: int
    n_finite_or_template_formula_authority: int
    n_technical_pending_not_certified: int
    missing_required_flags: str
    requirements: Sequence[Dict[str, object]]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "pass", "passed", "complete", "green"}


def _requirement(name: str, passed: bool, observed: object, expected: object, reason: str) -> Dict[str, object]:
    return {
        "requirement": name,
        "passed": bool(passed),
        "observed": str(observed),
        "expected": str(expected),
        "reason": reason,
    }


def run_scoped_pearl_promotion_gate(
    *,
    readiness: Mapping[str, object] | None = None,
    oracle: Mapping[str, object] | None = None,
    failure_certificate_coverage: Mapping[str, object] | None = None,
    full_recursive_authority_coverage: Mapping[str, object] | None = None,
    capability_flags: Mapping[str, object] | None = None,
) -> Dict[str, object]:
    """Return whether scoped Pearl-veto wording is safe for the audited corpus.

    This is intentionally different from ``run_id_full_promotion_gate``.  The scoped gate is green only when every audited public-surface component is
    green.  After Step 94, global flags are observed for manifest binding but no
    longer block the scoped claim.
    """
    flags = dict(capability_flags or id_capability_flags())
    readiness_payload = dict(readiness or run_full_id_readiness_matrix())
    oracle_payload = dict(oracle or run_id_oracle_parity_matrix())
    coverage_payload = dict(failure_certificate_coverage or run_failure_certificate_coverage_matrix(
        readiness=readiness_payload,
        oracle=oracle_payload,
    ))
    recursive_payload = dict(full_recursive_authority_coverage or run_full_recursive_authority_coverage_matrix(
        readiness=readiness_payload,
        oracle=oracle_payload,
    ))
    global_gate = dict(run_id_full_promotion_gate(
        readiness=readiness_payload,
        oracle=oracle_payload,
        capability_flags=flags,
        failure_certificate_coverage=coverage_payload,
        full_recursive_authority_coverage=recursive_payload,
    ))

    global_full_recursive = int(_truthy(flags.get("full_recursive_id_implemented")))
    global_claim = int(_truthy(flags.get("full_id_claim_allowed")))
    observed = {
        "id_full_readiness_matrix_passed": int(_truthy(global_gate.get("id_full_readiness_matrix_passed"))),
        "id_oracle_parity_fuzz_passed": int(_truthy(global_gate.get("id_oracle_parity_fuzz_passed"))),
        "formal_failure_certificate_coverage_complete": int(_truthy(global_gate.get("formal_failure_certificate_coverage_complete"))),
        "all_public_failure_channels_green": int(_truthy(global_gate.get("all_public_failure_channels_green"))),
        "full_recursive_formula_authority_present": int(_truthy(global_gate.get("full_recursive_formula_authority_present"))),
        "no_raw_delegated_formula_authority": int(_truthy(global_gate.get("no_raw_delegated_formula_authority"))),
        "no_finite_or_template_only_formula_authority_for_promotion": int(_truthy(global_gate.get("no_finite_or_template_only_formula_authority_for_promotion"))),
        "pearl_formula_authority_coverage_complete": int(_truthy(global_gate.get("pearl_formula_authority_coverage_complete"))),
        "global_full_recursive_id_implemented": global_full_recursive,
        "global_full_id_claim_allowed": global_claim,
    }
    requirements = []
    for name in SCOPED_PEARL_REQUIRED_GREEN_FLAGS:
        requirements.append(_requirement(name, observed[name] == 1, observed[name], 1, "required audited public-surface evidence is green"))
    requirements.append(_requirement(
        "global_full_recursive_id_implemented_observed_for_scoped_manifest",
        global_full_recursive in (0, 1),
        global_full_recursive,
        "0_or_1",
        "scoped Pearl manifest records the live global recursive-ID flag",
    ))
    requirements.append(_requirement(
        "global_full_id_claim_allowed_observed_for_scoped_manifest",
        global_claim in (0, 1),
        global_claim,
        "0_or_1",
        "scoped Pearl manifest records the live global Full-ID claim flag",
    ))
    missing = [r["requirement"] for r in requirements if not r["passed"]]
    allowed = int(not missing)
    gate = ScopedPearlPromotionGate(
        matrix_version=ID_SCOPED_PEARL_PROMOTION_GATE_VERSION,
        scope=ID_SCOPED_PEARL_PROMOTION_SCOPE,
        level=ID_SCOPED_PEARL_PROMOTION_LEVEL,
        scoped_promotion_allowed=allowed,
        scoped_pearl_veto_claim_allowed=allowed,
        global_full_recursive_id_implemented=global_full_recursive,
        global_full_id_claim_allowed=global_claim,
        global_full_id_claim_stays_blocked=int(global_full_recursive == 0 and global_claim == 0),
        id_full_promotion_gate=_s(global_gate.get("matrix_version")),
        id_full_promotion_gate_passed=int(_truthy(global_gate.get("promotion_allowed"))),
        id_full_promotion_gate_missing_required_flags=_s(global_gate.get("missing_required_flags")),
        id_full_readiness_matrix=_s(global_gate.get("id_full_readiness_matrix")),
        id_oracle_parity_matrix=_s(global_gate.get("id_oracle_parity_matrix")),
        failure_certificate_coverage_matrix=_s(global_gate.get("failure_certificate_coverage_matrix")),
        full_recursive_formula_authority_coverage_matrix=_s(global_gate.get("full_recursive_formula_authority_coverage_matrix")),
        n_identified_formula_rows_audited=int(global_gate.get("n_identified_formula_rows_audited", 0) or 0),
        n_full_recursive_formula_authority=int(global_gate.get("n_full_recursive_formula_authority", 0) or 0),
        n_finite_or_template_formula_authority=int(global_gate.get("n_finite_or_template_formula_authority", 0) or 0),
        n_technical_pending_not_certified=int(global_gate.get("n_technical_pending_not_certified", 0) or 0),
        missing_required_flags="|".join(str(m) for m in missing),
        requirements=tuple(requirements),
    )
    payload = gate.to_dict()
    payload["scoped_claim_reason"] = (
        "scoped_pearl_promotion_gate_passed_for_audited_public_surface_step87"
        if allowed
        else "scoped_pearl_promotion_blocked_missing_" + "|".join(str(m) for m in missing)
    )
    payload["global_claim_reason"] = "global_full_id_claim_observed_by_scoped_gate_step94"
    return payload


__all__ = [
    "ID_SCOPED_PEARL_PROMOTION_GATE_VERSION",
    "ID_SCOPED_PEARL_PROMOTION_SCOPE",
    "ID_SCOPED_PEARL_PROMOTION_LEVEL",
    "SCOPED_PEARL_REQUIRED_GREEN_FLAGS",
    "SCOPED_PEARL_GLOBAL_FLAGS_OBSERVED",
    "ScopedPearlPromotionGate",
    "run_scoped_pearl_promotion_gate",
]
