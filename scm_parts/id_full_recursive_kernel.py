from __future__ import annotations

"""Step 91 Full recursive-ID kernel readiness layer.

This module exposes the recursive ID engine as a first-class backend kernel
artifact.  It does not flip the global Full-ID claim flag.  Instead it audits
whether the current recursive expression runtime can operate as a kernel over a
representative arbitrary-ID surface: ID-1..ID-7 traces, multi-district
factorization, carried-Q recursion, observed-DAG set queries, and formal ID-5
hedge failure certificates.
"""

from dataclasses import asdict, dataclass
import json
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from .admg import ADMG, admg_from_edges
from .graph_criteria import directed_cycle_nodes
from .id_algorithm_common import _dedupe, _format_components, _joint_symbol, _s
from .id_recursive_expression import RecursiveIDExpressionDiagnostic, recursive_id_set_expression_diagnostic, _recursive_id_expression
from .id_status import id_capability_flags

ID_FULL_RECURSIVE_KERNEL_VERSION = "id_full_recursive_kernel_v1_step91"
ID_FULL_RECURSIVE_KERNEL_LEVEL = (
    "full_recursive_id_kernel_backend_audit_exposes_ID1_to_ID7_recursive_expression_"
    "district_decomposition_carried_Q_and_formal_hedge_certificate_paths_without_global_claim_flip"
)
ID_FULL_RECURSIVE_KERNEL_AUTHORITY = "full_recursive_id_kernel_trace_authority_step91"

_IDENTIFIED_TERMINAL_STATUSES = {
    "identified_no_intervention_base_case",
    "identified_graphical_zero_effect",
    "identified_q_input_observed_dag_truncated_factorization_step75",
    "identified_observed_dag_truncated_factorization_set_case",
    "identified_recursive_district_decomposition",
    "identified_q_factor_full_district",
    "identified_q_input_subdistrict_recursion",
    "identified_general_q_input_subdistrict_recursion",
}

_ACCEPTED_BLOCKED_STATUSES = {
    "blocked_formal_hedge_certificate",
    "blocked_directed_cycle",
    "invalid_set_query",
}

_PENDING_BLOCKER_CLASSES = {
    "subdistrict_q_factor_input_pending",
    "general_q_input_subproblem_blocked",
    "recursive_subproblem_blocked",
    "unhandled_recursive_case",
    "max_depth",
    "recursion_cycle_guard",
}


@dataclass(frozen=True)
class FullRecursiveIDKernelDiagnostic:
    kernel_version: str
    level: str
    treatments: str
    outcomes: str
    identified: int
    nonidentified_certified: int
    kernel_completed: int
    expression_status: str
    formula: str = ""
    expression_json: str = ""
    trace_json: str = ""
    applied_rules: str = ""
    n_trace_steps: int = 0
    blocker: str = ""
    blocker_class: str = ""
    pending_operator: str = ""
    reason_codes: str = ""
    formula_ast_present: int = 0
    formal_hedge_certificate_present: int = 0
    carried_q_recursion_used: int = 0
    district_decomposition_used: int = 0
    q_factor_used: int = 0
    observed_dag_used: int = 0
    no_pending_kernel_blocker: int = 0
    kernel_authority: str = ID_FULL_RECURSIVE_KERNEL_AUTHORITY
    full_recursive_id_implemented: int = 0
    full_id_claim_allowed: int = 0

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FullRecursiveIDKernelCase:
    case_id: str
    description: str
    graph: ADMG
    treatments: Sequence[str]
    outcomes: Sequence[str]
    expected_identified: int
    expected_nonidentified_certified: int = 0
    expected_rules: Sequence[str] = ()
    expected_status_contains: str = ""


@dataclass(frozen=True)
class FullRecursiveIDKernelMatrixRow:
    case_id: str
    description: str
    passed: int
    identified: int
    expected_identified: int
    nonidentified_certified: int
    expected_nonidentified_certified: int
    expression_status: str
    expected_status_contains: str
    applied_rules: str
    expected_rules: str
    kernel_completed: int
    no_pending_kernel_blocker: int
    formula_ast_present: int
    carried_q_recursion_used: int
    district_decomposition_used: int
    q_factor_used: int
    observed_dag_used: int
    formal_hedge_certificate_present: int
    reason_codes: str
    failure: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _join(values: Iterable[object]) -> str:
    return "|".join(_dedupe(values or []))


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "pass", "passed", "green", "complete"}


def _json_loads(raw: object) -> Dict[str, object]:
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _trace_steps(trace_json: str) -> List[Mapping[str, object]]:
    payload = _json_loads(trace_json)
    steps = payload.get("trace", []) if isinstance(payload, Mapping) else []
    return [s for s in steps if isinstance(s, Mapping)] if isinstance(steps, list) else []


def _rules_from_trace(trace_json: str) -> List[str]:
    mapping = {
        "id_base_no_intervention": "ID-1",
        "ancestor_reduction": "ID-2",
        "irrelevant_after_intervention_w_step": "ID-3",
        "district_decomposition_g_v_minus_x": "ID-4",
        "formal_hedge_certificate": "ID-5",
        "observed_dag_truncated_factorization": "ID-6",
        "q_factor_full_district": "ID-6",
        "graphical_zero_effect": "ID-6",
        "q_input_subdistrict_recursion": "ID-7",
        "q_input_general_recursion_step44": "ID-7",
        "q_input_general_carried_q_recursion_step51": "ID-7",
        "q_input_ancestor_marginalization_step75": "ID-7",
    }
    out: List[str] = []
    seen = set()
    for step in _trace_steps(trace_json):
        rule = mapping.get(_s(step.get("step")))
        status = _s(step.get("status"))
        if not rule or status in {"entered", "not_needed", "skipped"}:
            continue
        if rule not in seen:
            seen.add(rule)
            out.append(rule)
    return out


def _formula_ast_present(expression_json: str) -> int:
    payload = _json_loads(expression_json)
    return int(isinstance(payload.get("formula_ast"), Mapping))


def _formal_hedge_present(expression_json: str, expr: RecursiveIDExpressionDiagnostic) -> int:
    if expr.blocker_class == "formal_hedge_certificate" or expr.expression_status == "blocked_formal_hedge_certificate":
        return 1
    payload = _json_loads(expression_json)
    return int(isinstance(payload.get("formal_hedge_candidate"), Mapping))


def _kernel_completed(expr: RecursiveIDExpressionDiagnostic) -> int:
    if expr.expression_identified and expr.expression_status in _IDENTIFIED_TERMINAL_STATUSES:
        return 1
    if expr.expression_status in _ACCEPTED_BLOCKED_STATUSES:
        return 1
    if expr.blocker_class == "formal_hedge_certificate":
        return 1
    return 0


def _no_pending_blocker(expr: RecursiveIDExpressionDiagnostic) -> int:
    if expr.blocker_class in _PENDING_BLOCKER_CLASSES:
        return 0
    if expr.expression_status.startswith("blocked_") and expr.expression_status not in _ACCEPTED_BLOCKED_STATUSES:
        return 0
    return 1


def full_recursive_id_kernel_diagnostic(
    admg: ADMG,
    treatments: Sequence[object] | object,
    outcomes: Sequence[object] | object,
    *,
    max_depth: int = 12,
    capability_flags: Mapping[str, object] | None = None,
) -> FullRecursiveIDKernelDiagnostic:
    """Run the Step-91 recursive-ID kernel audit for a set-valued query.

    The returned diagnostic is deliberately separate from the public
    ``full_id_claim_allowed`` flag.  A completed kernel query means the recursive
    engine produced either a formula/AST or a formal rejection/certificate; it
    does not by itself authorize global Pearl-complete wording.
    """
    if isinstance(treatments, str):
        x = tuple(_dedupe([treatments]))
    else:
        x = tuple(_dedupe(treatments or []))
    if isinstance(outcomes, str):
        y = tuple(_dedupe([outcomes]))
    else:
        y = tuple(_dedupe(outcomes or []))

    flags = dict(capability_flags or id_capability_flags())
    expr = _recursive_id_expression(admg, y, x, max_depth=max_depth) if not x and y else recursive_id_set_expression_diagnostic(admg, x, y, max_depth=max_depth)
    steps = _trace_steps(expr.trace_json)
    rules = _rules_from_trace(expr.trace_json)
    trace_text = expr.trace_json or ""
    expression_text = expr.expression_json or ""
    return FullRecursiveIDKernelDiagnostic(
        kernel_version=ID_FULL_RECURSIVE_KERNEL_VERSION,
        level=ID_FULL_RECURSIVE_KERNEL_LEVEL,
        treatments=_join(x),
        outcomes=_join(y),
        identified=int(bool(expr.expression_identified)),
        nonidentified_certified=int((not expr.expression_identified) and _formal_hedge_present(expression_text, expr)),
        kernel_completed=_kernel_completed(expr),
        expression_status=expr.expression_status,
        formula=expr.formula,
        expression_json=expr.expression_json,
        trace_json=expr.trace_json,
        applied_rules="|".join(rules),
        n_trace_steps=len(steps),
        blocker=expr.blocker,
        blocker_class=expr.blocker_class,
        pending_operator=expr.pending_operator,
        reason_codes=expr.reason_codes,
        formula_ast_present=_formula_ast_present(expression_text),
        formal_hedge_certificate_present=_formal_hedge_present(expression_text, expr),
        carried_q_recursion_used=int("q_input_subdistrict_recursion" in trace_text or "q_input_general_carried_q_recursion_step51" in trace_text or "q_input_ancestor_marginalization_step75" in trace_text),
        district_decomposition_used=int("district_decomposition_g_v_minus_x" in trace_text),
        q_factor_used=int("q_factor_full_district" in trace_text),
        observed_dag_used=int("observed_dag_truncated_factorization" in trace_text),
        no_pending_kernel_blocker=_no_pending_blocker(expr),
        full_recursive_id_implemented=int(_truthy(flags.get("full_recursive_id_implemented"))),
        full_id_claim_allowed=int(_truthy(flags.get("full_id_claim_allowed"))),
    )


def _case_graph(nodes: Sequence[str], directed: Sequence[Tuple[str, str]], bidirected: Sequence[Tuple[str, str]] = ()) -> ADMG:
    return admg_from_edges(nodes, directed, bidirected)


def full_recursive_id_kernel_cases() -> List[FullRecursiveIDKernelCase]:
    """Representative Step-91 backend kernel cases.

    This is intentionally a backend/kernel matrix, not a statistical oracle.  It
    focuses on the recursive branches that must be first-class before the global
    Full-ID claim can be promoted by later broad parity/fuzz steps.
    """
    return [
        FullRecursiveIDKernelCase(
            case_id="kernel_id1_no_intervention_set_outcome",
            description="ID-1 no-intervention set outcome over an observed ADMG.",
            graph=_case_graph(["X", "Y", "Z"], [("X", "Z"), ("Z", "Y")]),
            treatments=(),
            outcomes=("Y",),
            expected_identified=1,
            expected_rules=("ID-1",),
            expected_status_contains="identified_no_intervention",
        ),
        FullRecursiveIDKernelCase(
            case_id="kernel_id6_observed_dag_multi_treatment_outcome",
            description="ID-6 observed-DAG truncated factorization with set treatments/outcomes.",
            graph=_case_graph(["X1", "X2", "Y1", "Y2"], [("X1", "Y1"), ("X2", "Y2"), ("Y1", "Y2")]),
            treatments=("X1", "X2"),
            outcomes=("Y1", "Y2"),
            expected_identified=1,
            expected_rules=("ID-6",),
            expected_status_contains="observed_dag",
        ),
        FullRecursiveIDKernelCase(
            case_id="kernel_id4_multidistrict_factorization",
            description="ID-4 multi-district decomposition plus ID-6 subfactors.",
            graph=_case_graph(["X", "Y", "Z", "W"], [("X", "Y"), ("Z", "Y"), ("W", "Z")], [("X", "Z")]),
            treatments=("X",),
            outcomes=("Y",),
            expected_identified=1,
            expected_rules=("ID-4", "ID-6"),
            expected_status_contains="district_decomposition",
        ),
        FullRecursiveIDKernelCase(
            case_id="kernel_id7_classic_frontdoor_carried_q",
            description="ID-7 carried-Q recursion for the classic frontdoor ADMG.",
            graph=_case_graph(["X", "Z", "Y"], [("X", "Z"), ("Z", "Y")], [("X", "Y")]),
            treatments=("X",),
            outcomes=("Y",),
            expected_identified=1,
            expected_rules=("ID-4", "ID-7"),
            expected_status_contains="district_decomposition",
        ),
        FullRecursiveIDKernelCase(
            case_id="kernel_id7_downstream_confounded_chain",
            description="Non-frontdoor downstream-confounded chain with carried-Q recursive trace.",
            graph=_case_graph(["X", "A", "B", "Y"], [("X", "A"), ("A", "B"), ("B", "Y")], [("X", "B")]),
            treatments=("X",),
            outcomes=("Y",),
            expected_identified=1,
            expected_rules=("ID-4", "ID-7"),
            expected_status_contains="district_decomposition",
        ),
        FullRecursiveIDKernelCase(
            case_id="kernel_id7_multi_intervention_carried_q",
            description="Set-valued intervention with carried-Q recursive subproblem.",
            graph=_case_graph(["X1", "X2", "M", "Y"], [("X1", "M"), ("X2", "M"), ("M", "Y")], [("X1", "Y")]),
            treatments=("X1", "X2"),
            outcomes=("Y",),
            expected_identified=1,
            expected_rules=("ID-4", "ID-7"),
            expected_status_contains="district_decomposition",
        ),
        FullRecursiveIDKernelCase(
            case_id="kernel_id5_formal_hedge_fail",
            description="ID-5 formal hedge certificate for non-identifiable graph.",
            graph=_case_graph(["X", "M", "Y"], [("X", "M"), ("M", "Y")], [("X", "Y"), ("M", "Y")]),
            treatments=("X",),
            outcomes=("Y",),
            expected_identified=0,
            expected_nonidentified_certified=1,
            expected_rules=("ID-5",),
            expected_status_contains="formal_hedge",
        ),
    ]


def evaluate_full_recursive_id_kernel_case(case: FullRecursiveIDKernelCase) -> FullRecursiveIDKernelMatrixRow:
    diag = full_recursive_id_kernel_diagnostic(case.graph, case.treatments, case.outcomes).to_dict()
    rules = [r for r in _s(diag.get("applied_rules")).split("|") if r]
    failures: List[str] = []
    identified = int(diag.get("identified", 0) or 0)
    nonidentified_certified = int(diag.get("nonidentified_certified", 0) or 0)
    if identified != int(case.expected_identified):
        failures.append("identified_mismatch")
    if nonidentified_certified != int(case.expected_nonidentified_certified):
        failures.append("nonidentified_certificate_mismatch")
    if not int(diag.get("kernel_completed", 0) or 0):
        failures.append("kernel_not_completed")
    if not int(diag.get("no_pending_kernel_blocker", 0) or 0):
        failures.append("pending_kernel_blocker")
    for expected_rule in case.expected_rules:
        if expected_rule not in rules:
            failures.append(f"missing_rule:{expected_rule}")
    if case.expected_status_contains and case.expected_status_contains not in _s(diag.get("expression_status")):
        failures.append("status_mismatch")
    if identified and not int(diag.get("formula_ast_present", 0) or 0):
        failures.append("identified_missing_formula_ast")
    row = FullRecursiveIDKernelMatrixRow(
        case_id=case.case_id,
        description=case.description,
        passed=int(not failures),
        identified=identified,
        expected_identified=int(case.expected_identified),
        nonidentified_certified=nonidentified_certified,
        expected_nonidentified_certified=int(case.expected_nonidentified_certified),
        expression_status=_s(diag.get("expression_status")),
        expected_status_contains=case.expected_status_contains,
        applied_rules="|".join(rules),
        expected_rules="|".join(case.expected_rules),
        kernel_completed=int(diag.get("kernel_completed", 0) or 0),
        no_pending_kernel_blocker=int(diag.get("no_pending_kernel_blocker", 0) or 0),
        formula_ast_present=int(diag.get("formula_ast_present", 0) or 0),
        carried_q_recursion_used=int(diag.get("carried_q_recursion_used", 0) or 0),
        district_decomposition_used=int(diag.get("district_decomposition_used", 0) or 0),
        q_factor_used=int(diag.get("q_factor_used", 0) or 0),
        observed_dag_used=int(diag.get("observed_dag_used", 0) or 0),
        formal_hedge_certificate_present=int(diag.get("formal_hedge_certificate_present", 0) or 0),
        reason_codes=_s(diag.get("reason_codes")),
        failure="; ".join(failures),
    )
    return row


def run_full_recursive_id_kernel_matrix() -> Dict[str, object]:
    rows = [evaluate_full_recursive_id_kernel_case(c) for c in full_recursive_id_kernel_cases()]
    n_cases = len(rows)
    n_passed = sum(r.passed for r in rows)
    n_identified = sum(r.identified for r in rows)
    n_certified_fail = sum(r.nonidentified_certified for r in rows)
    n_carried_q = sum(r.carried_q_recursion_used for r in rows)
    n_district_decomposition = sum(r.district_decomposition_used for r in rows)
    n_q_factor = sum(r.q_factor_used for r in rows)
    n_observed_dag = sum(r.observed_dag_used for r in rows)
    flags = id_capability_flags()
    return {
        "matrix_version": ID_FULL_RECURSIVE_KERNEL_VERSION,
        "level": ID_FULL_RECURSIVE_KERNEL_LEVEL,
        "all_passed": int(n_cases > 0 and n_passed == n_cases),
        "n_cases": n_cases,
        "n_passed": n_passed,
        "n_identified": n_identified,
        "n_nonidentified_certified": n_certified_fail,
        "n_carried_q_recursion_used": n_carried_q,
        "n_district_decomposition_used": n_district_decomposition,
        "n_q_factor_used": n_q_factor,
        "n_observed_dag_used": n_observed_dag,
        "kernel_authority": ID_FULL_RECURSIVE_KERNEL_AUTHORITY,
        "full_recursive_id_kernel_step91_implemented": 1,
        "global_full_recursive_id_implemented": int(_truthy(flags.get("full_recursive_id_implemented"))),
        "global_full_id_claim_allowed": int(_truthy(flags.get("full_id_claim_allowed"))),
        "global_claim_still_blocked": int(not _truthy(flags.get("full_id_claim_allowed"))),
        "promotion_note": "kernel_backend_ready_for_broader_oracle_expansion_but_global_full_id_claim_not_flipped_step91",
        "rows": [r.to_dict() for r in rows],
    }


__all__ = [
    "ID_FULL_RECURSIVE_KERNEL_VERSION",
    "ID_FULL_RECURSIVE_KERNEL_LEVEL",
    "ID_FULL_RECURSIVE_KERNEL_AUTHORITY",
    "FullRecursiveIDKernelDiagnostic",
    "FullRecursiveIDKernelCase",
    "FullRecursiveIDKernelMatrixRow",
    "full_recursive_id_kernel_diagnostic",
    "full_recursive_id_kernel_cases",
    "evaluate_full_recursive_id_kernel_case",
    "run_full_recursive_id_kernel_matrix",
]
