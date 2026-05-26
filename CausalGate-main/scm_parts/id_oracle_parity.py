from __future__ import annotations

"""Step 79 oracle/parity and no-overclaim fuzz guards for SCM Full-ID.

This module adds regression authority around the public ``full_id`` facade.
Step 80 also verifies that the finite deterministic-fuzz recursive ID-7
closures that remain after Step 79 are promoted to audited authority.  The invariant
remains safety oriented: every sampled query must either identify with a formula
+ AST, or return an explicit failure/rejection certificate, and, after Step 94, the global Full-ID claim must be enabled only by the controlled promotion gate.
"""

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple
import json

from .admg import ADMG, admg_from_edges
from .id_algorithm_common import _dedupe, _s
from .id_failure_certificate import ID_FAILURE_CERTIFICATE_AUTHORITY
from .id_step80_audited_fuzz import ID_STEP80_AUDITED_FUZZ_AUTHORITY
from .id_full import full_id
from .id_full_recursive_trace_authority import recursive_trace_authority_for_result
from .id_status import id_capability_flags

ID_ORACLE_PARITY_MATRIX_VERSION = "id_oracle_parity_matrix_v3_step80"
ID_ORACLE_PARITY_LEVEL = (
    "curated_oracle_parity_and_deterministic_admg_fuzz_no_overclaim_guards_"
    "with_step79_downstream_confounded_chain_step80_audited_fuzz_closure_step94_global_claim_gate"
)


@dataclass(frozen=True)
class IDOracleParityCase:
    case_id: str
    description: str
    graph: ADMG
    treatments: Sequence[str]
    outcomes: Sequence[str]
    expected_identified: bool
    expected_status_contains: str = ""
    expected_primary_formula_authority: str = ""
    expected_rules: Sequence[str] = ()
    expected_formula_contains: Sequence[str] = ()
    expected_failure_certificate_status: str = ""
    expected_failure_certified: int | None = None
    expected_delegated_formula_gap: int = 0


@dataclass(frozen=True)
class IDOracleParityRow:
    case_id: str
    description: str
    passed: bool
    identified: bool
    expected_identified: bool
    identification_status: str
    expected_status_contains: str
    primary_formula_authority: str
    expected_primary_formula_authority: str
    canonical_rules: str
    expected_rules: str
    formula: str
    expected_formula_contains: str
    failure_certificate_status: str
    expected_failure_certificate_status: str
    failure_certified: int
    expected_failure_certified: str
    expected_delegated_formula_gap: int
    delegated_formula_gap: int
    full_id_claim_allowed: int
    recursive_trace_authority: str = ""
    recursive_trace_authority_status: str = ""
    recursive_trace_certified: int = 0
    recursive_trace_rules: str = ""
    failure: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class IDFuzzRow:
    fuzz_id: str
    passed: bool
    identified: bool
    identification_status: str
    primary_formula_authority: str
    failure_certificate_status: str
    full_id_claim_allowed: int
    formula_present: int
    formula_ast_present: int
    recursive_trace_authority: str = ""
    recursive_trace_authority_status: str = ""
    recursive_trace_certified: int = 0
    recursive_trace_rules: str = ""
    directed_edges: str = ""
    bidirected_edges: str = ""
    failure: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _join_edges(edges: Iterable[Tuple[str, str]], arrow: str) -> str:
    return "|".join(f"{a}{arrow}{b}" for a, b in edges)


def _contains_all(text: str, snippets: Sequence[str]) -> List[str]:
    return [snippet for snippet in snippets if snippet not in text]


def _oracle_graphs() -> List[IDOracleParityCase]:
    """Return curated parity cases with stable expected public behavior."""
    return [
        IDOracleParityCase(
            case_id="oracle_observed_chain_id6",
            description="Observed chain X -> A -> Y must stay canonical ID-6.",
            graph=admg_from_edges(["X", "A", "Y"], [("X", "A"), ("A", "Y")]),
            treatments=("X",),
            outcomes=("Y",),
            expected_identified=True,
            expected_status_contains="observed_dag_truncated_factorization",
            expected_primary_formula_authority="id_canonical_formula_step60",
            expected_rules=("ID-6",),
            expected_formula_contains=("sum_{A}", "P(A | X)", "P(Y | A)"),
        ),
        IDOracleParityCase(
            case_id="oracle_classic_frontdoor_id7",
            description="Classic frontdoor parity case must stay canonical gated ID-7.",
            graph=admg_from_edges(["X", "Z", "Y"], [("X", "Z"), ("Z", "Y")], [("X", "Y")]),
            treatments=("X",),
            outcomes=("Y",),
            expected_identified=True,
            expected_primary_formula_authority="id_canonical_formula_step60",
            expected_rules=("ID-4", "ID-7"),
            expected_formula_contains=("sum_{Z}", "X_prime", "P(Z | X)", "P(Y | X_prime,Z)"),
        ),
        IDOracleParityCase(
            case_id="oracle_step75_non_frontdoor_carried_q",
            description="Step-75 non-frontdoor carried-Q ancestor marginalization must remain identified without global Full-ID claim.",
            graph=admg_from_edges(
                ["A", "B", "C", "D", "E"],
                [("A", "B"), ("A", "C"), ("C", "D"), ("D", "E")],
                [("A", "D"), ("A", "E"), ("B", "D")],
            ),
            treatments=("A",),
            outcomes=("E",),
            expected_identified=True,
            expected_status_contains="identified_recursive_district_decomposition",
            expected_primary_formula_authority="recursive_id_set_expression_diagnostic_step75",
            expected_rules=("ID-7",),
            expected_formula_contains=("sum_{A'} P(A') * P(E | A',C,D)",),
        ),
        IDOracleParityCase(
            case_id="oracle_downstream_confounded_chain_canonical_step79",
            description="Known non-frontdoor recursive ID-7 chain now has strict owned canonical formula authority instead of delegated formula authority.",
            graph=admg_from_edges(
                ["X", "A", "B", "Y"],
                [("X", "A"), ("A", "B"), ("B", "Y")],
                [("X", "B")],
            ),
            treatments=("X",),
            outcomes=("Y",),
            expected_identified=True,
            expected_status_contains="identified_recursive_district_decomposition",
            expected_primary_formula_authority="id_canonical_formula_step60",
            expected_rules=("ID-4", "ID-7"),
            expected_formula_contains=("sum_{A,B}", "sum_{X_prime}", "P(B | X_prime,A)", "P(Y | X,A,B)"),
            expected_delegated_formula_gap=0,
        ),
        IDOracleParityCase(
            case_id="oracle_step80_chain_dual_bridge_audited_closure",
            description="Previously fuzz-delegated recursive ID-7 four-node chain now has Step-80 audited authority, not raw delegate authority.",
            graph=admg_from_edges(
                ["X", "A", "B", "Y"],
                [("X", "A"), ("A", "B"), ("B", "Y")],
                [("X", "B"), ("A", "Y")],
            ),
            treatments=("X",),
            outcomes=("Y",),
            expected_identified=True,
            expected_status_contains="identified_recursive_district_decomposition",
            expected_primary_formula_authority=ID_STEP80_AUDITED_FUZZ_AUTHORITY,
            expected_rules=("ID-4", "ID-7"),
            expected_formula_contains=("sum_{A,B}", "sum_{X'}", "P(Y | X,A,B)", "P(B | X',A)"),
            expected_delegated_formula_gap=0,
        ),
        IDOracleParityCase(
            case_id="oracle_direct_confounding_formal_hedge",
            description="Direct confounded effect X -> Y plus X <-> Y must stay formally hedge-certified non-ID.",
            graph=admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")]),
            treatments=("X",),
            outcomes=("Y",),
            expected_identified=False,
            expected_status_contains="blocked_formal_hedge_certificate",
            expected_primary_formula_authority=ID_FAILURE_CERTIFICATE_AUTHORITY,
            expected_failure_certificate_status="formal_hedge_certified_step68",
            expected_failure_certified=1,
        ),
        IDOracleParityCase(
            case_id="oracle_cycle_rejection_certificate",
            description="Directed cycles must stay rejected through the failure-certificate channel.",
            graph=admg_from_edges(["X", "Y"], [("X", "Y"), ("Y", "X")]),
            treatments=("X",),
            outcomes=("Y",),
            expected_identified=False,
            expected_status_contains="blocked_directed_cycle",
            expected_primary_formula_authority=ID_FAILURE_CERTIFICATE_AUTHORITY,
            expected_failure_certificate_status="rejected_directed_cycle_step68",
            expected_failure_certified=0,
        ),
    ]


def evaluate_oracle_parity_case(case: IDOracleParityCase, *, max_depth: int = 12) -> IDOracleParityRow:
    result = full_id(case.graph, case.treatments, case.outcomes, max_depth=max_depth).to_dict()
    status = _s(result.get("identification_status"))
    primary = _s(result.get("primary_formula_authority"))
    formula = _s(result.get("formula"))
    rules = _s(result.get("canonical_rules"))
    failure_status = _s(result.get("failure_certificate_status"))
    failure_certified = int(result.get("failure_certified") or 0)
    claim = int(result.get("full_id_claim_allowed") or 0)
    delegated_gap = int(bool(result.get("identified")) and primary == "recursive_id_set_expression_diagnostic")
    trace_authority = recursive_trace_authority_for_result(result)
    trace_authority_dict = trace_authority.to_dict()

    failures: List[str] = []
    if bool(result.get("identified")) != bool(case.expected_identified):
        failures.append(f"identified={result.get('identified')} expected={case.expected_identified}")
    if case.expected_status_contains and case.expected_status_contains not in status:
        failures.append(f"status={status} missing={case.expected_status_contains}")
    if case.expected_primary_formula_authority and primary != case.expected_primary_formula_authority:
        failures.append(f"primary_formula_authority={primary} expected={case.expected_primary_formula_authority}")
    for rule in case.expected_rules:
        if rule not in rules.split("|"):
            failures.append(f"canonical_rule_missing={rule}")
    for snippet in _contains_all(formula, case.expected_formula_contains):
        failures.append(f"formula_missing={snippet}")
    if case.expected_failure_certificate_status and failure_status != case.expected_failure_certificate_status:
        failures.append(f"failure_certificate_status={failure_status} expected={case.expected_failure_certificate_status}")
    if case.expected_failure_certified is not None and failure_certified != int(case.expected_failure_certified):
        failures.append(f"failure_certified={failure_certified} expected={case.expected_failure_certified}")
    if delegated_gap != int(case.expected_delegated_formula_gap):
        failures.append(f"delegated_formula_gap={delegated_gap} expected={case.expected_delegated_formula_gap}")
    expected_claim = int(id_capability_flags().get("full_recursive_id_implemented") == 1 and id_capability_flags().get("full_id_claim_allowed") == 1)
    if claim != expected_claim:
        failures.append(f"full_id_claim_allowed={claim} expected={expected_claim}")
    if bool(result.get("identified")) and (not formula or not _s(result.get("formula_ast_json"))):
        failures.append("identified_output_missing_formula_or_ast")
    if not bool(result.get("identified")) and not failure_status:
        failures.append("nonidentified_output_missing_failure_certificate_status")

    return IDOracleParityRow(
        case_id=case.case_id,
        description=case.description,
        passed=not failures,
        identified=bool(result.get("identified")),
        expected_identified=bool(case.expected_identified),
        identification_status=status,
        expected_status_contains=case.expected_status_contains,
        primary_formula_authority=primary,
        expected_primary_formula_authority=case.expected_primary_formula_authority,
        canonical_rules=rules,
        expected_rules="|".join(case.expected_rules),
        formula=formula,
        expected_formula_contains="|".join(case.expected_formula_contains),
        failure_certificate_status=failure_status,
        expected_failure_certificate_status=case.expected_failure_certificate_status,
        failure_certified=failure_certified,
        expected_failure_certified="" if case.expected_failure_certified is None else str(case.expected_failure_certified),
        expected_delegated_formula_gap=int(case.expected_delegated_formula_gap),
        delegated_formula_gap=delegated_gap,
        full_id_claim_allowed=claim,
        recursive_trace_authority=_s(trace_authority_dict.get("authority")),
        recursive_trace_authority_status=_s(trace_authority_dict.get("status")),
        recursive_trace_certified=int(trace_authority_dict.get("certified") or 0),
        recursive_trace_rules=_s(trace_authority_dict.get("rules")),
        failure="; ".join(failures),
    )


def _fuzz_graph_specs() -> Iterable[Tuple[Tuple[Tuple[str, str], ...], Tuple[Tuple[str, str], ...]]]:
    directed_patterns: List[Tuple[Tuple[str, str], ...]] = [
        (),
        (("X", "Y"),),
        (("X", "A"), ("A", "Y")),
        (("X", "A"), ("A", "B"), ("B", "Y")),
        (("X", "A"), ("X", "B"), ("A", "Y"), ("B", "Y")),
        (("A", "X"), ("X", "B"), ("B", "Y")),
        (("X", "A"), ("A", "Y"), ("B", "Y")),
        (("X", "B"), ("A", "B"), ("B", "Y")),
    ]
    bidirected_patterns: List[Tuple[Tuple[str, str], ...]] = [
        (),
        (("X", "Y"),),
        (("X", "A"),),
        (("A", "Y"),),
        (("X", "B"),),
        (("B", "Y"),),
        (("X", "B"), ("A", "Y")),
        (("X", "Y"), ("A", "B")),
        (("X", "A"), ("A", "B"), ("B", "Y")),
    ]
    for directed in directed_patterns:
        for bidirected in bidirected_patterns:
            yield directed, bidirected


def run_no_overclaim_fuzz_matrix(*, max_depth: int = 8) -> Dict[str, object]:
    rows: List[IDFuzzRow] = []
    nodes = ("X", "A", "B", "Y")
    allowed_identified_authorities = {
        "id_canonical_formula_step60",
        "recursive_id_set_expression_diagnostic",
        "recursive_id_set_expression_diagnostic_step75",
        ID_STEP80_AUDITED_FUZZ_AUTHORITY,
    }
    for idx, (directed, bidirected) in enumerate(_fuzz_graph_specs(), start=1):
        graph = admg_from_edges(nodes, directed, bidirected)
        result = full_id(graph, ["X"], ["Y"], max_depth=max_depth).to_dict()
        identified = bool(result.get("identified"))
        primary = _s(result.get("primary_formula_authority"))
        failure_status = _s(result.get("failure_certificate_status"))
        claim = int(result.get("full_id_claim_allowed") or 0)
        formula_present = int(bool(_s(result.get("formula"))))
        ast_present = int(bool(_s(result.get("formula_ast_json"))))
        trace_authority = recursive_trace_authority_for_result(result)
        trace_authority_dict = trace_authority.to_dict()
        failures: List[str] = []
        expected_claim = int(id_capability_flags().get("full_recursive_id_implemented") == 1 and id_capability_flags().get("full_id_claim_allowed") == 1)
        if claim != expected_claim:
            failures.append(f"full_id_claim_allowed={claim}_expected={expected_claim}")
        if identified:
            if primary not in allowed_identified_authorities:
                failures.append(f"unexpected_identified_authority={primary}")
            if not formula_present or not ast_present:
                failures.append("identified_missing_formula_or_ast")
        else:
            if primary != ID_FAILURE_CERTIFICATE_AUTHORITY:
                failures.append(f"nonidentified_primary_not_failure_certificate={primary}")
            if not failure_status:
                failures.append("nonidentified_missing_failure_certificate_status")
            if not ast_present:
                failures.append("nonidentified_missing_failure_ast")
        rows.append(IDFuzzRow(
            fuzz_id=f"fuzz_step76_{idx:03d}",
            passed=not failures,
            identified=identified,
            identification_status=_s(result.get("identification_status")),
            primary_formula_authority=primary,
            failure_certificate_status=failure_status,
            full_id_claim_allowed=claim,
            formula_present=formula_present,
            formula_ast_present=ast_present,
            recursive_trace_authority=_s(trace_authority_dict.get("authority")),
            recursive_trace_authority_status=_s(trace_authority_dict.get("status")),
            recursive_trace_certified=int(trace_authority_dict.get("certified") or 0),
            recursive_trace_rules=_s(trace_authority_dict.get("rules")),
            directed_edges=_join_edges(directed, "->"),
            bidirected_edges=_join_edges(bidirected, "<->"),
            failure="; ".join(failures),
        ))
    passed = sum(1 for row in rows if row.passed)
    delegated = sum(1 for row in rows if row.identified and row.primary_formula_authority == "recursive_id_set_expression_diagnostic")
    failure_certs = sum(1 for row in rows if (not row.identified) and bool(row.failure_certificate_status))
    return {
        "matrix_version": ID_ORACLE_PARITY_MATRIX_VERSION,
        "matrix_kind": "deterministic_admg_no_overclaim_fuzz",
        "n_cases": len(rows),
        "n_passed": passed,
        "n_failed": len(rows) - passed,
        "all_passed": int(passed == len(rows)),
        "n_identified": sum(1 for row in rows if row.identified),
        "n_nonidentified_with_failure_certificates": failure_certs,
        "n_delegated_identified_formula_authority": delegated,
        "full_id_claim_allowed": int(id_capability_flags().get("full_recursive_id_implemented") == 1 and id_capability_flags().get("full_id_claim_allowed") == 1),
        "remaining_gap_note": "raw delegated identified formulas remain blocked; after Step 94 the global claim is allowed only because the promotion gate is green",
        "rows": [row.to_dict() for row in rows],
    }


def run_id_oracle_parity_matrix(cases: Iterable[IDOracleParityCase] | None = None, *, include_fuzz: bool = True) -> Dict[str, object]:
    rows = [evaluate_oracle_parity_case(c) for c in (list(cases) if cases is not None else _oracle_graphs())]
    passed = sum(1 for row in rows if row.passed)
    delegated_gaps = sum(1 for row in rows if row.delegated_formula_gap)
    fuzz = run_no_overclaim_fuzz_matrix() if include_fuzz else {}
    fuzz_failed = int(fuzz.get("n_failed", 0) or 0) if fuzz else 0
    return {
        "matrix_version": ID_ORACLE_PARITY_MATRIX_VERSION,
        "matrix_kind": "oracle_parity_plus_no_overclaim_fuzz",
        "level": ID_ORACLE_PARITY_LEVEL,
        "n_oracle_cases": len(rows),
        "n_oracle_passed": passed,
        "n_oracle_failed": len(rows) - passed,
        "n_oracle_delegated_formula_gaps": delegated_gaps,
        "fuzz": fuzz,
        "all_passed": int(passed == len(rows) and fuzz_failed == 0),
        "full_id_claim_allowed": int(id_capability_flags().get("full_recursive_id_implemented") == 1 and id_capability_flags().get("full_id_claim_allowed") == 1),
        "full_id_claim_reason": (
            "Step 94 allows the global Full-ID claim only when oracle/parity/fuzz, failure coverage, recursive trace authority, and the promotion gate are green."
        ),
        "remaining_required_before_full_id_claim": [
            "turn any remaining raw delegated recursive ID-7 fuzz/oracle gaps into owned formulas, audited finite authority, or certified failures",
            "expand formal hedge coverage so every ID-5 FAIL branch is certified when mathematically non-identifiable",
            "expand deterministic fuzz to broader random/seeded ADMG families and IDC queries",
            "complete full IDC simplification beyond disconnectivity pruning and ratio-over-joint",
        ],
        "rows": [row.to_dict() for row in rows],
    }


__all__ = [
    "ID_ORACLE_PARITY_MATRIX_VERSION",
    "ID_ORACLE_PARITY_LEVEL",
    "IDOracleParityCase",
    "IDOracleParityRow",
    "IDFuzzRow",
    "evaluate_oracle_parity_case",
    "run_id_oracle_parity_matrix",
    "run_no_overclaim_fuzz_matrix",
]
