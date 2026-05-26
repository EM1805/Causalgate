import json

from causalgate.integrations.gemini_dialogue_adapter import (
    GeminiDialogueAdapter,
    GeminiDialogueAdapterConfig,
    GeminiGoalNormalizer,
    GeminiLanguageRenderer,
    build_gemini_dialogue_prompt,
    build_gemini_goal_normalization_prompt,
    build_gemini_language_render_prompt,
    run_gemini_llm_dialogue,
)
from causalgate.mcp.tools import call_tool, list_tools
from causalgate.scientific.hypothesis_discovery_agent import generate_hypothesis


def test_gemini_named_dialogue_uses_native_json_without_config(monkeypatch):
    monkeypatch.delenv("CAUSALGATE_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("CAUSALGATE_GEMINI_MODEL", raising=False)

    result = run_gemini_llm_dialogue({"goal": "laser detuning -> resonance linewidth", "max_steps": 2, "enable_identification": False})

    assert result["metadata"]["native_hypothesis_agent"] is True
    assert result["metadata"]["external_llm_used"] is False
    assert result["metadata"]["gemini_disabled"] is True
    assert result["metadata"]["output_format"] == "json_only"
    assert result["native_discovery"]["hypothesis"]["metadata"]["generated_by"] == "causalgate.scientific.hypothesis_discovery_agent"
    assert result["status"] != "AWAITING_GEMINI_CONFIG"


def test_compatibility_prompts_are_json_and_mark_native_mode():
    dialogue_prompt = json.loads(build_gemini_dialogue_prompt({"goal": "Find a testable hypothesis."}))
    normalization_prompt = json.loads(build_gemini_goal_normalization_prompt({"goal": "Voglio una ipotesi di fisica"}))
    render_prompt = json.loads(build_gemini_language_render_prompt({"final_decision": "FINAL_CANDIDATE"}))

    assert dialogue_prompt["native_json_mode"] is True
    assert normalization_prompt["native_json_mode"] is True
    assert render_prompt["native_json_mode"] is True


def test_gemini_adapter_is_noop_and_does_not_call_transport():
    calls = []

    def fake_transport(url, headers, payload, timeout_seconds):
        calls.append((url, headers, payload, timeout_seconds))
        return {}

    adapter = GeminiDialogueAdapter(
        GeminiDialogueAdapterConfig(api_key="test-key", model="gemini-test", base_url="https://example.test/v1beta"),
        transport=fake_transport,
    )
    result = adapter({"goal": "revise"})

    assert result == {}
    assert calls == []


def test_gemini_goal_normalizer_returns_local_topic_metadata_only():
    normalizer = GeminiGoalNormalizer(GeminiDialogueAdapterConfig())
    result = normalizer.normalize({"goal": "laser detuning -> resonance linewidth"})

    metadata = result["language_normalization"]
    assert metadata["needs_clarification"] is False
    assert metadata["research_goal"] == "laser detuning -> resonance linewidth"
    assert metadata["user_intent"] == "generate_hypothesis"
    assert "hypothesis" not in metadata


def test_gemini_language_renderer_returns_no_natural_language_block():
    renderer = GeminiLanguageRenderer(GeminiDialogueAdapterConfig())
    assert renderer.render({"final_decision": "FINAL_CANDIDATE"}) == {}


def test_mcp_exposes_native_alias_and_gemini_compat_tool(monkeypatch):
    monkeypatch.delenv("CAUSALGATE_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    tools = {tool["name"] for tool in list_tools()["tools"]}
    assert "causalgate_run_native_json_hypothesis" in tools
    assert "causalgate_run_gemini_llm_dialogue" in tools
    assert "causalgate_generate_hypothesis" in tools

    result = call_tool("causalgate_run_native_json_hypothesis", {"goal": "magnetic field strength -> spectral peak shift", "max_steps": 2, "enable_identification": False})
    assert result["metadata"]["gemini_disabled"] is True
    assert result["metadata"]["external_llm_used"] is False
    assert result["metadata"]["output_format"] == "json_only"


def test_generic_goal_auto_selects_only_physics_or_math_topic(monkeypatch):
    monkeypatch.delenv("CAUSALGATE_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    result = run_gemini_llm_dialogue({"goal": "Genera e migliora una ipotesi scientifica", "max_steps": 2, "enable_identification": False})

    components = result["metadata"]["auto_hypothesis_components"]
    assert result["metadata"]["gemini_disabled"] is True
    assert result["metadata"]["auto_hypothesis_generator"] == "dynamic_combinatorial_v3_physics_math_only"
    assert components["goal"] == result["goal"]
    assert components["family"]
    assert components["domain"] in {"mechanistic_physics", "mathematical"}
    assert components["domain"] != "empirical_causal"
    assert components["outcome"] in result["goal"]
    assert components["population"] in result["goal"]
    assert result["native_discovery"]["discovery_patch"]["goal"] == result["goal"]
    assert result["final_hypothesis"]["claim_level"] == "hypothesis_only"


def test_physics_goal_uses_mechanistic_physics_protocol():
    result = generate_hypothesis({"goal": "laser detuning -> resonance linewidth in cryogenic optical cavity setups under controlled laboratory boundary conditions"})
    hypothesis = result["hypothesis"]

    assert result["discovery_patch"]["detected_domain"] == "mechanistic_physics"
    assert hypothesis["domain"] == "mechanistic_physics"
    assert hypothesis["metadata"]["physics_protocol"] is True
    assert "uncertainty" in hypothesis["estimation_plan"].lower()
    assert "calibration" in " ".join(hypothesis["data_requirements"]).lower()
    assert "simulation" in hypothesis["simulation_plan"].lower()


def test_generated_physics_uses_clean_treatment_and_outcome():
    result = run_gemini_llm_dialogue({
        "goal": "magnetic field topology -> disk luminosity variability in galaxy survey samples across repeated experimental runs",
        "max_steps": 10,
        "enable_identification": False,
    })
    hypothesis = result["final_hypothesis"]

    assert hypothesis["treatment"] == "MagneticFieldTopology"
    assert hypothesis["outcome"] == "DiskLuminosityVariability"
    assert "DiskLuminosityVariabilityInGalaxySurveySamples" not in hypothesis["outcome"]
    assert hypothesis["domain"] == "mechanistic_physics"
    assert hypothesis["metadata"]["physics_protocol_type"] == "observational_or_simulation"
    assert result["final_verdict"]["decision"] == "FINAL_CANDIDATE"


def test_math_goal_uses_mathematical_conjecture_protocol_without_duplicate_prefix():
    result = run_gemini_llm_dialogue({
        "goal": "mathematical conjecture: chromatic-number bounds for sparse graphs in finite simple graphs with explicit definitions",
        "max_steps": 2,
        "enable_identification": False,
    })
    hypothesis = result["final_hypothesis"]
    verdict = result["final_verdict"]

    assert hypothesis["domain"] == "mathematical"
    assert hypothesis["hypothesis_kind"] == "mathematical_conjecture"
    assert hypothesis["claim"].count("mathematical conjecture") == 1
    assert "counterexample" in " ".join(hypothesis["falsification_tests"]).lower()
    assert result["metadata"]["external_llm_used"] is False
    assert verdict["claim_level"] == "conjecture_candidate"
    assert verdict["claim_level_key"] == "proof_or_counterexample_candidate"
    assert verdict["causal_status"] == "not_applicable_mathematical_conjecture"
    assert "treatment_or_cause" not in verdict["missing_items"]


def test_generic_goal_generation_varies_across_runs(monkeypatch):
    monkeypatch.delenv("CAUSALGATE_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    goals = {
        run_gemini_llm_dialogue({"goal": "Genera e migliora una ipotesi scientifica", "max_steps": 1, "enable_identification": False})["goal"]
        for _ in range(4)
    }

    assert len(goals) >= 2


def test_config_reports_native_json_mode(monkeypatch):
    monkeypatch.setenv("CAUSALGATE_GEMINI_API_KEY", "ignored-key")
    config = GeminiDialogueAdapterConfig.from_env()

    assert config.configured is False
    assert config.safe_dict()["native_json_mode"] is True
    assert config.safe_dict()["api_key"] == ""
