from causalgate.scientific.diagnostic_attention import apply_diagnostic_attention_to_dialogue_result
from causalgate.mcp.tools import call_tool


def test_diagnostic_attention_postprocessor_surfaces_sensitivity_required_tests():
    result = {
        "status": "FINAL_CANDIDATE",
        "final_decision": "FINAL_CANDIDATE",
        "next_instruction": "old",
        "metadata": {},
        "final_verdict": {
            "decision": "FINAL_CANDIDATE",
            "reason": "The hypothesis is acceptable only as a testable scientific candidate, not as a confirmed law.",
            "reason_codes": ["ESTIMATION_AVAILABLE"],
            "required_tests": [],
            "overclaim_risk": "low",
            "estimation": {
                "estimated": True,
                "estimation_status": "loaded_manual_effect",
                "effect_estimate": 0.4,
                "robustness_status": "computed_basic_synthetic_robustness_attention_required",
                "negative_control_status": "computed_passed",
                "placebo_status": "computed_passed",
                "sensitivity_status": "computed_attention_required",
                "estimation_diagnostics": {
                    "diagnostics_status": "computed_attention_required",
                    "sensitivity": {"tested": True, "passed": False},
                    "reason_codes": ["SENSITIVITY_CHECK_ATTENTION_REQUIRED"],
                },
            },
            "audit_payload": {
                "reason_codes": ["ESTIMATION_AVAILABLE"],
                "estimation": {"estimation_status": "loaded_manual_effect"},
            },
            "short_for_llm": {"reason": "old", "next_instruction": "old", "overclaim_risk": "low"},
        },
        "turns": [
            {
                "step": 1,
                "actor": "causalgate",
                "status": "FINAL_CANDIDATE",
                "verdict": {
                    "decision": "FINAL_CANDIDATE",
                    "reason": "candidate",
                    "reason_codes": [],
                    "required_tests": [],
                    "overclaim_risk": "low",
                    "estimation": {
                        "estimated": True,
                        "estimation_status": "loaded_manual_effect",
                        "sensitivity_status": "computed_attention_required",
                    },
                },
            }
        ],
    }

    patched = apply_diagnostic_attention_to_dialogue_result(result)

    assert patched["status"] == "FINAL_CANDIDATE_DIAGNOSTIC_ATTENTION"
    assert patched["final_decision"] == "FINAL_CANDIDATE_DIAGNOSTIC_ATTENTION"
    assert patched["diagnostic_attention_status"] == "attention_required"
    assert patched["metadata"]["diagnostic_attention_status"] == "attention_required"
    assert patched["final_verdict"]["diagnostic_attention_status"] == "attention_required"
    assert "ESTIMATION_DIAGNOSTICS_ATTENTION_REQUIRED" in patched["final_verdict"]["reason_codes"]
    assert "SENSITIVITY_CHECK_ATTENTION_REQUIRED" in patched["final_verdict"]["reason_codes"]
    assert "investigate_sensitivity_failure_before_claim_upgrade" in patched["final_verdict"]["required_tests"]
    assert "compare_effect_across_sensitivity_strata" in patched["final_verdict"]["required_tests"]
    assert patched["final_verdict"]["overclaim_risk"] == "medium"
    assert patched["final_verdict"]["estimation"]["diagnostic_attention_status"] == "attention_required"
    assert patched["final_verdict"]["audit_payload"]["diagnostic_attention_status"] == "attention_required"
    assert patched["final_verdict"]["short_for_llm"]["diagnostic_attention_status"] == "attention_required"
    assert patched["turns"][0]["status"] == "FINAL_CANDIDATE_DIAGNOSTIC_ATTENTION"


def test_native_physics_tool_surfaces_diagnostic_attention_when_sensitivity_fails():
    result = call_tool("causalgate_run_native_json_hypothesis", {
        "goal": "stellar metallicity -> gravitational-wave waveform residual in accretion disk models using calibrated survey selection functions",
        "max_steps": 6,
        "enable_identification": True,
        "auto_expand": True,
        "agent_repair": True,
        "output_format": "json_only",
    })

    assert result["final_verdict"]["estimation"]["estimation_status"] == "loaded_manual_effect"
    assert result["final_verdict"]["estimation"]["sensitivity_status"] == "computed_attention_required"
    assert result["diagnostic_attention_status"] == "attention_required"
    assert result["final_decision"] == "FINAL_CANDIDATE_DIAGNOSTIC_ATTENTION"
    assert "ESTIMATION_DIAGNOSTICS_ATTENTION_REQUIRED" in result["final_verdict"]["reason_codes"]
    assert "investigate_sensitivity_failure_before_claim_upgrade" in result["final_verdict"]["required_tests"]
    assert result["metadata"]["diagnostic_attention_status"] == "attention_required"
