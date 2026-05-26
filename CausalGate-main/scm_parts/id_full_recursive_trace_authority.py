from __future__ import annotations

"""Step 86 recursive trace formula-authority certificates.

This module does not implement arbitrary Shpitser/Pearl ID and does not raise
``full_id_claim_allowed``.  It adds the missing middle layer between finite
formula templates and global Full-ID promotion: every currently identified public
formula can carry a machine-checkable recursive-ID trace certificate when its
output has:

- an identified formula and normalized formula AST;
- non-raw formula authority from the current public surface;
- a canonical ID-1..ID-7 rule trace/control payload;
- no runtime Full-ID claim flag.

The certificate is deliberately scoped to the audited public corpus.  The global
promotion gate still requires the backend capability flags before any Pearl-
complete wording can be enabled.
"""

from dataclasses import asdict, dataclass
import json
from typing import Dict, Iterable, Mapping, Sequence

from .id_algorithm_common import _s

ID_FULL_RECURSIVE_TRACE_AUTHORITY_VERSION = "id_full_recursive_trace_authority_v1_step86"
ID_FULL_RECURSIVE_TRACE_AUTHORITY_LEVEL = (
    "audited_public_formula_recursive_id_trace_certificate_for_ID_1_to_ID_7_"
    "formula_authority_coverage_no_global_full_id_claim_step86"
)
FULL_RECURSIVE_TRACE_FORMULA_AUTHORITY = "full_recursive_id_trace_formula_authority_step86"

RAW_DELEGATED_FORMULA_AUTHORITY = "recursive_id_set_expression_diagnostic"
FAILURE_FORMULA_AUTHORITY = "id_failure_certificate_step68"
KNOWN_ID_RULES = {"ID-1", "ID-2", "ID-3", "ID-4", "ID-5", "ID-6", "ID-7"}


@dataclass(frozen=True)
class RecursiveTraceAuthorityDiagnostic:
    trace_authority_version: str
    trace_authority_level: str
    certified: int
    authority: str
    status: str
    rules: str
    terminal_rule: str = ""
    terminal_status: str = ""
    evidence_source: str = ""
    blocker: str = ""
    full_id_claim_allowed: int = 0

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "pass", "passed", "green", "complete"}


def _json_payload(raw: object) -> Dict[str, object]:
    if isinstance(raw, Mapping):
        return dict(raw)
    text = _s(raw)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _rules_from_text(value: object) -> Sequence[str]:
    text = _s(value)
    return tuple(rule for rule in text.split("|") if rule)


def _rules_from_control(payload: Mapping[str, object]) -> Sequence[str]:
    raw = payload.get("applied_rules")
    if isinstance(raw, str):
        return tuple(rule for rule in raw.split("|") if rule)
    if isinstance(raw, Iterable):
        return tuple(_s(rule) for rule in raw if _s(rule))
    return ()


def _trace_rules(result: Mapping[str, object]) -> tuple[Sequence[str], str]:
    trace = _json_payload(result.get("trace_json"))
    steps = trace.get("trace") if isinstance(trace, Mapping) else None
    if not isinstance(steps, list) or not steps:
        return (), ""
    names = []
    terminal_status = ""
    mapping = {
        "id_base_no_intervention": "ID-1",
        "no_intervention": "ID-1",
        "ancestor_reduction": "ID-2",
        "irrelevant_after_intervention_w_step": "ID-3",
        "w_step_irrelevant_interventions": "ID-3",
        "district_decomposition_g_v_minus_x": "ID-4",
        "formal_hedge_certificate": "ID-5",
        "q_factor_full_district": "ID-6",
        "observed_dag_truncated_factorization": "ID-6",
        "graphical_zero_effect": "ID-6",
        "q_input_subdistrict_recursion": "ID-7",
        "q_input_general_recursion_step44": "ID-7",
        "q_input_general_carried_q_recursion_step51": "ID-7",
    }
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        status = _s(step.get("status"))
        if status.startswith("blocked"):
            return (), status
        rule = _s(step.get("rule")) if _s(step.get("rule")) in KNOWN_ID_RULES else mapping.get(_s(step.get("step")))
        if rule and rule not in names:
            names.append(rule)
        if status.startswith("identified") or status in {"applied", "terminal_no_intervention", "terminal_observed_dag_truncated_factorization", "terminal_q_factor_full_district"}:
            terminal_status = status
    return tuple(names), terminal_status


def _control_certifies(result: Mapping[str, object]) -> tuple[int, str, str, str, str]:
    control = _json_payload(result.get("canonical_control_json"))
    trace_rules, trace_terminal_status = _trace_rules(result)
    if control:
        status = _s(control.get("status"))
        terminal_rule = _s(control.get("terminal_rule"))
        terminal_status = _s(control.get("terminal_status")) or trace_terminal_status
        rules = list(_rules_from_control(control))
        for rule in trace_rules:
            if rule not in rules:
                rules.append(rule)
        if status and not status.startswith("blocked") and not status.startswith("invalid") and terminal_rule in KNOWN_ID_RULES and rules:
            return 1, "|".join(rules), terminal_rule, terminal_status, "canonical_control_json+trace_json"
    if trace_rules:
        return 1, "|".join(trace_rules), trace_rules[-1], trace_terminal_status, "trace_json"
    if trace_terminal_status.startswith("blocked"):
        return 0, "", "", trace_terminal_status, "trace_json"
    return 0, "", "", "", ""


def recursive_trace_authority_for_result(result: Mapping[str, object], *, query_kind: str = "id") -> RecursiveTraceAuthorityDiagnostic:
    """Return a scoped Step-86 recursive trace certificate for an identified result.

    For IDC rows, the actual ID authority lives on the identified joint query;
    the outer IDC ratio is only a normalization step.  In that case this helper
    certifies the embedded ``joint_full_id_json`` while preserving the outer
    result's no-claim invariant.
    """
    row = dict(result or {})
    if query_kind == "idc":
        joint = _json_payload(row.get("joint_full_id_json"))
        if not joint:
            return _blocked("missing_joint_full_id_json_for_idc_trace_authority")
        if not _truthy(row.get("identified")) or not _s(row.get("formula")):
            return _blocked("idc_outer_formula_missing_or_not_identified")
        row = joint

    identified = _truthy(row.get("identified"))
    formula = _s(row.get("formula"))
    ast = _s(row.get("formula_ast_json"))
    primary = _s(row.get("primary_formula_authority"))
    claim = int(row.get("full_id_claim_allowed") or 0)
    if not identified:
        return _blocked("result_not_identified")
    if not formula:
        return _blocked("missing_identified_formula")
    if not ast:
        return _blocked("missing_formula_ast_json")
    if primary in {"", RAW_DELEGATED_FORMULA_AUTHORITY, FAILURE_FORMULA_AUTHORITY}:
        return _blocked("missing_or_raw_or_failure_formula_authority")
    if claim not in (0, 1):
        return _blocked("invalid_full_id_claim_flag_inside_trace_certificate", claim=claim)

    rules = _rules_from_text(row.get("canonical_rules"))
    if not rules:
        return _blocked("missing_canonical_id_rules")
    if any(rule not in KNOWN_ID_RULES for rule in rules):
        return _blocked("unknown_canonical_id_rule")
    ok, control_rules, terminal_rule, terminal_status, source = _control_certifies(row)
    if not ok:
        return _blocked("missing_or_blocked_recursive_control_trace")
    # The public canonical_rules field and control payload must be compatible.
    # We allow the control payload to be more detailed than the compact field.
    control_set = set(_rules_from_text(control_rules))
    missing_rules = set(rules) - control_set
    if missing_rules:
        graphical_zero_id6 = missing_rules == {"ID-6"} and _s(row.get("identification_status")) == "identified_graphical_zero_effect"
        if not graphical_zero_id6:
            return _blocked("canonical_rules_not_covered_by_control_trace")
    return RecursiveTraceAuthorityDiagnostic(
        trace_authority_version=ID_FULL_RECURSIVE_TRACE_AUTHORITY_VERSION,
        trace_authority_level=ID_FULL_RECURSIVE_TRACE_AUTHORITY_LEVEL,
        certified=1,
        authority=FULL_RECURSIVE_TRACE_FORMULA_AUTHORITY,
        status="full_recursive_trace_certified_step86",
        rules="|".join(rules),
        terminal_rule=terminal_rule,
        terminal_status=terminal_status,
        evidence_source=source,
        full_id_claim_allowed=claim,
    )


def _blocked(reason: str, *, claim: int = 0) -> RecursiveTraceAuthorityDiagnostic:
    return RecursiveTraceAuthorityDiagnostic(
        trace_authority_version=ID_FULL_RECURSIVE_TRACE_AUTHORITY_VERSION,
        trace_authority_level=ID_FULL_RECURSIVE_TRACE_AUTHORITY_LEVEL,
        certified=0,
        authority="",
        status="trace_authority_blocked_step86",
        rules="",
        blocker=reason,
        full_id_claim_allowed=int(claim),
    )


__all__ = [
    "ID_FULL_RECURSIVE_TRACE_AUTHORITY_VERSION",
    "ID_FULL_RECURSIVE_TRACE_AUTHORITY_LEVEL",
    "FULL_RECURSIVE_TRACE_FORMULA_AUTHORITY",
    "RecursiveTraceAuthorityDiagnostic",
    "recursive_trace_authority_for_result",
]
