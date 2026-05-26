from __future__ import annotations

"""Step 92 broad Full-recursive-ID kernel oracle expansion.

Step 91 made the recursive-ID kernel a first-class backend artifact.  Step 92
adds a wider, deterministic oracle-expansion surface around that kernel before
any global Full-ID/Pearl-complete flag can be flipped.  This is intentionally an
audit matrix, not a claim flip: every sampled ADMG query must either complete
with an identified formula/AST or with a formal failure certificate, and the
global Full-ID flags remain off.
"""

from dataclasses import asdict, dataclass
from functools import lru_cache
from itertools import combinations
from typing import Dict, Iterable, List, Sequence, Tuple

from .admg import ADMG, admg_from_edges
from .graph_criteria import directed_cycle_nodes
from .id_algorithm_common import _dedupe, _s
from .id_full_recursive_kernel import (
    ID_FULL_RECURSIVE_KERNEL_AUTHORITY,
    ID_FULL_RECURSIVE_KERNEL_VERSION,
    full_recursive_id_kernel_diagnostic,
)
from .id_status import id_capability_flags

ID_FULL_RECURSIVE_ORACLE_EXPANSION_VERSION = "id_full_recursive_oracle_expansion_v1_step92"
ID_FULL_RECURSIVE_ORACLE_EXPANSION_LEVEL = (
    "broad_deterministic_full_recursive_id_kernel_oracle_expansion_over_curated_"
    "and_stratified_admg_surfaces_before_any_global_full_id_claim_flip"
)

Directed = Tuple[str, str]
Bidirected = Tuple[str, str]


@dataclass(frozen=True)
class FullRecursiveIDOracleExpansionCase:
    case_id: str
    description: str
    graph: ADMG
    treatments: Sequence[str]
    outcomes: Sequence[str]
    case_kind: str
    expected_identified: int | None = None
    expected_rules_any: Sequence[str] = ()
    expected_status_contains: str = ""


@dataclass(frozen=True)
class FullRecursiveIDOracleExpansionRow:
    case_id: str
    case_kind: str
    description: str
    passed: int
    identified: int
    expected_identified: str
    nonidentified_certified: int
    kernel_completed: int
    no_pending_kernel_blocker: int
    expression_status: str
    expected_status_contains: str
    applied_rules: str
    expected_rules_any: str
    formula_ast_present: int
    formal_hedge_certificate_present: int
    carried_q_recursion_used: int
    district_decomposition_used: int
    q_factor_used: int
    observed_dag_used: int
    directed_edges: str = ""
    bidirected_edges: str = ""
    failure: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _edge_text(edges: Iterable[Tuple[str, str]], arrow: str) -> str:
    return "|".join(f"{a}{arrow}{b}" for a, b in edges)


def _case_graph(nodes: Sequence[str], directed: Sequence[Directed], bidirected: Sequence[Bidirected] = ()) -> ADMG:
    return admg_from_edges(nodes, directed, bidirected)


@lru_cache(maxsize=1)
def full_recursive_oracle_expansion_curated_cases() -> List[FullRecursiveIDOracleExpansionCase]:
    """Curated step-92 cases that exercise broader kernel branches than Step 91."""
    return [
        FullRecursiveIDOracleExpansionCase(
            case_id="oracle92_observed_parallel_mediators",
            description="Observed parallel mediators should complete through ID-6 set-valued truncated factorization.",
            graph=_case_graph(["X", "A", "B", "Y"], [("X", "A"), ("X", "B"), ("A", "Y"), ("B", "Y")]),
            treatments=("X",),
            outcomes=("Y",),
            case_kind="curated_observed_dag",
            expected_identified=1,
            expected_rules_any=("ID-6",),
            expected_status_contains="observed_dag",
        ),
        FullRecursiveIDOracleExpansionCase(
            case_id="oracle92_parallel_frontdoor_latent_xy",
            description="Parallel mediated graph with X<->Y should complete via recursive district decomposition.",
            graph=_case_graph(
                ["X", "A", "B", "Y"],
                [("X", "A"), ("X", "B"), ("A", "Y"), ("B", "Y")],
                [("X", "Y")],
            ),
            treatments=("X",),
            outcomes=("Y",),
            case_kind="curated_id7_carried_q",
            expected_identified=1,
            expected_rules_any=("ID-4", "ID-7"),
            expected_status_contains="recursive_district_decomposition",
        ),
        FullRecursiveIDOracleExpansionCase(
            case_id="oracle92_three_mediator_chain_latent_xy",
            description="Three-mediator chain with X<->Y exercises deeper carried-Q recursion than the Step-91 corpus.",
            graph=_case_graph(
                ["X", "A", "B", "C", "Y"],
                [("X", "A"), ("A", "B"), ("B", "C"), ("C", "Y")],
                [("X", "Y")],
            ),
            treatments=("X",),
            outcomes=("Y",),
            case_kind="curated_deeper_id7_chain",
            expected_identified=1,
            expected_rules_any=("ID-4", "ID-7"),
            expected_status_contains="recursive_district_decomposition",
        ),
        FullRecursiveIDOracleExpansionCase(
            case_id="oracle92_three_mediator_chain_latent_xc",
            description="Three-mediator chain with downstream X<->C confounding should complete without a template-only authority.",
            graph=_case_graph(
                ["X", "A", "B", "C", "Y"],
                [("X", "A"), ("A", "B"), ("B", "C"), ("C", "Y")],
                [("X", "C")],
            ),
            treatments=("X",),
            outcomes=("Y",),
            case_kind="curated_downstream_confounding",
            expected_identified=1,
            expected_rules_any=("ID-4", "ID-7"),
            expected_status_contains="recursive_district_decomposition",
        ),
        FullRecursiveIDOracleExpansionCase(
            case_id="oracle92_three_parallel_frontdoor_latent_xy",
            description="Three parallel mediators with X<->Y expands the finite parallel-frontdoor surface.",
            graph=_case_graph(
                ["X", "A", "B", "C", "Y"],
                [("X", "A"), ("X", "B"), ("X", "C"), ("A", "Y"), ("B", "Y"), ("C", "Y")],
                [("X", "Y")],
            ),
            treatments=("X",),
            outcomes=("Y",),
            case_kind="curated_parallel_id7",
            expected_identified=1,
            expected_rules_any=("ID-4", "ID-7"),
            expected_status_contains="recursive_district_decomposition",
        ),
        FullRecursiveIDOracleExpansionCase(
            case_id="oracle92_mixed_chain_parallel_latent_xy",
            description="Mixed chain/parallel mediator graph with X<->Y completes through recursive decomposition.",
            graph=_case_graph(
                ["X", "A", "B", "C", "Y"],
                [("X", "A"), ("A", "Y"), ("X", "B"), ("B", "C"), ("C", "Y")],
                [("X", "Y")],
            ),
            treatments=("X",),
            outcomes=("Y",),
            case_kind="curated_mixed_id7",
            expected_identified=1,
            expected_rules_any=("ID-4", "ID-7"),
            expected_status_contains="recursive_district_decomposition",
        ),
        FullRecursiveIDOracleExpansionCase(
            case_id="oracle92_w_step_irrelevant_intervention",
            description="Ancestor/W-step path should complete and expose ID-3 in the recursive trace.",
            graph=_case_graph(
                ["A", "X", "B", "Y"],
                [("A", "X"), ("X", "B"), ("B", "Y")],
                [("A", "Y")],
            ),
            treatments=("X",),
            outcomes=("Y",),
            case_kind="curated_w_step",
            expected_identified=1,
            expected_rules_any=("ID-3", "ID-7"),
            expected_status_contains="recursive_district_decomposition",
        ),
        FullRecursiveIDOracleExpansionCase(
            case_id="oracle92_simple_formal_hedge",
            description="Direct X/Y latent confounding with directed effect should remain a formal hedge failure.",
            graph=_case_graph(["X", "Y"], [("X", "Y")], [("X", "Y")]),
            treatments=("X",),
            outcomes=("Y",),
            case_kind="curated_formal_hedge_fail",
            expected_identified=0,
            expected_rules_any=("ID-5",),
            expected_status_contains="formal_hedge",
        ),
        FullRecursiveIDOracleExpansionCase(
            case_id="oracle92_multi_node_formal_hedge",
            description="Multi-node non-identifiable hedge should emit a formal failure certificate, not a pending branch.",
            graph=_case_graph(
                ["X", "M", "Y"],
                [("X", "M"), ("M", "Y")],
                [("X", "Y"), ("M", "Y")],
            ),
            treatments=("X",),
            outcomes=("Y",),
            case_kind="curated_formal_hedge_fail",
            expected_identified=0,
            expected_rules_any=("ID-5",),
            expected_status_contains="formal_hedge",
        ),
        FullRecursiveIDOracleExpansionCase(
            case_id="oracle92_set_valued_treatments_outcomes",
            description="Set-valued treatments/outcomes over an observed DAG should stay kernel-complete.",
            graph=_case_graph(
                ["X1", "X2", "A", "Y1", "Y2"],
                [("X1", "A"), ("X2", "A"), ("A", "Y1"), ("A", "Y2"), ("Y1", "Y2")],
            ),
            treatments=("X1", "X2"),
            outcomes=("Y1", "Y2"),
            case_kind="curated_set_query",
            expected_identified=1,
            expected_rules_any=("ID-6",),
            expected_status_contains="observed_dag",
        ),
    ]


def _fuzz_directed_patterns() -> List[Tuple[Directed, ...]]:
    backbone: List[Directed] = [("X", "A"), ("A", "B"), ("B", "C"), ("C", "Y")]
    extras: List[Directed] = [("X", "B"), ("X", "C"), ("A", "C"), ("A", "Y"), ("B", "Y"), ("X", "Y")]
    patterns: List[Tuple[Directed, ...]] = [tuple(backbone)]
    for edge in extras:
        patterns.append(tuple(backbone + [edge]))
    for e1, e2 in combinations(extras, 2):
        patterns.append(tuple(backbone + [e1, e2]))
    return patterns


def _fuzz_bidirected_patterns() -> List[Tuple[Bidirected, ...]]:
    pairs: List[Bidirected] = [("X", "Y"), ("X", "B"), ("X", "C"), ("A", "Y"), ("B", "Y"), ("A", "C")]
    patterns: List[Tuple[Bidirected, ...]] = [()]
    patterns.extend((pair,) for pair in pairs)
    patterns.extend(tuple(combo) for combo in list(combinations(pairs, 2))[:8])
    return patterns


@lru_cache(maxsize=8)
def full_recursive_oracle_expansion_fuzz_cases(*, limit: int = 96) -> List[FullRecursiveIDOracleExpansionCase]:
    """Deterministic stratified ADMG fuzz surface used by Step 92."""
    nodes = ("X", "A", "B", "C", "Y")
    out: List[FullRecursiveIDOracleExpansionCase] = []
    for directed in _fuzz_directed_patterns():
        for bidirected in _fuzz_bidirected_patterns():
            if len(out) >= limit:
                return out
            graph = admg_from_edges(nodes, directed, bidirected)
            if directed_cycle_nodes(graph):
                continue
            out.append(
                FullRecursiveIDOracleExpansionCase(
                    case_id=f"oracle92_fuzz_{len(out) + 1:03d}",
                    description="Deterministic five-node ADMG kernel fuzz case.",
                    graph=graph,
                    treatments=("X",),
                    outcomes=("Y",),
                    case_kind="stratified_five_node_admg_fuzz",
                )
            )
    return out


def _evaluate(case: FullRecursiveIDOracleExpansionCase) -> FullRecursiveIDOracleExpansionRow:
    diag = full_recursive_id_kernel_diagnostic(case.graph, case.treatments, case.outcomes).to_dict()
    rules = [r for r in _s(diag.get("applied_rules")).split("|") if r]
    identified = int(diag.get("identified", 0) or 0)
    nonidentified_certified = int(diag.get("nonidentified_certified", 0) or 0)
    formula_ast_present = int(diag.get("formula_ast_present", 0) or 0)
    formal_hedge_present = int(diag.get("formal_hedge_certificate_present", 0) or 0)
    failures: List[str] = []
    if case.expected_identified is not None and identified != int(case.expected_identified):
        failures.append("identified_mismatch")
    if not int(diag.get("kernel_completed", 0) or 0):
        failures.append("kernel_not_completed")
    if not int(diag.get("no_pending_kernel_blocker", 0) or 0):
        failures.append("pending_kernel_blocker")
    if identified and not formula_ast_present:
        failures.append("identified_missing_formula_ast")
    if not identified and not formal_hedge_present:
        failures.append("nonidentified_missing_formal_hedge_certificate")
    if case.expected_status_contains and case.expected_status_contains not in _s(diag.get("expression_status")):
        failures.append("status_mismatch")
    for expected_rule in case.expected_rules_any:
        if expected_rule not in rules:
            failures.append(f"missing_rule:{expected_rule}")
    return FullRecursiveIDOracleExpansionRow(
        case_id=case.case_id,
        case_kind=case.case_kind,
        description=case.description,
        passed=int(not failures),
        identified=identified,
        expected_identified="" if case.expected_identified is None else str(int(case.expected_identified)),
        nonidentified_certified=nonidentified_certified,
        kernel_completed=int(diag.get("kernel_completed", 0) or 0),
        no_pending_kernel_blocker=int(diag.get("no_pending_kernel_blocker", 0) or 0),
        expression_status=_s(diag.get("expression_status")),
        expected_status_contains=case.expected_status_contains,
        applied_rules="|".join(rules),
        expected_rules_any="|".join(case.expected_rules_any),
        formula_ast_present=formula_ast_present,
        formal_hedge_certificate_present=formal_hedge_present,
        carried_q_recursion_used=int(diag.get("carried_q_recursion_used", 0) or 0),
        district_decomposition_used=int(diag.get("district_decomposition_used", 0) or 0),
        q_factor_used=int(diag.get("q_factor_used", 0) or 0),
        observed_dag_used=int(diag.get("observed_dag_used", 0) or 0),
        directed_edges=_edge_text(case.graph.directed_edges, "->"),
        bidirected_edges=_edge_text(case.graph.bidirected_edges, "<->"),
        failure="; ".join(failures),
    )


@lru_cache(maxsize=8)
def run_full_recursive_oracle_expansion_matrix(*, include_fuzz: bool = True, fuzz_limit: int = 96) -> Dict[str, object]:
    curated_cases = full_recursive_oracle_expansion_curated_cases()
    fuzz_cases = full_recursive_oracle_expansion_fuzz_cases(limit=fuzz_limit) if include_fuzz else []
    rows = [_evaluate(c) for c in curated_cases + fuzz_cases]
    curated_rows = [r for r in rows if r.case_id.startswith("oracle92_") and not r.case_id.startswith("oracle92_fuzz_")]
    fuzz_rows = [r for r in rows if r.case_id.startswith("oracle92_fuzz_")]
    n_passed = sum(r.passed for r in rows)
    n_identified = sum(r.identified for r in rows)
    n_nonidentified_certified = sum((not r.identified) and r.nonidentified_certified for r in rows)
    n_pending = sum(1 for r in rows if not r.no_pending_kernel_blocker)
    n_identified_missing_ast = sum(1 for r in rows if r.identified and not r.formula_ast_present)
    n_nonidentified_missing_certificate = sum(1 for r in rows if (not r.identified) and not r.formal_hedge_certificate_present)
    flags = id_capability_flags()
    all_passed = int(rows and n_passed == len(rows))
    return {
        "matrix_version": ID_FULL_RECURSIVE_ORACLE_EXPANSION_VERSION,
        "level": ID_FULL_RECURSIVE_ORACLE_EXPANSION_LEVEL,
        "kernel_matrix_version": ID_FULL_RECURSIVE_KERNEL_VERSION,
        "kernel_authority": ID_FULL_RECURSIVE_KERNEL_AUTHORITY,
        "all_passed": all_passed,
        "n_cases": len(rows),
        "n_passed": n_passed,
        "n_failed": len(rows) - n_passed,
        "n_curated_cases": len(curated_rows),
        "n_curated_passed": sum(r.passed for r in curated_rows),
        "n_fuzz_cases": len(fuzz_rows),
        "n_fuzz_passed": sum(r.passed for r in fuzz_rows),
        "n_identified": n_identified,
        "n_nonidentified_certified": n_nonidentified_certified,
        "n_pending_kernel_blockers": n_pending,
        "n_identified_missing_formula_ast": n_identified_missing_ast,
        "n_nonidentified_missing_formal_certificate": n_nonidentified_missing_certificate,
        "n_carried_q_recursion_used": sum(r.carried_q_recursion_used for r in rows),
        "n_district_decomposition_used": sum(r.district_decomposition_used for r in rows),
        "n_q_factor_used": sum(r.q_factor_used for r in rows),
        "n_observed_dag_used": sum(r.observed_dag_used for r in rows),
        "global_full_recursive_id_implemented": int(bool(flags.get("full_recursive_id_implemented"))),
        "global_full_id_claim_allowed": int(bool(flags.get("full_id_claim_allowed"))),
        "global_claim_still_blocked": int(not bool(flags.get("full_id_claim_allowed"))),
        "promotion_note": "oracle_expansion_green_but_global_flags_remain_required_step92" if all_passed else "oracle_expansion_failed_blocks_global_full_id_step92",
        "rows": [r.to_dict() for r in rows],
    }


__all__ = [
    "ID_FULL_RECURSIVE_ORACLE_EXPANSION_VERSION",
    "ID_FULL_RECURSIVE_ORACLE_EXPANSION_LEVEL",
    "FullRecursiveIDOracleExpansionCase",
    "FullRecursiveIDOracleExpansionRow",
    "full_recursive_oracle_expansion_curated_cases",
    "full_recursive_oracle_expansion_fuzz_cases",
    "run_full_recursive_oracle_expansion_matrix",
]
