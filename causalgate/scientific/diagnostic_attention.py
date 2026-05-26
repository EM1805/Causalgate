from __future__ import annotations

"""Post-process verdicts when estimation diagnostics require attention.

The scientific veto can accept a hypothesis as a candidate while estimation
sub-diagnostics still flag sensitivity, robustness, placebo, or negative-control
issues.  This module keeps that distinction explicit in JSON outputs: candidate
status is preserved, but the verdict carries diagnostic reason codes and required
follow-up tests.
"""

from typing import Any, Dict, List, Mapping


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _append_unique(values: Any, additions: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in [*_as_list(values), *additions]:
        text = _clean_str(value)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _attention_codes_and_tests(estimation: Mapping[str, Any]) -> tuple[List[str], List[str]]:
    est = _as_dict(estimation)
    diagnostics = _as_dict(est.get("estimation_diagnostics")) or _as_dict(est.get("raw_estimation_result")).get("estimation_diagnostics", {})
    codes: List[str] = []
    tests: List[str] = []

    status_pairs = [
        ("robustness_status", "ROBUSTNESS_CHECK_ATTENTION_REQUIRED", "rerun_with_alternate_calibration_noise_or_outlier_rules"),
        ("negative_control_status", "NEGATIVE_CONTROL_ATTENTION_REQUIRED", "investigate_negative_control_signal_before_claim_upgrade"),
        ("placebo_status", "PLACEBO_TEST_ATTENTION_REQUIRED", "rerun_placebo_or_label_shuffle_test_before_claim_upgrade"),
        ("sensitivity_status", "SENSITIVITY_CHECK_ATTENTION_REQUIRED", "investigate_sensitivity_failure_before_claim_upgrade"),
    ]
    for key, code, test in status_pairs:
        status = _clean_str(est.get(key) or diagnostics.get(key)).lower()
        if "attention_required" in status or "failed" in status:
            codes.append(code)
            tests.append(test)

    diag_status = _clean_str(diagnostics.get("diagnostics_status") or est.get("diagnostics_status")).lower()
    if "attention_required" in diag_status:
        codes.append("ESTIMATION_DIAGNOSTICS_ATTENTION_REQUIRED")
        tests.append("review_estimation_diagnostics_before_claim_upgrade")

    sensitivity = _as_dict(diagnostics.get("sensitivity"))
    if sensitivity and sensitivity.get("tested") and sensitivity.get("passed") is False:
        codes.append("SENSITIVITY_CHECK_ATTENTION_REQUIRED")
        tests.extend([
            "compare_effect_across_sensitivity_strata",
            "rerun_with_alternate_noise_model",
            "do_not_upgrade_claim_until_sensitivity_passes_or_is_explained",
        ])

    for source_code in _as_list(diagnostics.get("reason_codes")):
        text = _clean_str(source_code)
        if text.endswith("ATTENTION_REQUIRED"):
            codes.append(text)

    if codes:
        codes.insert(0, "ESTIMATION_DIAGNOSTICS_ATTENTION_REQUIRED")
    return _append_unique([], codes), _append_unique([], tests)


def _patch_verdict(verdict: Mapping[str, Any]) -> tuple[Dict[str, Any], bool]:
    patched = _as_dict(verdict)
    if not patched:
        return patched, False
    estimation = _as_dict(patched.get("estimation"))
    codes, tests = _attention_codes_and_tests(estimation)
    if not codes:
        return patched, False

    patched["diagnostic_attention_status"] = "attention_required"
    patched["reason_codes"] = _append_unique(patched.get("reason_codes"), codes)
    patched["required_tests"] = _append_unique(patched.get("required_tests"), tests)
    if _clean_str(patched.get("overclaim_risk"), "low") == "low":
        patched["overclaim_risk"] = "medium"

    base_reason = _clean_str(patched.get("reason"))
    diagnostic_reason = "Estimation diagnostics require attention before any claim upgrade."
    if diagnostic_reason not in base_reason:
        patched["reason"] = (base_reason + " " + diagnostic_reason).strip()

    patched["next_instruction"] = (
        "Keep the hypothesis at candidate level; investigate diagnostic attention items, especially sensitivity/robustness, "
        "and replace synthetic demo diagnostics with real measurements or validated simulations before any stronger conclusion."
    )

    audit = _as_dict(patched.get("audit_payload"))
    if audit:
        audit["reason_codes"] = _append_unique(audit.get("reason_codes"), codes)
        audit["required_tests"] = _append_unique(audit.get("required_tests"), tests)
        audit["diagnostic_attention_status"] = "attention_required"
        audit_estimation = _as_dict(audit.get("estimation"))
        if audit_estimation:
            audit_estimation["diagnostic_attention_status"] = "attention_required"
            audit["estimation"] = audit_estimation
        patched["audit_payload"] = audit

    short = _as_dict(patched.get("short_for_llm"))
    if short:
        short["overclaim_risk"] = patched.get("overclaim_risk", short.get("overclaim_risk"))
        short["reason"] = patched["reason"]
        short["next_instruction"] = patched["next_instruction"]
        short["diagnostic_attention_status"] = "attention_required"
        patched["short_for_llm"] = short

    estimation["diagnostic_attention_status"] = "attention_required"
    patched["estimation"] = estimation
    return patched, True


def apply_diagnostic_attention_to_dialogue_result(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a copy of a dialogue result with diagnostic attention surfaced.

    The function is intentionally conservative: it does not fabricate additional
    estimates and it does not mark a candidate as confirmed.  It only surfaces
    already-computed diagnostic attention flags in the final/turn verdicts and
    metadata so downstream UI can display them.
    """

    data = dict(result)
    applied = 0

    for key in ("initial_verdict", "final_verdict"):
        verdict, changed = _patch_verdict(_as_dict(data.get(key)))
        if changed:
            applied += 1
            data[key] = verdict

    turns: List[Dict[str, Any]] = []
    for turn in _as_list(data.get("turns")):
        turn_dict = _as_dict(turn)
        verdict, changed = _patch_verdict(_as_dict(turn_dict.get("verdict")))
        if changed:
            applied += 1
            turn_dict["verdict"] = verdict
            if turn_dict.get("status") == "FINAL_CANDIDATE":
                turn_dict["status"] = "FINAL_CANDIDATE_DIAGNOSTIC_ATTENTION"
            turn_dict["next_instruction"] = verdict.get("next_instruction", turn_dict.get("next_instruction", ""))
        turns.append(turn_dict)
    if turns:
        data["turns"] = turns

    final_verdict = _as_dict(data.get("final_verdict"))
    if final_verdict.get("diagnostic_attention_status") == "attention_required":
        data["diagnostic_attention_status"] = "attention_required"
        if data.get("status") == "FINAL_CANDIDATE":
            data["status"] = "FINAL_CANDIDATE_DIAGNOSTIC_ATTENTION"
        if data.get("final_decision") == "FINAL_CANDIDATE":
            data["final_decision"] = "FINAL_CANDIDATE_DIAGNOSTIC_ATTENTION"
        data["next_instruction"] = final_verdict.get("next_instruction", data.get("next_instruction", ""))

    metadata = _as_dict(data.get("metadata"))
    metadata["diagnostic_attention_postprocess_applied"] = applied
    if final_verdict.get("diagnostic_attention_status") == "attention_required":
        metadata["diagnostic_attention_status"] = "attention_required"
    data["metadata"] = metadata
    return data


__all__ = ["apply_diagnostic_attention_to_dialogue_result"]
