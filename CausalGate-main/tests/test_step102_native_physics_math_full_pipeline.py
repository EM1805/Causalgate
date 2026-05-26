from causalgate.integrations.gemini_dialogue_adapter import run_native_json_hypothesis_dialogue


def test_native_math_candidate_passes_through_full_pipeline_with_not_applicable_id_estimation():
    result = run_native_json_hypothesis_dialogue({
        "goal": "mathematical conjecture: bounded curvature implication for finite triangulations",
        "max_steps": 3,
        "enable_identification": True,
        "auto_expand": True,
        "agent_repair": True,
        "output_format": "json_only",
    })

    assert result["final_verdict"]["decision"] == "FINAL_CANDIDATE"
    assert result["final_hypothesis"]["domain"] == "mathematical"
    assert result["final_hypothesis"]["verification_protocol"]["type"] == "proof_or_counterexample"
    assert result["final_verdict"]["identification"]["not_applicable"] is True
    assert result["final_verdict"]["estimation"]["estimated"] is False
    assert result["final_verdict"]["estimation"]["estimation_status"] == "not_applicable_mathematical_conjecture"
    assert result["metadata"]["native_hypothesis_agent"] is True
    assert result["metadata"]["output_format"] == "json_only"


def test_native_physics_candidate_passes_through_veto_identification_and_estimation_fields():
    result = run_native_json_hypothesis_dialogue({
        "goal": "laser detuning -> resonance linewidth in cryogenic optical cavity setups under controlled laboratory boundary conditions",
        "max_steps": 4,
        "enable_identification": True,
        "auto_expand": True,
        "agent_repair": True,
        "output_format": "json_only",
    })

    assert result["final_hypothesis"]["domain"] == "mechanistic_physics"
    assert result["final_verdict"]["decision"] in {"FINAL_CANDIDATE", "TEST_MORE", "REVISE"}
    assert "identification" in result["final_verdict"]
    assert "estimation" in result["final_verdict"]
    assert "falsification" in result["final_verdict"]["audit_payload"]
    assert result["final_verdict"]["identification"]["reason_codes"]
    assert result["final_verdict"]["estimation"]["estimation_status"]
    assert result["final_hypothesis"]["negative_control_tests"]
    assert result["final_hypothesis"]["placebo_tests"]
    assert result["final_hypothesis"]["sensitivity_checks"]
    assert result["metadata"]["native_hypothesis_agent"] is True
    assert result["metadata"]["output_format"] == "json_only"
