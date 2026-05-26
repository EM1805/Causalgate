from __future__ import annotations

"""Formal hedge detection helpers for SCM ID.

This module is intentionally narrow and audit-first.  It tries to certify the
standard ID failure witness shape without estimating anything:

    two C-forests F and F' such that F' is a strict subset of F,
    F intersects the intervention set X, F' is disjoint from X, F' contains
    or ancestrally supports the outcome query, and F/F' share exactly the same
    roots.

When the checks are not all satisfied the result is explicit ``not_certified``;
callers must never treat a non-certificate as identification.
"""

from dataclasses import asdict, dataclass
from itertools import combinations
from typing import Dict, Iterable, List, Mapping, Sequence, Set, Tuple

from .admg import ADMG
from .id_algorithm_common import _dedupe, _format_component, _format_components, _json_formula, _s


def _roots_in_subgraph(admg: ADMG, nodes: Sequence[str]) -> List[str]:
    keep = set(_dedupe(nodes))
    children = admg.children()
    roots: List[str] = []
    for n in sorted(keep):
        if not (children.get(n, set()) & keep):
            roots.append(n)
    return roots


def _is_c_forest(admg: ADMG, nodes: Sequence[str]) -> Tuple[bool, List[str], str]:
    """Conservative C-forest check: one bidirected district, <=1 child/node."""
    keep = sorted(_dedupe(nodes))
    if not keep:
        return False, [], "EMPTY_NODE_SET"
    sub = admg.induced_subgraph(keep)
    districts = sub.districts()
    if len(districts) != 1:
        return False, _roots_in_subgraph(sub, keep), "NOT_SINGLE_C_COMPONENT"
    children = sub.children()
    multi_child = [n for n in keep if len(children.get(n, set()) & set(keep)) > 1]
    if multi_child:
        return False, _roots_in_subgraph(sub, keep), "NOT_FOREST_NODE_HAS_MULTIPLE_CHILDREN"
    roots = _roots_in_subgraph(sub, keep)
    if not roots:
        return False, [], "NO_ROOTS_FOUND"
    return True, roots, "C_FOREST_OK"


@dataclass(frozen=True)
class FormalHedgeDiagnostic:
    formal_hedge_status: str
    formal_hedge_certified: bool = False
    hedge_F: str = ""
    hedge_F_prime: str = ""
    hedge_roots_F: str = ""
    hedge_roots_F_prime: str = ""
    hedge_treatment_in_F_minus_F_prime: str = ""
    hedge_outcome_witness: str = ""
    hedge_graph_without_treatment_nodes: str = ""
    hedge_checks_json: str = ""
    hedge_certificate_json: str = ""
    hedge_reason_codes: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def formal_hedge_diagnostic(admg: ADMG, treatments: Iterable[object], outcomes: Iterable[object]) -> FormalHedgeDiagnostic:
    """Return a formal hedge certificate when the limited auditable shape holds.

    The search is deterministic and intentionally small:
    1. restrict to ancestors of the outcomes;
    2. use full C-components in that graph as possible ``F``;
    3. use districts in ``G[V\\X]`` as possible ``F'``;
    4. require both sets to satisfy the conservative C-forest check and share
       exactly the same roots.  Outcome-ancestor support is retained only as an
       audit field; it is not sufficient for a formal hedge certificate.
    """
    x = set(_dedupe(treatments))
    y = set(_dedupe(outcomes))
    if not x or not y or not x.issubset(admg.node_set) or not y.issubset(admg.node_set):
        return FormalHedgeDiagnostic("invalid_query", False, hedge_reason_codes="MISSING_QUERY_NODE")
    if not admg.bidirected_edges:
        return FormalHedgeDiagnostic("not_applicable_no_bidirected_edges", False, hedge_reason_codes="NO_BIDIRECTED_EDGES")

    ancestral_nodes = sorted(admg.ancestors(y))
    ancestral = admg.induced_subgraph(ancestral_nodes)
    gx = ancestral.induced_subgraph(sorted(set(ancestral.nodes) - x))
    outcome_support = set(ancestral.ancestors(y))

    def _maybe_add_candidate(
        *,
        f_set: Set[str],
        fp_set: Set[str],
        f_roots: List[str],
        fp_roots: List[str],
        f_reason: str,
        fp_reason: str,
        search_scope: str,
    ) -> Mapping[str, object] | None:
        if not (f_set & x):
            return None
        if not fp_set < f_set:
            return None
        if fp_set & x:
            return None
        if not fp_set.issubset(set(gx.nodes)):
            return None
        if not (fp_set & outcome_support):
            return None
        same_roots = set(f_roots) == set(fp_roots)
        roots_supported = set(fp_roots).issubset(outcome_support) and bool(set(fp_roots) & outcome_support)
        checks = {
            "F_is_c_forest": True,
            "F_prime_is_c_forest": True,
            "F_prime_strict_subset_of_F": fp_set < f_set,
            "F_intersects_treatment": bool(f_set & x),
            "F_prime_disjoint_from_treatment": not bool(fp_set & x),
            "F_prime_in_G_without_X": True,
            "same_roots": same_roots,
            "roots_supported_by_outcome_ancestry": roots_supported,
            "F_reason": f_reason,
            "F_prime_reason": fp_reason,
            "search_scope": search_scope,
            "step84_subforest_hedge_search": int(search_scope == "audited_subforest_step84"),
        }
        # Pearl/Shpitser hedge certificates require the two C-forests to have
        # the same roots.  Outcome ancestry support is recorded for audit, but
        # it is not sufficient on its own.
        if not same_roots:
            return None
        return {
            "F": sorted(f_set),
            "F_prime": sorted(fp_set),
            "roots_F": f_roots,
            "roots_F_prime": fp_roots,
            "treatment_in_F_minus_F_prime": sorted(x & (f_set - fp_set)),
            "outcome_witness": sorted(y & outcome_support),
            "graph_without_treatment_nodes": sorted(gx.nodes),
            "ancestral_nodes": ancestral_nodes,
            "checks": checks,
            "reason_codes": "FORMAL_HEDGE_CERTIFIED_STEP38" + (";SUBFOREST_HEDGE_CERTIFIED_STEP84" if search_scope == "audited_subforest_step84" else ""),
        }

    def _prefer(candidate: Mapping[str, object], current: Mapping[str, object] | None) -> Mapping[str, object]:
        if current is None:
            return candidate
        # Preserve earlier district-level certificates when they exist.  Only
        # the Step-84 subforest fallback should fill gaps left by the original
        # district-based search, which keeps legacy direct-confounding witnesses stable.
        cand_key = (len(candidate["F"]), len(candidate["F_prime"]), candidate["F"])
        cur_key = (len(current["F"]), len(current["F_prime"]), current["F"])
        return candidate if cand_key < cur_key else current

    best: Mapping[str, object] | None = None
    for f in ancestral.districts():
        f_set = set(f)
        f_ok, f_roots, f_reason = _is_c_forest(ancestral, f)
        if not f_ok:
            continue
        for fp in gx.districts():
            fp_set = set(fp)
            fp_ok, fp_roots, fp_reason = _is_c_forest(ancestral, fp)
            if not fp_ok:
                continue
            candidate = _maybe_add_candidate(
                f_set=f_set,
                fp_set=fp_set,
                f_roots=f_roots,
                fp_roots=fp_roots,
                f_reason=f_reason,
                fp_reason=fp_reason,
                search_scope="ancestral_district_step38",
            )
            if candidate is not None:
                best = _prefer(candidate, best)

    if best is None and len(ancestral_nodes) <= 8:
        # Step 84: fallback to an audited finite subforest search.  The original
        # Step-38/68 detector only considered full ancestral districts as F and
        # districts of G[V\X] as F'.  That misses valid hedge witnesses where a
        # strict C-subforest inside a larger district is the certificate.  This
        # finite search is still conservative: both F and F' must be C-forests,
        # F' must live in G[V\X], F' must be a strict subset of F, and the two
        # forests must share exactly the same roots.
        candidates = sorted(ancestral_nodes)
        gx_nodes = set(gx.nodes)
        for size_f in range(2, len(candidates) + 1):
            for f_tuple in combinations(candidates, size_f):
                f_set = set(f_tuple)
                if not (f_set & x):
                    continue
                f_ok, f_roots, f_reason = _is_c_forest(ancestral, f_tuple)
                if not f_ok:
                    continue
                fp_pool = sorted(f_set & gx_nodes)
                for size_fp in range(1, len(fp_pool) + 1):
                    for fp_tuple in combinations(fp_pool, size_fp):
                        fp_set = set(fp_tuple)
                        fp_ok, fp_roots, fp_reason = _is_c_forest(gx, fp_tuple)
                        if not fp_ok:
                            continue
                        candidate = _maybe_add_candidate(
                            f_set=f_set,
                            fp_set=fp_set,
                            f_roots=f_roots,
                            fp_roots=fp_roots,
                            f_reason=f_reason,
                            fp_reason=fp_reason,
                            search_scope="audited_subforest_step84",
                        )
                        if candidate is not None:
                            best = _prefer(candidate, best)

    if best is None:
        return FormalHedgeDiagnostic(
            "not_certified",
            False,
            hedge_graph_without_treatment_nodes="|".join(sorted(gx.nodes)),
            hedge_checks_json=_json_formula({"ancestral_nodes": ancestral_nodes, "ancestral_districts": ancestral.districts(), "districts_without_treatment": gx.districts()}),
            hedge_reason_codes="NO_FORMAL_HEDGE_CERTIFICATE_FOUND",
        )

    return FormalHedgeDiagnostic(
        "formal_hedge_certified",
        True,
        hedge_F=_format_component(best["F"]),
        hedge_F_prime=_format_component(best["F_prime"]),
        hedge_roots_F="|".join(best["roots_F"]),
        hedge_roots_F_prime="|".join(best["roots_F_prime"]),
        hedge_treatment_in_F_minus_F_prime="|".join(best["treatment_in_F_minus_F_prime"]),
        hedge_outcome_witness="|".join(best["outcome_witness"]),
        hedge_graph_without_treatment_nodes="|".join(best["graph_without_treatment_nodes"]),
        hedge_checks_json=_json_formula(best["checks"]),
        hedge_certificate_json=_json_formula(best),
        hedge_reason_codes=_s(best.get("reason_codes")) or "FORMAL_HEDGE_CERTIFIED_STEP38",
    )
