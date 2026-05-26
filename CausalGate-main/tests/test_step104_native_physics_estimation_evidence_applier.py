from causalgate.integrations.gemini_dialogue_adapter import run_native_json_hypothesis_dialogue


def test_native_physics_adds_synthetic_estimation_when_missing_evidence():
    result = run_native_json_hypothesis_dialogue({
        "goal": "magnetic field strength -> photon-count correlation in superconducting qubit devices with simulation-backed parameter sweeps",
        "max_steps": 6,
        "enable_identification": True,
        "auto_expand": True,
        "agent_repair": True,
        "output_format": "json_only",
    })

    assert result["metadata"]["estimation_revisions_applied"] == 1
    assert any(turn["actor"] == "causalgate_estimation_evidence_applier" for turn in result["turns"])

    final_hypothesis = result["final_hypothesis"]
    metadata = final_hypothesis["metadata"]
    final_estimation = result["final_verdict"]["estimation"]

    assert final_hypothesis["domain"] == "mechanistic_physics"
    assert metadata["synthetic_demo_estimation"] is True
    assert metadata["estimation_diagnostics_computed"] is True
    assert "synthetic_demo_estimation_diagnostics" in metadata["agent_applied_estimation_revisions"]
    assert metadata["estimation_diagnostics"]["negative_control"]["tested"] is True
    assert metadata["estimation_diagnostics"]["placebo"]["tested"] is True
    assert metadata["estimation_diagnostics"]["sensitivity"]["tested"] is True
    assert metadata["negative_control_status"].startswith("computed_")
    assert metadata["placebo_status"].startswith("computed_")
    assert metadata["sensitivity_status"].startswith("computed_")

    assert final_estimation["estimated"] is True
    assert final_estimation["estimation_status"] == "loaded_manual_effect"
    assert final_estimation["effect_estimate"] is not None
    assert final_estimation["negative_control_status"].startswith("computed_")
    assert final_estimation["placebo_status"].startswith("computed_")
    assert final_estimation["sensitivity_status"].startswith("computed_")


def test_native_math_does_not_get_synthetic_estimation_evidence():
    result = run_native_json_hypothesis_dialogue({
        "goal": "mathematical conjecture: bounded curvature implication for finite triangulations",
        "max_steps": 4,
        "enable_identification": True,
        "auto_expand": True,
        "agent_repair": True,
        "output_format": "json_only",
    })

    assert result["final_hypothesis"]["domain"] == "mathematical"
    assert result["metadata"].get("estimation_revisions_applied", 0) == 0
    assert result["final_verdict"]["estimation"]["estimation_status"] == "not_applicable_mathematical_conjecture"
    assert not result["final_hypothesis"].get("metadata", {}).get("synthetic_demo_estimation")
