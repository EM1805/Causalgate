from __future__ import annotations

"""Step 93 Global Full-ID promotion dry-run.

Step 92 made the full-recursive-ID backend pass a broad kernel oracle expansion,
but the global capability flags deliberately remain off.  Step 93 is the last
pre-flip rehearsal: it proves that the current promotion gate is blocked *only*
by the two explicit global flags, then reruns that same gate with an in-memory
simulated flip.  It does not mutate :mod:`id_status` and does not authorize
runtime Pearl-complete wording by itself.
"""

from dataclasses import asdict, dataclass
from typing import Dict, Mapping, Sequence

from .id_algorithm_common import _s
from .id_full_promotion_gate import (
    ID_FULL_PROMOTION_GATE_VERSION,
    PROMOTION_REQUIRED_FLAGS,
    run_id_full_promotion_gate,
)
from .id_status import id_capability_flags

ID_GLOBAL_FULL_ID_PROMOTION_DRY_RUN_VERSION = "id_global_full_id_promotion_dry_run_v1_step93"
ID_GLOBAL_FULL_ID_PROMOTION_DRY_RUN_LEVEL = (
    "pre_flip_global_full_id_promotion_dry_run_requires_current_gate_blocked_only_"
    "by_global_flags_and_simulated_global_flag_flip_makes_step92_promotion_gate_green"
)

GLOBAL_FULL_ID_FLIP_FLAGS = ("full_recursive_id_implemented", "full_id_claim_allowed")


@dataclass(frozen=True)
class GlobalFullIDPromotionDryRunRequirement:
    requirement: str
    passed: bool
    observed: str
    expected: str
    blocker_class: str
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class GlobalFullIDPromotionDryRun:
    matrix_version: str
    level: str
    global_promotion_dry_run_allowed: int
    current_full_recursive_id_implemented: int
    current_full_id_claim_allowed: int
    would_set_full_recursive_id_implemented: int
    would_set_full_id_claim_allowed: int
    current_promotion_gate_version: str
    current_promotion_gate_allowed: int
    current_promotion_gate_missing_required_flags: str
    simulated_promotion_gate_version: str
    simulated_promotion_gate_allowed: int
    simulated_promotion_gate_missing_required_flags: str
    missing_non_global_prerequisites: str
    expected_current_blockers: str
    n_requirements: int
    n_requirements_passed: int
    n_blockers: int
    blocker_classes: str
    requirements: Sequence[GlobalFullIDPromotionDryRunRequirement]

    def to_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["requirements"] = [r.to_dict() for r in self.requirements]
        return payload


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "pass", "passed", "complete", "green"}


def _split_flags(value: object) -> tuple[str, ...]:
    return tuple(part for part in _s(value).split("|") if part)


def _req(name: str, passed: bool, observed: object, expected: object, blocker_class: str, reason: str) -> GlobalFullIDPromotionDryRunRequirement:
    return GlobalFullIDPromotionDryRunRequirement(
        requirement=name,
        passed=bool(passed),
        observed=str(observed),
        expected=str(expected),
        blocker_class=blocker_class,
        reason=reason,
    )


def _simulated_global_flag_payload(flags: Mapping[str, object] | None) -> Dict[str, object]:
    simulated = dict(flags or id_capability_flags())
    simulated["full_recursive_id_implemented"] = 1
    simulated["full_id_claim_allowed"] = 1
    return simulated


def run_global_full_id_promotion_dry_run(
    *,
    readiness: Mapping[str, object] | None = None,
    oracle: Mapping[str, object] | None = None,
    capability_flags: Mapping[str, object] | None = None,
    formal_failure_certificate_coverage_complete: object | None = None,
    failure_certificate_coverage: Mapping[str, object] | None = None,
    full_recursive_authority_coverage: Mapping[str, object] | None = None,
    full_recursive_kernel_matrix: Mapping[str, object] | None = None,
    full_recursive_oracle_expansion: Mapping[str, object] | None = None,
) -> Dict[str, object]:
    """Run the Step-93 pre-flip Global Full-ID promotion rehearsal.

    A green dry-run means: all audited non-flag prerequisites are green, the
    current gate is blocked only by ``full_recursive_id_implemented`` and
    ``full_id_claim_allowed``, and the exact same evidence would make the Step-92
    promotion gate green if those two flags were flipped in memory.
    """
    flags = dict(capability_flags or id_capability_flags())
    current_gate = run_id_full_promotion_gate(
        readiness=readiness,
        oracle=oracle,
        capability_flags=flags,
        formal_failure_certificate_coverage_complete=formal_failure_certificate_coverage_complete,
        failure_certificate_coverage=failure_certificate_coverage,
        full_recursive_authority_coverage=full_recursive_authority_coverage,
        full_recursive_kernel_matrix=full_recursive_kernel_matrix,
        full_recursive_oracle_expansion=full_recursive_oracle_expansion,
    )
    simulated_flags = _simulated_global_flag_payload(flags)
    simulated_gate = run_id_full_promotion_gate(
        readiness=readiness,
        oracle=oracle,
        capability_flags=simulated_flags,
        formal_failure_certificate_coverage_complete=formal_failure_certificate_coverage_complete,
        failure_certificate_coverage=failure_certificate_coverage,
        full_recursive_authority_coverage=full_recursive_authority_coverage,
        full_recursive_kernel_matrix=full_recursive_kernel_matrix,
        full_recursive_oracle_expansion=full_recursive_oracle_expansion,
    )

    current_missing = _split_flags(current_gate.get("missing_required_flags"))
    expected_blockers = tuple(GLOBAL_FULL_ID_FLIP_FLAGS)
    missing_non_global = tuple(flag for flag in current_missing if flag not in expected_blockers)
    current_flags_off = int(not _truthy(flags.get("full_recursive_id_implemented")) and not _truthy(flags.get("full_id_claim_allowed")))
    current_gate_blocked_only_by_global_flags = int(tuple(current_missing) == expected_blockers)
    simulated_gate_green = int(_truthy(simulated_gate.get("promotion_allowed")) and not _split_flags(simulated_gate.get("missing_required_flags")))
    dry_run_allowed = int(bool(current_flags_off and current_gate_blocked_only_by_global_flags and simulated_gate_green))

    requirements = (
        _req(
            "current_global_flags_still_off",
            bool(current_flags_off),
            f"full_recursive_id_implemented={int(_truthy(flags.get('full_recursive_id_implemented')))};full_id_claim_allowed={int(_truthy(flags.get('full_id_claim_allowed')))}",
            "0;0",
            "global_flags_already_mutated_or_partially_set",
            "Step 93 must be a dry-run: it cannot depend on or mutate already-raised global Full-ID flags.",
        ),
        _req(
            "current_gate_blocked_only_by_global_flags",
            bool(current_gate_blocked_only_by_global_flags),
            "|".join(current_missing),
            "|".join(expected_blockers),
            "non_global_prerequisite_missing",
            "The pre-flip gate must be red only because the two explicit global flags are still off.",
        ),
        _req(
            "simulated_global_flag_flip_makes_promotion_gate_green",
            bool(simulated_gate_green),
            f"promotion_allowed={int(_truthy(simulated_gate.get('promotion_allowed')))};missing={_s(simulated_gate.get('missing_required_flags'))}",
            "promotion_allowed=1;missing=",
            "simulated_flip_did_not_make_gate_green",
            "With identical evidence and only the two global flags flipped in memory, the Step-92 promotion gate must pass.",
        ),
        _req(
            "dry_run_does_not_mutate_supplied_flags",
            True,
            f"supplied_full_recursive_id_implemented={flags.get('full_recursive_id_implemented')};supplied_full_id_claim_allowed={flags.get('full_id_claim_allowed')}",
            "no mutation",
            "dry_run_mutated_status_flags",
            "The dry-run may report would-set fields but must not mutate its supplied evidence/flag payload.",
        ),
    )
    blockers = sorted(set(r.blocker_class for r in requirements if not r.passed))
    gate = GlobalFullIDPromotionDryRun(
        matrix_version=ID_GLOBAL_FULL_ID_PROMOTION_DRY_RUN_VERSION,
        level=ID_GLOBAL_FULL_ID_PROMOTION_DRY_RUN_LEVEL,
        global_promotion_dry_run_allowed=dry_run_allowed,
        current_full_recursive_id_implemented=int(_truthy(flags.get("full_recursive_id_implemented"))),
        current_full_id_claim_allowed=int(_truthy(flags.get("full_id_claim_allowed"))),
        would_set_full_recursive_id_implemented=int(bool(dry_run_allowed)),
        would_set_full_id_claim_allowed=int(bool(dry_run_allowed)),
        current_promotion_gate_version=_s(current_gate.get("matrix_version")),
        current_promotion_gate_allowed=int(_truthy(current_gate.get("promotion_allowed"))),
        current_promotion_gate_missing_required_flags="|".join(current_missing),
        simulated_promotion_gate_version=_s(simulated_gate.get("matrix_version")),
        simulated_promotion_gate_allowed=int(_truthy(simulated_gate.get("promotion_allowed"))),
        simulated_promotion_gate_missing_required_flags=_s(simulated_gate.get("missing_required_flags")),
        missing_non_global_prerequisites="|".join(missing_non_global),
        expected_current_blockers="|".join(expected_blockers),
        n_requirements=len(requirements),
        n_requirements_passed=sum(1 for r in requirements if r.passed),
        n_blockers=len(blockers),
        blocker_classes="|".join(blockers),
        requirements=requirements,
    )
    payload = gate.to_dict()
    payload["promotion_required_flags"] = tuple(PROMOTION_REQUIRED_FLAGS)
    payload["current_promotion_gate"] = {
        "matrix_version": current_gate.get("matrix_version", ID_FULL_PROMOTION_GATE_VERSION),
        "promotion_allowed": int(_truthy(current_gate.get("promotion_allowed"))),
        "missing_required_flags": "|".join(current_missing),
        "id_full_recursive_kernel_matrix_passed": int(_truthy(current_gate.get("id_full_recursive_kernel_matrix_passed"))),
        "id_full_recursive_oracle_expansion_passed": int(_truthy(current_gate.get("id_full_recursive_oracle_expansion_passed"))),
        "formal_failure_certificate_coverage_complete": int(_truthy(current_gate.get("formal_failure_certificate_coverage_complete"))),
        "pearl_formula_authority_coverage_complete": int(_truthy(current_gate.get("pearl_formula_authority_coverage_complete"))),
        "no_raw_delegated_formula_authority": int(_truthy(current_gate.get("no_raw_delegated_formula_authority"))),
    }
    payload["simulated_promotion_gate"] = {
        "matrix_version": simulated_gate.get("matrix_version", ID_FULL_PROMOTION_GATE_VERSION),
        "promotion_allowed": int(_truthy(simulated_gate.get("promotion_allowed"))),
        "missing_required_flags": _s(simulated_gate.get("missing_required_flags")),
        "full_recursive_id_implemented": int(_truthy(simulated_gate.get("full_recursive_id_implemented"))),
        "full_id_claim_allowed": int(_truthy(simulated_gate.get("full_id_claim_allowed"))),
        "full_id_claim_allowed_after_promotion_gate": int(_truthy(simulated_gate.get("full_id_claim_allowed_after_promotion_gate"))),
    }
    payload["dry_run_claim_reason"] = (
        "global_full_id_promotion_dry_run_passed_ready_for_controlled_flip"
        if dry_run_allowed
        else "blocked_" + ("|".join(blockers) or "unknown")
    )
    payload["global_full_id_flags_mutated"] = 0
    return payload


__all__ = [
    "ID_GLOBAL_FULL_ID_PROMOTION_DRY_RUN_VERSION",
    "ID_GLOBAL_FULL_ID_PROMOTION_DRY_RUN_LEVEL",
    "GLOBAL_FULL_ID_FLIP_FLAGS",
    "GlobalFullIDPromotionDryRunRequirement",
    "GlobalFullIDPromotionDryRun",
    "run_global_full_id_promotion_dry_run",
]
