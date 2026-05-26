from __future__ import annotations

"""Step 94 Full-ID/Pearl promotion gate.

This module is deliberately a *promotion gate*, not a new identification
algorithm.  Earlier readiness matrices prove that supported branches behave
coherently; this gate answers the stronger question needed before CausalGate may
raise Full-ID / Pearl-complete wording anywhere else in the stack.

A green readiness matrix is necessary but not sufficient.  Promotion additionally
requires a real full-recursive-ID implementation flag, a global claim flag, broad
oracle/fuzz parity, complete failure-certificate coverage, and complete
full-recursive formula-authority coverage.  Step 86 allows scoped recursive
trace certificates to satisfy the public formula-authority coverage requirement
without raising the global implementation or claim flags. Step 92 adds a broader
recursive-kernel oracle expansion as a required green matrix before promotion.
Step 94 flips the two explicit global flags only after the Step 93 dry-run is green.
"""

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from .id_algorithm_common import _s
from .id_full_readiness import run_full_id_readiness_matrix
from .id_oracle_parity import run_id_oracle_parity_matrix
from .id_failure_certificate_coverage import run_failure_certificate_coverage_matrix
from .id_status import id_capability_flags
from .id_full_recursive_authority_coverage import (
    ID_FULL_RECURSIVE_AUTHORITY_COVERAGE_VERSION,
    FULL_RECURSIVE_FORMULA_AUTHORITIES,
    run_full_recursive_authority_coverage_matrix,
)
from .id_step80_audited_fuzz import ID_STEP80_AUDITED_FUZZ_AUTHORITY
from .id_full_recursive_kernel import run_full_recursive_id_kernel_matrix
from .id_full_recursive_oracle_expansion import (
    ID_FULL_RECURSIVE_ORACLE_EXPANSION_VERSION,
    run_full_recursive_oracle_expansion_matrix,
)

ID_FULL_PROMOTION_GATE_VERSION = "id_full_promotion_gate_v7_step94"
ID_FULL_PROMOTION_GATE_LEVEL = (
    "full_id_and_pearl_promotion_gate_requires_full_recursive_id_flags_readiness_"
    "oracle_fuzz_step84_failure_certificate_coverage_step86_recursive_trace_formula_authority_step92_kernel_oracle_expansion_step94_controlled_flip_no_overclaim"
)


FINITE_OR_TEMPLATE_AUTHORITIES = {
    "id_canonical_formula_step60",
    "recursive_id_set_expression_diagnostic_step75",
    "recursive_id_set_expression_diagnostic_step79",
    ID_STEP80_AUDITED_FUZZ_AUTHORITY,
}

PROMOTION_REQUIRED_FLAGS = (
    "full_recursive_id_implemented",
    "full_id_claim_allowed",
    "id_full_readiness_matrix_passed",
    "id_oracle_parity_fuzz_passed",
    "id_full_recursive_oracle_expansion_passed",
    "formal_failure_certificate_coverage_complete",
    "all_public_failure_channels_green",
    "full_recursive_formula_authority_present",
    "no_raw_delegated_formula_authority",
    "no_finite_or_template_only_formula_authority_for_promotion",
    "pearl_formula_authority_coverage_complete",
)


@dataclass(frozen=True)
class IDFullPromotionRequirement:
    requirement: str
    passed: bool
    observed: str
    expected: str
    blocker_class: str
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class IDFullPromotionGate:
    matrix_version: str
    level: str
    promotion_allowed: int
    full_recursive_id_implemented: int
    full_id_claim_allowed: int
    id_full_readiness_matrix: str
    id_full_readiness_matrix_passed: int
    id_oracle_parity_matrix: str
    id_oracle_parity_fuzz_passed: int
    formal_failure_certificate_coverage_complete: int
    failure_certificate_coverage_matrix: str
    all_public_failure_channels_green: int
    n_technical_pending_not_certified: int
    full_recursive_formula_authority_present: int
    no_raw_delegated_formula_authority: int
    no_finite_or_template_only_formula_authority_for_promotion: int
    full_recursive_formula_authority_coverage_matrix: str
    all_identified_formula_rows_public_clean: int
    pearl_formula_authority_coverage_complete: int
    n_identified_formula_rows_audited: int
    n_full_recursive_formula_authority: int
    n_finite_or_template_formula_authority: int
    id_full_recursive_oracle_expansion_matrix: str
    id_full_recursive_oracle_expansion_passed: int
    n_full_recursive_oracle_expansion_cases: int
    n_full_recursive_oracle_expansion_passed: int
    n_blockers: int
    blocker_classes: str
    missing_required_flags: str
    requirements: Sequence[IDFullPromotionRequirement]

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


def _iter_formula_authorities(readiness: Mapping[str, object], oracle: Mapping[str, object]) -> Iterable[str]:
    for row in readiness.get("rows", []) or []:
        if not isinstance(row, Mapping):
            continue
        identified = _truthy(row.get("identified"))
        if identified:
            for key in ("primary_formula_authority", "joint_primary_formula_authority"):
                val = _s(row.get(key))
                if val:
                    yield val
    for row in oracle.get("rows", []) or []:
        if not isinstance(row, Mapping):
            continue
        if _truthy(row.get("identified")):
            val = _s(row.get("primary_formula_authority"))
            if val:
                yield val
    fuzz = oracle.get("fuzz", {}) if isinstance(oracle.get("fuzz"), Mapping) else {}
    for row in fuzz.get("rows", []) or []:
        if not isinstance(row, Mapping):
            continue
        if _truthy(row.get("identified")):
            val = _s(row.get("primary_formula_authority"))
            if val:
                yield val


def _raw_delegated_count(readiness: Mapping[str, object], oracle: Mapping[str, object]) -> int:
    count = int(readiness.get("n_delegated_formula_authority", 0) or 0)
    count += int(oracle.get("n_oracle_delegated_formula_gaps", 0) or 0)
    fuzz = oracle.get("fuzz", {}) if isinstance(oracle.get("fuzz"), Mapping) else {}
    count += int(fuzz.get("n_delegated_identified_formula_authority", 0) or 0)
    return count


def _requirement(name: str, passed: bool, observed: object, expected: object, blocker_class: str, reason: str) -> IDFullPromotionRequirement:
    return IDFullPromotionRequirement(
        requirement=name,
        passed=bool(passed),
        observed=str(observed),
        expected=str(expected),
        blocker_class=blocker_class,
        reason=reason,
    )


def run_id_full_promotion_gate(
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
    """Evaluate whether the current SCM-ID backend may promote to Full-ID/Pearl.

    Before Step 94 the expected answer was intentionally ``promotion_allowed=0``.
    After the controlled flip, the live gate is expected to pass only if all
    matrix, oracle, failure-certificate, recursive-authority and explicit global
    claim flags are green.
    """
    flags = dict(capability_flags or id_capability_flags())
    readiness_payload = dict(readiness or run_full_id_readiness_matrix())
    oracle_payload = dict(oracle or run_id_oracle_parity_matrix())

    readiness_passed = int(_truthy(readiness_payload.get("all_passed")))
    oracle_passed = int(_truthy(oracle_payload.get("all_passed")))
    full_recursive = int(_truthy(flags.get("full_recursive_id_implemented")))
    claim_allowed = int(_truthy(flags.get("full_id_claim_allowed")))
    raw_delegated = _raw_delegated_count(readiness_payload, oracle_payload)
    no_raw_delegated = int(raw_delegated == 0)

    authorities = list(_iter_formula_authorities(readiness_payload, oracle_payload))
    recursive_authorities = sorted(set(a for a in authorities if a in FULL_RECURSIVE_FORMULA_AUTHORITIES))
    finite_authorities = sorted(set(a for a in authorities if a in FINITE_OR_TEMPLATE_AUTHORITIES or a.startswith("recursive_id_set_expression_diagnostic_step")))
    recursive_authority_payload = dict(full_recursive_authority_coverage or run_full_recursive_authority_coverage_matrix(
        readiness=readiness_payload,
        oracle=oracle_payload,
    ))
    recursive_authority_public_clean = int(_truthy(recursive_authority_payload.get("all_identified_formula_rows_public_clean")))
    pearl_formula_authority_coverage_complete = int(_truthy(recursive_authority_payload.get("pearl_formula_authority_coverage_complete")))
    n_identified_formula_rows_audited = int(recursive_authority_payload.get("n_identified_formula_rows_audited", 0) or 0)
    n_full_recursive_formula_authority = int(recursive_authority_payload.get("n_full_recursive_formula_authority", 0) or 0)
    n_finite_or_template_formula_authority = int(recursive_authority_payload.get("n_finite_or_template_formula_authority", 0) or 0)
    n_primary_finite_or_template_formula_authority = int(recursive_authority_payload.get("n_primary_finite_or_template_formula_authority", 0) or 0)
    recursive_authorities_from_coverage = [a for a in _s(recursive_authority_payload.get("full_recursive_formula_authorities_observed")).split("|") if a]
    recursive_authorities = sorted(set(recursive_authorities) | set(recursive_authorities_from_coverage))
    full_recursive_authority_present = int(bool(recursive_authorities) or n_full_recursive_formula_authority > 0)
    no_finite_or_template_only = int(bool(pearl_formula_authority_coverage_complete) and n_finite_or_template_formula_authority == 0)
    finite_authorities = [a for a in _s(recursive_authority_payload.get("finite_or_template_authorities_observed")).split("|") if a]
    primary_finite_authorities = [a for a in _s(recursive_authority_payload.get("primary_finite_or_template_authorities_observed")).split("|") if a]

    coverage_payload = dict(failure_certificate_coverage or run_failure_certificate_coverage_matrix(
        readiness=readiness_payload,
        oracle=oracle_payload,
    ))
    kernel_payload = dict(full_recursive_kernel_matrix or run_full_recursive_id_kernel_matrix())
    kernel_passed = int(_truthy(kernel_payload.get("all_passed")))
    kernel_oracle_payload = dict(full_recursive_oracle_expansion or run_full_recursive_oracle_expansion_matrix())
    kernel_oracle_passed = int(_truthy(kernel_oracle_payload.get("all_passed")))
    if formal_failure_certificate_coverage_complete is None:
        formal_failure_certificate_coverage_complete = coverage_payload.get(
            "formal_failure_certificate_coverage_complete",
            flags.get("formal_failure_certificate_coverage_complete", 0),
        )
    failure_coverage = int(_truthy(formal_failure_certificate_coverage_complete))
    public_failure_channels_green = int(_truthy(coverage_payload.get("all_public_failure_channels_green")))
    technical_pending_not_certified = int(coverage_payload.get("n_technical_pending_not_certified", 0) or 0)

    requirements = [
        _requirement(
            "full_recursive_id_implemented",
            bool(full_recursive),
            full_recursive,
            1,
            "implementation_flag_missing",
            "Global capability flag must be raised only after arbitrary recursive ID is implemented.",
        ),
        _requirement(
            "id_full_recursive_kernel_matrix_passed",
            bool(kernel_passed),
            f"{kernel_payload.get('matrix_version','')}:{kernel_payload.get('n_passed',0)}/{kernel_payload.get('n_cases',0)}",
            "all_passed=1",
            "full_recursive_kernel_matrix_failed",
            "Step 91 recursive-ID kernel matrix must be green before the global implementation flag can be promoted.",
        ),
        _requirement(
            "id_full_recursive_oracle_expansion_passed",
            bool(kernel_oracle_passed),
            f"{kernel_oracle_payload.get('matrix_version','')}:{kernel_oracle_payload.get('n_passed',0)}/{kernel_oracle_payload.get('n_cases',0)}",
            "all_passed=1",
            "full_recursive_oracle_expansion_failed",
            "Step 92 broad recursive-ID kernel oracle expansion must be green before global Full-ID/Pearl promotion.",
        ),
        _requirement(
            "full_id_claim_allowed",
            bool(claim_allowed),
            claim_allowed,
            1,
            "claim_flag_missing",
            "Global Full-ID claim flag must be raised by the SCM-ID backend, not inferred by runtime veto code.",
        ),
        _requirement(
            "id_full_readiness_matrix_passed",
            bool(readiness_passed),
            f"{readiness_payload.get('matrix_version','')}:{readiness_payload.get('n_passed',0)}/{readiness_payload.get('n_cases',0)}",
            "all_passed=1",
            "readiness_matrix_failed",
            "Public Full-ID/IDC readiness matrix must be green.",
        ),
        _requirement(
            "id_oracle_parity_fuzz_passed",
            bool(oracle_passed),
            f"{oracle_payload.get('matrix_version','')}:{oracle_payload.get('all_passed',0)}",
            "all_passed=1",
            "oracle_or_fuzz_failed",
            "Curated oracle parity and deterministic ADMG fuzz guard must be green.",
        ),
        _requirement(
            "formal_failure_certificate_coverage_complete",
            bool(failure_coverage),
            failure_coverage,
            1,
            "failure_certificate_coverage_incomplete",
            "Every ID-5 FAIL branch must have formal failure-certificate coverage before Full-ID/Pearl promotion. Step 84 closes the currently audited subforest hedge pending rows; future pending rows still block promotion.",
        ),
        _requirement(
            "all_public_failure_channels_green",
            bool(public_failure_channels_green),
            public_failure_channels_green,
            1,
            "public_failure_certificate_channel_missing",
            "Every current public non-identified readiness/oracle/fuzz output must have a non-silent failure certificate channel.",
        ),
        _requirement(
            "full_recursive_formula_authority_present",
            bool(full_recursive_authority_present),
            "|".join(recursive_authorities),
            "one_of=" + "|".join(sorted(FULL_RECURSIVE_FORMULA_AUTHORITIES)),
            "formula_authority_not_full_recursive",
            "Promotion requires at least one emitted/contracted formula authority backed by full recursive ID, not only finite closures.",
        ),
        _requirement(
            "no_raw_delegated_formula_authority",
            bool(no_raw_delegated),
            raw_delegated,
            0,
            "raw_delegated_formula_authority_remaining",
            "Raw recursive_id_set_expression_diagnostic gaps must be eliminated or converted to owned/certified branches.",
        ),
        _requirement(
            "no_finite_or_template_only_formula_authority_for_promotion",
            bool(no_finite_or_template_only),
            "|".join(finite_authorities),
            "no finite/template-only authority in promotion evidence",
            "finite_or_template_authority_not_pearl_complete",
            "Finite/templates are not enough unless every public identified formula row has a Step-86 recursive trace certificate or another full-recursive formula authority.",
        ),
        _requirement(
            "pearl_formula_authority_coverage_complete",
            bool(pearl_formula_authority_coverage_complete),
            f"{recursive_authority_payload.get('matrix_version','')}:{n_full_recursive_formula_authority}/{n_identified_formula_rows_audited}",
            "all identified formula rows backed by full recursive formula authority",
            "recursive_formula_authority_coverage_incomplete",
            "Step 86 audits formula authority separately: public rows must be clean/no-raw-delegate and backed by full-recursive trace/formula authority before promotion.",
        ),
    ]
    missing = [r.requirement for r in requirements if not r.passed]
    blocker_classes = sorted(set(r.blocker_class for r in requirements if not r.passed))
    promotion_allowed = int(not missing)
    gate = IDFullPromotionGate(
        matrix_version=ID_FULL_PROMOTION_GATE_VERSION,
        level=ID_FULL_PROMOTION_GATE_LEVEL,
        promotion_allowed=promotion_allowed,
        full_recursive_id_implemented=full_recursive,
        full_id_claim_allowed=claim_allowed,
        id_full_readiness_matrix=_s(readiness_payload.get("matrix_version")),
        id_full_readiness_matrix_passed=readiness_passed,
        id_oracle_parity_matrix=_s(oracle_payload.get("matrix_version")),
        id_oracle_parity_fuzz_passed=oracle_passed,
        formal_failure_certificate_coverage_complete=failure_coverage,
        failure_certificate_coverage_matrix=_s(coverage_payload.get("matrix_version")),
        all_public_failure_channels_green=public_failure_channels_green,
        n_technical_pending_not_certified=technical_pending_not_certified,
        full_recursive_formula_authority_present=full_recursive_authority_present,
        no_raw_delegated_formula_authority=no_raw_delegated,
        no_finite_or_template_only_formula_authority_for_promotion=no_finite_or_template_only,
        full_recursive_formula_authority_coverage_matrix=_s(recursive_authority_payload.get("matrix_version")),
        all_identified_formula_rows_public_clean=recursive_authority_public_clean,
        pearl_formula_authority_coverage_complete=pearl_formula_authority_coverage_complete,
        n_identified_formula_rows_audited=n_identified_formula_rows_audited,
        n_full_recursive_formula_authority=n_full_recursive_formula_authority,
        n_finite_or_template_formula_authority=n_finite_or_template_formula_authority,
        id_full_recursive_oracle_expansion_matrix=_s(kernel_oracle_payload.get("matrix_version")),
        id_full_recursive_oracle_expansion_passed=kernel_oracle_passed,
        n_full_recursive_oracle_expansion_cases=int(kernel_oracle_payload.get("n_cases", 0) or 0),
        n_full_recursive_oracle_expansion_passed=int(kernel_oracle_payload.get("n_passed", 0) or 0),
        n_blockers=len(missing),
        blocker_classes="|".join(blocker_classes),
        missing_required_flags="|".join(missing),
        requirements=tuple(requirements),
    )
    payload = gate.to_dict()
    payload["full_recursive_formula_authorities_observed"] = recursive_authorities
    payload["finite_or_template_authorities_observed"] = finite_authorities
    payload["primary_finite_or_template_authorities_observed"] = primary_finite_authorities
    payload["n_raw_delegated_formula_authority"] = raw_delegated
    payload["full_recursive_authority_coverage"] = {
        "matrix_version": recursive_authority_payload.get("matrix_version", ID_FULL_RECURSIVE_AUTHORITY_COVERAGE_VERSION),
        "all_identified_formula_rows_public_clean": recursive_authority_public_clean,
        "pearl_formula_authority_coverage_complete": pearl_formula_authority_coverage_complete,
        "n_identified_formula_rows_audited": n_identified_formula_rows_audited,
        "n_full_recursive_formula_authority": n_full_recursive_formula_authority,
        "n_finite_or_template_formula_authority": n_finite_or_template_formula_authority,
        "n_primary_finite_or_template_formula_authority": n_primary_finite_or_template_formula_authority,
        "promotion_blocker_reason": recursive_authority_payload.get("promotion_blocker_reason", ""),
        "raw_delegated_row_ids": recursive_authority_payload.get("raw_delegated_row_ids", ""),
    }
    payload["failure_certificate_coverage"] = {
        "matrix_version": coverage_payload.get("matrix_version", ""),
        "all_public_failure_channels_green": public_failure_channels_green,
        "formal_failure_certificate_coverage_complete": failure_coverage,
        "n_technical_pending_not_certified": technical_pending_not_certified,
        "technical_pending_case_ids": coverage_payload.get("technical_pending_case_ids", ""),
        "promotion_blocker_reason": coverage_payload.get("promotion_blocker_reason", ""),
    }
    payload["full_recursive_kernel_matrix"] = {
        "matrix_version": kernel_payload.get("matrix_version", ""),
        "all_passed": kernel_passed,
        "n_cases": int(kernel_payload.get("n_cases", 0) or 0),
        "n_passed": int(kernel_payload.get("n_passed", 0) or 0),
        "n_identified": int(kernel_payload.get("n_identified", 0) or 0),
        "n_nonidentified_certified": int(kernel_payload.get("n_nonidentified_certified", 0) or 0),
        "promotion_note": kernel_payload.get("promotion_note", ""),
    }
    payload["full_recursive_oracle_expansion"] = {
        "matrix_version": kernel_oracle_payload.get("matrix_version", ID_FULL_RECURSIVE_ORACLE_EXPANSION_VERSION),
        "all_passed": kernel_oracle_passed,
        "n_cases": int(kernel_oracle_payload.get("n_cases", 0) or 0),
        "n_passed": int(kernel_oracle_payload.get("n_passed", 0) or 0),
        "n_curated_cases": int(kernel_oracle_payload.get("n_curated_cases", 0) or 0),
        "n_fuzz_cases": int(kernel_oracle_payload.get("n_fuzz_cases", 0) or 0),
        "n_identified": int(kernel_oracle_payload.get("n_identified", 0) or 0),
        "n_nonidentified_certified": int(kernel_oracle_payload.get("n_nonidentified_certified", 0) or 0),
        "n_pending_kernel_blockers": int(kernel_oracle_payload.get("n_pending_kernel_blockers", 0) or 0),
        "promotion_note": kernel_oracle_payload.get("promotion_note", ""),
    }
    payload["id_full_recursive_kernel_matrix_passed"] = kernel_passed
    payload["id_full_recursive_oracle_expansion_passed"] = kernel_oracle_passed
    payload["promotion_claim_reason"] = (
        "full_recursive_id_promotion_gate_passed" if promotion_allowed else "blocked_missing_" + "|".join(missing)
    )
    payload["full_id_claim_allowed_after_promotion_gate"] = int(promotion_allowed and claim_allowed)
    return payload


__all__ = [
    "ID_FULL_PROMOTION_GATE_VERSION",
    "ID_FULL_PROMOTION_GATE_LEVEL",
    "FULL_RECURSIVE_FORMULA_AUTHORITIES",
    "FINITE_OR_TEMPLATE_AUTHORITIES",
    "PROMOTION_REQUIRED_FLAGS",
    "IDFullPromotionRequirement",
    "IDFullPromotionGate",
    "run_id_full_promotion_gate",
]
