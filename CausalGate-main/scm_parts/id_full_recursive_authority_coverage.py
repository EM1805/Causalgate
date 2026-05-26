from __future__ import annotations

"""Step 86 recursive formula-authority coverage matrix.

This module is a promotion-readiness audit, not a new ID algorithm and not a
Full-ID/Pearl-complete claim.  After Step 84 the failure-certificate side is complete for the public corpus and
Step 85 made formula-authority gaps measurable.  Step 86 adds the first strong
Pearl-facing layer: a scoped recursive-ID trace certificate can upgrade an
identified public formula row from finite/template authority to full-recursive
trace authority **for the audited public surface**.  This is still not a global
arbitrary-ID claim; the promotion gate must keep requiring backend capability
flags before any Pearl-complete wording is allowed.
"""

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Mapping, Sequence

from .id_algorithm_common import _s
from .id_full_readiness import run_full_id_readiness_matrix
from .id_oracle_parity import run_id_oracle_parity_matrix
from .id_step80_audited_fuzz import ID_STEP80_AUDITED_FUZZ_AUTHORITY
from .id_full_recursive_trace_authority import FULL_RECURSIVE_TRACE_FORMULA_AUTHORITY
from .id_status import id_capability_flags

ID_FULL_RECURSIVE_AUTHORITY_COVERAGE_VERSION = "id_full_recursive_authority_coverage_v2_step86"
ID_FULL_RECURSIVE_AUTHORITY_COVERAGE_LEVEL = (
    "identified_formula_authority_coverage_audit_for_full_id_promotion_"
    "with_step86_recursive_trace_certificates_no_global_full_id_claim"
)

FULL_RECURSIVE_FORMULA_AUTHORITIES = {
    "full_recursive_id_canonical_formula_authority",
    "full_recursive_id_formula_authority",
    "shpitser_pearl_full_recursive_id_authority",
    FULL_RECURSIVE_TRACE_FORMULA_AUTHORITY,
}

FINITE_OR_TEMPLATE_AUTHORITIES = {
    "id_canonical_formula_step60",
    "recursive_id_set_expression_diagnostic_step75",
    "recursive_id_set_expression_diagnostic_step79",
    ID_STEP80_AUDITED_FUZZ_AUTHORITY,
}

RAW_DELEGATED_FORMULA_AUTHORITY = "recursive_id_set_expression_diagnostic"


@dataclass(frozen=True)
class FullRecursiveAuthorityCoverageRow:
    source_matrix: str
    row_id: str
    identified: bool
    primary_formula_authority: str
    effective_formula_authority: str
    authority_class: str
    recursive_trace_authority: str
    recursive_trace_certified: int
    formula_or_ast_evidence_present: int
    raw_delegated_formula_authority: int
    full_recursive_formula_authority: int
    finite_or_template_formula_authority: int
    primary_finite_or_template_formula_authority: int
    promotion_complete: int
    failure: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "pass", "passed", "green", "complete"}


def _authority_class(authority: str) -> str:
    if not authority:
        return "missing_formula_authority"
    if authority == RAW_DELEGATED_FORMULA_AUTHORITY:
        return "raw_delegated_formula_authority"
    if authority in FULL_RECURSIVE_FORMULA_AUTHORITIES:
        return "full_recursive_formula_authority"
    if authority in FINITE_OR_TEMPLATE_AUTHORITIES or authority.startswith("recursive_id_set_expression_diagnostic_step"):
        return "finite_or_template_formula_authority"
    return "other_formula_authority"


def _evidence_present(row: Mapping[str, object]) -> int:
    # Readiness/oracle rows expose display formula and canonical rules.  Fuzz
    # rows expose explicit formula/AST presence flags.  Either is enough for the
    # current no-overclaim audit, but neither upgrades a row to full-recursive
    # authority by itself.
    if _truthy(row.get("formula_ast_present")) or _truthy(row.get("formula_present")):
        return 1
    if _s(row.get("formula")) or _s(row.get("canonical_rules")) or _s(row.get("identification_status")):
        return 1
    return 0


def _row(source_matrix: str, row_id: object, authority: object, row: Mapping[str, object]) -> FullRecursiveAuthorityCoverageRow:
    primary_auth = _s(authority)
    trace_auth = _s(row.get("recursive_trace_authority"))
    trace_certified = int(_truthy(row.get("recursive_trace_certified")))
    effective_auth = trace_auth if trace_certified and trace_auth else primary_auth
    klass = _authority_class(effective_auth)
    primary_klass = _authority_class(primary_auth)
    evidence = _evidence_present(row)
    raw = int(primary_klass == "raw_delegated_formula_authority")
    full = int(klass == "full_recursive_formula_authority")
    finite = int(klass == "finite_or_template_formula_authority")
    primary_finite = int(primary_klass == "finite_or_template_formula_authority")
    failures: List[str] = []
    if not primary_auth:
        failures.append("missing_primary_formula_authority")
    if not evidence:
        failures.append("missing_formula_or_trace_evidence")
    if raw:
        failures.append("raw_delegated_formula_authority")
    if trace_certified and trace_auth != FULL_RECURSIVE_TRACE_FORMULA_AUTHORITY:
        failures.append("unexpected_recursive_trace_authority")
    return FullRecursiveAuthorityCoverageRow(
        source_matrix=source_matrix,
        row_id=_s(row_id),
        identified=True,
        primary_formula_authority=primary_auth,
        effective_formula_authority=effective_auth,
        authority_class=klass,
        recursive_trace_authority=trace_auth,
        recursive_trace_certified=trace_certified,
        formula_or_ast_evidence_present=evidence,
        raw_delegated_formula_authority=raw,
        full_recursive_formula_authority=full,
        finite_or_template_formula_authority=finite,
        primary_finite_or_template_formula_authority=primary_finite,
        promotion_complete=int(full and evidence and not raw),
        failure="; ".join(failures),
    )


def _iter_identified_authority_rows(readiness: Mapping[str, object], oracle: Mapping[str, object]) -> Iterable[FullRecursiveAuthorityCoverageRow]:
    readiness_version = _s(readiness.get("matrix_version")) or "id_full_readiness_matrix"
    for row in readiness.get("rows", []) or []:
        if not isinstance(row, Mapping) or not _truthy(row.get("identified")):
            continue
        primary = _s(row.get("primary_formula_authority")) or _s(row.get("joint_primary_formula_authority"))
        yield _row(readiness_version, row.get("case_id"), primary, row)

    oracle_version = _s(oracle.get("matrix_version")) or "id_oracle_parity_matrix"
    for row in oracle.get("rows", []) or []:
        if not isinstance(row, Mapping) or not _truthy(row.get("identified")):
            continue
        yield _row(oracle_version, row.get("case_id"), row.get("primary_formula_authority"), row)

    fuzz = oracle.get("fuzz", {}) if isinstance(oracle.get("fuzz"), Mapping) else {}
    fuzz_version = _s(fuzz.get("matrix_version")) or oracle_version + ":fuzz"
    for row in fuzz.get("rows", []) or []:
        if not isinstance(row, Mapping) or not _truthy(row.get("identified")):
            continue
        yield _row(fuzz_version, row.get("fuzz_id"), row.get("primary_formula_authority"), row)


def run_full_recursive_authority_coverage_matrix(
    *,
    readiness: Mapping[str, object] | None = None,
    oracle: Mapping[str, object] | None = None,
) -> Dict[str, object]:
    """Audit whether identified public formulas are promotion-ready.

    The audit surface is clean for no-overclaim usage only when all identified
    rows have formula/AST evidence and recursive trace/full-recursive authority.
    """
    readiness_payload = dict(readiness or run_full_id_readiness_matrix())
    oracle_payload = dict(oracle or run_id_oracle_parity_matrix())
    rows = list(_iter_identified_authority_rows(readiness_payload, oracle_payload))

    n_total = len(rows)
    n_full = sum(r.full_recursive_formula_authority for r in rows)
    n_finite = sum(r.finite_or_template_formula_authority for r in rows)
    n_primary_finite = sum(r.primary_finite_or_template_formula_authority for r in rows)
    n_trace_certified = sum(r.recursive_trace_certified for r in rows)
    n_raw = sum(r.raw_delegated_formula_authority for r in rows)
    n_missing = sum(1 for r in rows if r.authority_class == "missing_formula_authority")
    n_evidence = sum(r.formula_or_ast_evidence_present for r in rows)
    n_complete = sum(r.promotion_complete for r in rows)
    n_failures = sum(1 for r in rows if r.failure)
    authority_classes = sorted(set(r.authority_class for r in rows))
    raw_ids = [r.row_id for r in rows if r.raw_delegated_formula_authority]
    missing_evidence_ids = [r.row_id for r in rows if not r.formula_or_ast_evidence_present]
    finite_authorities = sorted(set(r.effective_formula_authority for r in rows if r.finite_or_template_formula_authority))
    primary_finite_authorities = sorted(set(r.primary_formula_authority for r in rows if r.primary_finite_or_template_formula_authority))
    full_authorities = sorted(set(r.effective_formula_authority for r in rows if r.full_recursive_formula_authority))

    public_clean = int(n_total > 0 and n_raw == 0 and n_missing == 0 and n_evidence == n_total)
    promotion_complete = int(n_total > 0 and n_complete == n_total)
    blocker_reason = (
        "no_full_recursive_formula_authority_rows_yet_step86"
        if public_clean and not promotion_complete and n_full == 0
        else (
            "finite_or_template_authority_rows_still_present_step86"
            if public_clean and not promotion_complete
            else (
                "formula_authority_coverage_complete"
                if promotion_complete
                else "raw_or_missing_formula_authority_evidence_blocks_promotion_step86"
            )
        )
    )

    return {
        "matrix_version": ID_FULL_RECURSIVE_AUTHORITY_COVERAGE_VERSION,
        "level": ID_FULL_RECURSIVE_AUTHORITY_COVERAGE_LEVEL,
        "n_identified_formula_rows_audited": n_total,
        "n_formula_authority_rows_with_evidence": n_evidence,
        "n_raw_delegated_formula_authority": n_raw,
        "n_missing_formula_authority": n_missing,
        "n_full_recursive_formula_authority": n_full,
        "n_finite_or_template_formula_authority": n_finite,
        "n_primary_finite_or_template_formula_authority": n_primary_finite,
        "n_recursive_trace_certified_formula_authority": n_trace_certified,
        "n_promotion_complete_formula_authority_rows": n_complete,
        "n_failed_rows": n_failures,
        "all_identified_formula_rows_public_clean": public_clean,
        "pearl_formula_authority_coverage_complete": promotion_complete,
        "full_recursive_formula_authorities_observed": "|".join(full_authorities),
        "finite_or_template_authorities_observed": "|".join(finite_authorities),
        "primary_finite_or_template_authorities_observed": "|".join(primary_finite_authorities),
        "authority_classes_observed": "|".join(authority_classes),
        "raw_delegated_row_ids": "|".join(raw_ids),
        "missing_formula_or_trace_evidence_row_ids": "|".join(missing_evidence_ids),
        "promotion_blocker_reason": blocker_reason,
        "full_id_claim_allowed": int(id_capability_flags().get("full_recursive_id_implemented") == 1 and id_capability_flags().get("full_id_claim_allowed") == 1),
        "rows": [r.to_dict() for r in rows],
    }


__all__ = [
    "ID_FULL_RECURSIVE_AUTHORITY_COVERAGE_VERSION",
    "ID_FULL_RECURSIVE_AUTHORITY_COVERAGE_LEVEL",
    "FULL_RECURSIVE_TRACE_FORMULA_AUTHORITY",
    "FULL_RECURSIVE_FORMULA_AUTHORITIES",
    "FINITE_OR_TEMPLATE_AUTHORITIES",
    "RAW_DELEGATED_FORMULA_AUTHORITY",
    "FullRecursiveAuthorityCoverageRow",
    "run_full_recursive_authority_coverage_matrix",
]
