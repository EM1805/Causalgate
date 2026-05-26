from __future__ import annotations

"""Step 97 final Global Pearl readiness report.

Step 97 is not another promotion shortcut.  It is a single machine-readable
release report that binds the Global Full-ID backend, Global Pearl-complete
runtime veto, attestation verifier, and adversarial no-overclaim suite into one
final evidence digest.  If any upstream gate drifts red, this report becomes red
and its digest changes.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Dict, Mapping, Sequence

from .id_algorithm_common import _s
from .id_full_promotion_gate import ID_FULL_PROMOTION_GATE_VERSION, run_id_full_promotion_gate
from .id_global_full_id_controlled_flip import ID_GLOBAL_FULL_ID_CONTROLLED_FLIP_VERSION, run_global_full_id_controlled_flip
from .id_global_pearl_no_overclaim import ID_GLOBAL_PEARL_NO_OVERCLAIM_MATRIX_VERSION, run_global_pearl_no_overclaim_suite
from .id_global_pearl_veto_release import run_global_pearl_veto_release_matrix

ID_FINAL_PEARL_READINESS_REPORT_VERSION = "id_final_pearl_readiness_report_v1_step97"
ID_FINAL_PEARL_READINESS_REPORT_LEVEL = (
    "final_global_pearl_readiness_report_requires_green_global_full_id_promotion_gate_"
    "step94_controlled_flip_step95_runtime_release_step96_no_overclaim_and_digest_bound_evidence"
)
ID_FINAL_PEARL_READINESS_SCOPE = "global_full_id_and_pearl_complete_veto_release_step97"


@dataclass(frozen=True)
class FinalPearlReadinessRequirement:
    requirement: str
    passed: bool
    observed: str
    expected: str
    blocker_class: str
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FinalPearlReadinessReport:
    matrix_version: str
    level: str
    scope: str
    final_pearl_readiness_allowed: int
    global_full_id_backend_ready: int
    pearl_complete_veto_runtime_ready: int
    adversarial_no_overclaim_passed: int
    id_full_promotion_gate: str
    id_full_promotion_gate_passed: int
    id_global_full_id_controlled_flip: str
    id_global_full_id_controlled_flip_passed: int
    id_global_pearl_veto_attestation: str
    id_global_pearl_veto_release_allowed: int
    id_global_pearl_no_overclaim_matrix: str
    id_global_pearl_no_overclaim_passed: int
    full_recursive_id_implemented: int
    full_id_claim_allowed: int
    id_full_readiness_matrix: str
    id_oracle_parity_matrix: str
    id_full_recursive_kernel_matrix: str
    id_full_recursive_oracle_expansion_matrix: str
    failure_certificate_coverage_matrix: str
    recursive_formula_authority_coverage_matrix: str
    n_kernel_cases: int
    n_kernel_passed: int
    n_oracle_expansion_cases: int
    n_oracle_expansion_passed: int
    n_identified_formula_rows_audited: int
    n_full_recursive_formula_authority: int
    n_no_overclaim_cases: int
    n_adversarial_cases_blocked: int
    n_requirements: int
    n_requirements_passed: int
    n_blockers: int
    blocker_classes: str
    missing_required_flags: str
    report_digest: str
    requirements: Sequence[FinalPearlReadinessRequirement]

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


def _req(name: str, passed: bool, observed: object, expected: object, blocker_class: str, reason: str) -> FinalPearlReadinessRequirement:
    return FinalPearlReadinessRequirement(
        requirement=name,
        passed=bool(passed),
        observed=str(observed),
        expected=str(expected),
        blocker_class=blocker_class,
        reason=reason,
    )


def final_pearl_readiness_report_digest(payload: Mapping[str, object]) -> str:
    """Return a stable digest for a final readiness report payload.

    The digest intentionally excludes itself, so callers may verify the report by
    recomputing over the same structure with ``report_digest`` removed or empty.
    """
    normalized = dict(payload)
    normalized.pop("report_digest", None)
    raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def run_final_pearl_readiness_report(
    *,
    promotion_gate: Mapping[str, object] | None = None,
    controlled_flip: Mapping[str, object] | None = None,
    pearl_veto_release: Mapping[str, object] | None = None,
    no_overclaim: Mapping[str, object] | None = None,
    include_subreports: bool = True,
) -> Dict[str, object]:
    """Build the Step-97 final Global Pearl readiness report.

    The report is green only when the Global Full-ID backend, Step-94 controlled
    flip, Step-95/96 Pearl-complete runtime veto attestation, and Step-96
    adversarial no-overclaim suite are all green at the same time.
    """
    gate = dict(promotion_gate or run_id_full_promotion_gate())
    flip = dict(controlled_flip or run_global_full_id_controlled_flip())
    release = dict(pearl_veto_release or run_global_pearl_veto_release_matrix())
    no_over = dict(no_overclaim or run_global_pearl_no_overclaim_suite())

    kernel = dict(gate.get("full_recursive_kernel_matrix") or {})
    oracle_expansion = dict(gate.get("full_recursive_oracle_expansion") or {})
    failure_coverage = dict(gate.get("failure_certificate_coverage") or {})
    recursive_authority = dict(gate.get("full_recursive_authority_coverage") or {})

    requirements = (
        _req(
            "global_full_id_promotion_gate_green",
            bool(_truthy(gate.get("promotion_allowed")) and not _s(gate.get("missing_required_flags"))),
            f"{gate.get('matrix_version')}:{int(_truthy(gate.get('promotion_allowed')))};missing={_s(gate.get('missing_required_flags'))}",
            f"{ID_FULL_PROMOTION_GATE_VERSION}:1;missing=",
            "full_id_promotion_gate_not_green",
            "The final Pearl report requires the live Global Full-ID promotion gate to pass with no missing prerequisites.",
        ),
        _req(
            "global_full_id_flags_green",
            bool(_truthy(gate.get("full_recursive_id_implemented")) and _truthy(gate.get("full_id_claim_allowed"))),
            f"full_recursive_id_implemented={int(_truthy(gate.get('full_recursive_id_implemented')))};full_id_claim_allowed={int(_truthy(gate.get('full_id_claim_allowed')))}",
            "1;1",
            "global_full_id_flags_not_green",
            "Both explicit Global Full-ID flags must be on after the controlled Step-94 flip.",
        ),
        _req(
            "recursive_kernel_matrix_green",
            bool(_truthy(gate.get("id_full_recursive_kernel_matrix_passed"))),
            f"{kernel.get('matrix_version','')}:{kernel.get('n_passed',0)}/{kernel.get('n_cases',0)}",
            "all_passed=1",
            "recursive_kernel_matrix_not_green",
            "Step 91 recursive-ID kernel matrix must remain green in the final report.",
        ),
        _req(
            "recursive_oracle_expansion_green",
            bool(_truthy(gate.get("id_full_recursive_oracle_expansion_passed"))),
            f"{oracle_expansion.get('matrix_version','')}:{oracle_expansion.get('n_passed',0)}/{oracle_expansion.get('n_cases',0)}",
            "all_passed=1",
            "recursive_oracle_expansion_not_green",
            "Step 92 oracle/fuzz expansion must remain green in the final report.",
        ),
        _req(
            "failure_certificate_coverage_complete",
            bool(_truthy(gate.get("formal_failure_certificate_coverage_complete")) and _truthy(gate.get("all_public_failure_channels_green"))),
            f"formal={int(_truthy(gate.get('formal_failure_certificate_coverage_complete')))};public={int(_truthy(gate.get('all_public_failure_channels_green')))};pending={failure_coverage.get('n_technical_pending_not_certified',0)}",
            "formal=1;public=1;pending=0",
            "failure_certificate_coverage_not_complete",
            "All non-identification branches must have formal/public failure certificate coverage.",
        ),
        _req(
            "recursive_formula_authority_complete",
            bool(_truthy(gate.get("pearl_formula_authority_coverage_complete")) and _truthy(gate.get("full_recursive_formula_authority_present"))),
            f"{recursive_authority.get('matrix_version','')}:{gate.get('n_full_recursive_formula_authority',0)}/{gate.get('n_identified_formula_rows_audited',0)}",
            "all identified rows full-recursive-authorized",
            "recursive_formula_authority_not_complete",
            "Every public identified formula row must be backed by full recursive formula authority, not template-only evidence.",
        ),
        _req(
            "step94_controlled_flip_green",
            bool(_truthy(flip.get("global_full_id_controlled_flip_allowed"))),
            f"{flip.get('matrix_version')}:{int(_truthy(flip.get('global_full_id_controlled_flip_allowed')))}",
            f"{ID_GLOBAL_FULL_ID_CONTROLLED_FLIP_VERSION}:1",
            "controlled_flip_not_green",
            "The final report requires the audited Step-94 controlled Global Full-ID flip to be green.",
        ),
        _req(
            "global_pearl_veto_runtime_release_green",
            bool(_truthy(release.get("global_pearl_veto_release_allowed")) and _truthy(release.get("attestation_verified"))),
            f"{release.get('matrix_version')}:{int(_truthy(release.get('global_pearl_veto_release_allowed')))};attestation={int(_truthy(release.get('attestation_verified')))}",
            "release=1;attestation=1",
            "global_pearl_veto_release_not_green",
            "The runtime Pearl-complete veto release must emit a verified digest-bound attestation.",
        ),
        _req(
            "global_pearl_no_overclaim_suite_green",
            bool(_truthy(no_over.get("all_passed")) and int(no_over.get("n_adversarial_cases_blocked", 0) or 0) == int(no_over.get("n_adversarial_cases", 0) or 0)),
            f"{no_over.get('matrix_version')}:{no_over.get('n_passed',0)}/{no_over.get('n_cases',0)};blocked={no_over.get('n_adversarial_cases_blocked',0)}/{no_over.get('n_adversarial_cases',0)}",
            f"{ID_GLOBAL_PEARL_NO_OVERCLAIM_MATRIX_VERSION}:all_passed=1;all_adversarial_blocked=1",
            "global_pearl_no_overclaim_suite_not_green",
            "The final report requires the Step-96 adversarial no-overclaim suite to pass and block every adversarial case.",
        ),
    )

    missing = [r.requirement for r in requirements if not r.passed]
    blockers = sorted(set(r.blocker_class for r in requirements if not r.passed))
    final_allowed = int(not missing)
    global_full_id_backend_ready = int(
        final_allowed
        and _truthy(gate.get("promotion_allowed"))
        and _truthy(flip.get("global_full_id_controlled_flip_allowed"))
    )
    pearl_runtime_ready = int(
        final_allowed
        and _truthy(release.get("global_pearl_veto_release_allowed"))
        and _truthy(release.get("attestation_verified"))
    )
    no_over_green = int(_truthy(no_over.get("all_passed")))

    report = FinalPearlReadinessReport(
        matrix_version=ID_FINAL_PEARL_READINESS_REPORT_VERSION,
        level=ID_FINAL_PEARL_READINESS_REPORT_LEVEL,
        scope=ID_FINAL_PEARL_READINESS_SCOPE,
        final_pearl_readiness_allowed=final_allowed,
        global_full_id_backend_ready=global_full_id_backend_ready,
        pearl_complete_veto_runtime_ready=pearl_runtime_ready,
        adversarial_no_overclaim_passed=no_over_green,
        id_full_promotion_gate=_s(gate.get("matrix_version")),
        id_full_promotion_gate_passed=int(_truthy(gate.get("promotion_allowed"))),
        id_global_full_id_controlled_flip=_s(flip.get("matrix_version")),
        id_global_full_id_controlled_flip_passed=int(_truthy(flip.get("global_full_id_controlled_flip_allowed"))),
        id_global_pearl_veto_attestation=_s(release.get("matrix_version")),
        id_global_pearl_veto_release_allowed=int(_truthy(release.get("global_pearl_veto_release_allowed"))),
        id_global_pearl_no_overclaim_matrix=_s(no_over.get("matrix_version")),
        id_global_pearl_no_overclaim_passed=no_over_green,
        full_recursive_id_implemented=int(_truthy(gate.get("full_recursive_id_implemented"))),
        full_id_claim_allowed=int(_truthy(gate.get("full_id_claim_allowed"))),
        id_full_readiness_matrix=_s(gate.get("id_full_readiness_matrix")),
        id_oracle_parity_matrix=_s(gate.get("id_oracle_parity_matrix")),
        id_full_recursive_kernel_matrix=_s(kernel.get("matrix_version")),
        id_full_recursive_oracle_expansion_matrix=_s(oracle_expansion.get("matrix_version")),
        failure_certificate_coverage_matrix=_s(gate.get("failure_certificate_coverage_matrix")),
        recursive_formula_authority_coverage_matrix=_s(gate.get("full_recursive_formula_authority_coverage_matrix")),
        n_kernel_cases=int(kernel.get("n_cases", 0) or 0),
        n_kernel_passed=int(kernel.get("n_passed", 0) or 0),
        n_oracle_expansion_cases=int(gate.get("n_full_recursive_oracle_expansion_cases", 0) or 0),
        n_oracle_expansion_passed=int(gate.get("n_full_recursive_oracle_expansion_passed", 0) or 0),
        n_identified_formula_rows_audited=int(gate.get("n_identified_formula_rows_audited", 0) or 0),
        n_full_recursive_formula_authority=int(gate.get("n_full_recursive_formula_authority", 0) or 0),
        n_no_overclaim_cases=int(no_over.get("n_cases", 0) or 0),
        n_adversarial_cases_blocked=int(no_over.get("n_adversarial_cases_blocked", 0) or 0),
        n_requirements=len(requirements),
        n_requirements_passed=sum(1 for r in requirements if r.passed),
        n_blockers=len(blockers),
        blocker_classes="|".join(blockers),
        missing_required_flags="|".join(missing),
        report_digest="",
        requirements=requirements,
    )
    payload = report.to_dict()
    if include_subreports:
        payload["subreports"] = {
            "promotion_gate": gate,
            "controlled_flip": flip,
            "global_pearl_veto_release": release,
            "global_pearl_no_overclaim": no_over,
        }
    else:
        payload["subreports"] = {}
    payload["final_pearl_readiness_claim"] = (
        "CausalGate supports Global Full-ID gated Pearl-complete veto authority for the released runtime path."
        if final_allowed
        else "Global Pearl readiness blocked: " + ("|".join(blockers) or "unknown")
    )
    payload["report_digest"] = final_pearl_readiness_report_digest(payload)
    return payload


__all__ = [
    "ID_FINAL_PEARL_READINESS_REPORT_VERSION",
    "ID_FINAL_PEARL_READINESS_REPORT_LEVEL",
    "ID_FINAL_PEARL_READINESS_SCOPE",
    "FinalPearlReadinessRequirement",
    "FinalPearlReadinessReport",
    "final_pearl_readiness_report_digest",
    "run_final_pearl_readiness_report",
]
