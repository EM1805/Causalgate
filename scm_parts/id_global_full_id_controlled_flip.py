from __future__ import annotations

"""Step 94 controlled Global Full-ID flag flip.

Step 93 proved, without mutating status constants, that the Step-92 promotion
surface was blocked only by the two explicit global flags. Step 94 is the narrow
release layer that verifies that archived pre-flip dry-run and then requires the
live status constants to be flipped together.  It is deliberately not an ID
algorithm; it is the auditable promotion envelope for the global Full-ID claim.
"""

from dataclasses import asdict, dataclass
from typing import Dict, Mapping, Sequence

from .id_algorithm_common import _s
from .id_full_promotion_gate import ID_FULL_PROMOTION_GATE_VERSION, run_id_full_promotion_gate
from .id_global_full_id_promotion_dry_run import (
    GLOBAL_FULL_ID_FLIP_FLAGS,
    ID_GLOBAL_FULL_ID_PROMOTION_DRY_RUN_VERSION,
    run_global_full_id_promotion_dry_run,
)
from .id_status import id_capability_flags

ID_GLOBAL_FULL_ID_CONTROLLED_FLIP_VERSION = "id_global_full_id_controlled_flip_v1_step94"
ID_GLOBAL_FULL_ID_CONTROLLED_FLIP_LEVEL = (
    "controlled_global_full_id_release_requires_step93_preflip_dry_run_green_"
    "atomic_full_recursive_id_and_claim_flags_and_live_promotion_gate_green"
)


@dataclass(frozen=True)
class GlobalFullIDControlledFlipRequirement:
    requirement: str
    passed: bool
    observed: str
    expected: str
    blocker_class: str
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class GlobalFullIDControlledFlip:
    matrix_version: str
    level: str
    global_full_id_controlled_flip_allowed: int
    global_full_id_flags_mutated: int
    full_recursive_id_implemented: int
    full_id_claim_allowed: int
    id_full_promotion_gate_passed: int
    id_full_promotion_gate_version: str
    id_global_full_id_promotion_dry_run_version: str
    preflip_dry_run_allowed: int
    live_promotion_gate_allowed: int
    live_promotion_gate_missing_required_flags: str
    live_promotion_gate_claim_allowed_after_gate: int
    n_requirements: int
    n_requirements_passed: int
    n_blockers: int
    blocker_classes: str
    requirements: Sequence[GlobalFullIDControlledFlipRequirement]

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


def _req(name: str, passed: bool, observed: object, expected: object, blocker_class: str, reason: str) -> GlobalFullIDControlledFlipRequirement:
    return GlobalFullIDControlledFlipRequirement(
        requirement=name,
        passed=bool(passed),
        observed=str(observed),
        expected=str(expected),
        blocker_class=blocker_class,
        reason=reason,
    )


def _preflip_flags(flags: Mapping[str, object] | None = None) -> Dict[str, object]:
    payload = dict(flags or id_capability_flags())
    payload["full_recursive_id_implemented"] = 0
    payload["full_id_claim_allowed"] = 0
    return payload


def run_global_full_id_controlled_flip(
    *,
    capability_flags: Mapping[str, object] | None = None,
    preflip_capability_flags: Mapping[str, object] | None = None,
    readiness: Mapping[str, object] | None = None,
    oracle: Mapping[str, object] | None = None,
    formal_failure_certificate_coverage_complete: object | None = None,
    failure_certificate_coverage: Mapping[str, object] | None = None,
    full_recursive_authority_coverage: Mapping[str, object] | None = None,
    full_recursive_kernel_matrix: Mapping[str, object] | None = None,
    full_recursive_oracle_expansion: Mapping[str, object] | None = None,
) -> Dict[str, object]:
    """Verify that the global Full-ID flags have been flipped safely.

    The function intentionally replays Step 93 against an explicit pre-flip view
    of the same evidence, then checks the live capability flags and promotion
    gate. A partial or unbacked flip is blocked.
    """
    live_flags = dict(capability_flags or id_capability_flags())
    preflip_flags = dict(preflip_capability_flags or _preflip_flags(live_flags))

    preflip_dry_run = run_global_full_id_promotion_dry_run(
        readiness=readiness,
        oracle=oracle,
        capability_flags=preflip_flags,
        formal_failure_certificate_coverage_complete=formal_failure_certificate_coverage_complete,
        failure_certificate_coverage=failure_certificate_coverage,
        full_recursive_authority_coverage=full_recursive_authority_coverage,
        full_recursive_kernel_matrix=full_recursive_kernel_matrix,
        full_recursive_oracle_expansion=full_recursive_oracle_expansion,
    )
    live_gate = run_id_full_promotion_gate(
        readiness=readiness,
        oracle=oracle,
        capability_flags=live_flags,
        formal_failure_certificate_coverage_complete=formal_failure_certificate_coverage_complete,
        failure_certificate_coverage=failure_certificate_coverage,
        full_recursive_authority_coverage=full_recursive_authority_coverage,
        full_recursive_kernel_matrix=full_recursive_kernel_matrix,
        full_recursive_oracle_expansion=full_recursive_oracle_expansion,
    )

    full_recursive = int(_truthy(live_flags.get("full_recursive_id_implemented")))
    claim_allowed = int(_truthy(live_flags.get("full_id_claim_allowed")))
    gate_allowed = int(_truthy(live_gate.get("promotion_allowed")))
    gate_claim_after = int(_truthy(live_gate.get("full_id_claim_allowed_after_promotion_gate")))
    dry_run_allowed = int(_truthy(preflip_dry_run.get("global_promotion_dry_run_allowed")))
    missing = _s(live_gate.get("missing_required_flags"))

    requirements = (
        _req(
            "step93_preflip_dry_run_allowed",
            bool(dry_run_allowed),
            f"{preflip_dry_run.get('matrix_version')}:{dry_run_allowed};missing={preflip_dry_run.get('missing_non_global_prerequisites','')}",
            f"{ID_GLOBAL_FULL_ID_PROMOTION_DRY_RUN_VERSION}:1;missing=",
            "preflip_dry_run_not_green",
            "The controlled flip must be backed by the Step-93 pre-flip rehearsal over the same evidence surface.",
        ),
        _req(
            "global_flags_flipped_atomically",
            bool(full_recursive and claim_allowed),
            f"full_recursive_id_implemented={full_recursive};full_id_claim_allowed={claim_allowed}",
            "1;1",
            "global_flags_not_flipped_together",
            "Global Full-ID release requires both explicit flags; either flag alone is treated as a failed release.",
        ),
        _req(
            "live_promotion_gate_green",
            bool(gate_allowed and not missing),
            f"promotion_allowed={gate_allowed};missing={missing}",
            "promotion_allowed=1;missing=",
            "live_promotion_gate_not_green",
            "After the atomic flag flip the live Full-ID promotion gate must be green with no missing requirements.",
        ),
        _req(
            "claim_allowed_only_after_promotion_gate",
            bool(gate_claim_after),
            f"full_id_claim_allowed_after_promotion_gate={gate_claim_after}",
            "1",
            "claim_flag_not_gate_backed",
            "The claim flag is effective only when the live promotion gate also passes.",
        ),
    )
    blockers = sorted(set(r.blocker_class for r in requirements if not r.passed))
    allowed = int(not blockers)
    gate = GlobalFullIDControlledFlip(
        matrix_version=ID_GLOBAL_FULL_ID_CONTROLLED_FLIP_VERSION,
        level=ID_GLOBAL_FULL_ID_CONTROLLED_FLIP_LEVEL,
        global_full_id_controlled_flip_allowed=allowed,
        global_full_id_flags_mutated=allowed,
        full_recursive_id_implemented=full_recursive,
        full_id_claim_allowed=claim_allowed,
        id_full_promotion_gate_passed=gate_allowed,
        id_full_promotion_gate_version=_s(live_gate.get("matrix_version") or ID_FULL_PROMOTION_GATE_VERSION),
        id_global_full_id_promotion_dry_run_version=_s(preflip_dry_run.get("matrix_version") or ID_GLOBAL_FULL_ID_PROMOTION_DRY_RUN_VERSION),
        preflip_dry_run_allowed=dry_run_allowed,
        live_promotion_gate_allowed=gate_allowed,
        live_promotion_gate_missing_required_flags=missing,
        live_promotion_gate_claim_allowed_after_gate=gate_claim_after,
        n_requirements=len(requirements),
        n_requirements_passed=sum(1 for r in requirements if r.passed),
        n_blockers=len(blockers),
        blocker_classes="|".join(blockers),
        requirements=requirements,
    )
    payload = gate.to_dict()
    payload["controlled_flip_claim_reason"] = (
        "global_full_id_controlled_flip_passed_step94" if allowed else "blocked_" + ("|".join(blockers) or "unknown")
    )
    payload["global_full_id_flip_flags"] = tuple(GLOBAL_FULL_ID_FLIP_FLAGS)
    payload["preflip_dry_run"] = {
        "matrix_version": preflip_dry_run.get("matrix_version"),
        "global_promotion_dry_run_allowed": dry_run_allowed,
        "current_promotion_gate_missing_required_flags": preflip_dry_run.get("current_promotion_gate_missing_required_flags", ""),
        "simulated_promotion_gate_allowed": int(_truthy(preflip_dry_run.get("simulated_promotion_gate_allowed"))),
    }
    payload["live_promotion_gate"] = {
        "matrix_version": live_gate.get("matrix_version"),
        "promotion_allowed": gate_allowed,
        "missing_required_flags": missing,
        "full_id_claim_allowed_after_promotion_gate": gate_claim_after,
    }
    return payload


__all__ = [
    "ID_GLOBAL_FULL_ID_CONTROLLED_FLIP_VERSION",
    "ID_GLOBAL_FULL_ID_CONTROLLED_FLIP_LEVEL",
    "GlobalFullIDControlledFlipRequirement",
    "GlobalFullIDControlledFlip",
    "run_global_full_id_controlled_flip",
]
