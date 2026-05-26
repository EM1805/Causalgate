from causalgate.mcp.http_server import capabilities_payload, health_payload, metadata_payload, _demo_arguments, _demo_tool_name


def test_capabilities_payload_advertises_complete_json_demo(monkeypatch):
    monkeypatch.delenv("CAUSALGATE_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    capabilities = capabilities_payload()

    assert capabilities["native_hypothesis_agent"] is True
    assert capabilities["external_llm_used"] is False
    assert capabilities["gemini_disabled"] is True
    assert capabilities["gemini_propose_or_revise"] is False
    assert capabilities["gemini_language_only"] is False
    assert capabilities["gemini_configured"] is False
    assert capabilities["output_format"] == "json_only"
    assert capabilities["demo_default_mode"] == "complete_causal_json"
    assert capabilities["demo_full_pipeline"] is True
    assert capabilities["native_physics_math_full_pipeline"] is True
    assert "HypothesisDiscoveryAgent" in capabilities["demo_pipeline_components"]
    assert "SCM-ID identification" in capabilities["demo_pipeline_components"]
    assert "Estimation adapter" in capabilities["demo_pipeline_components"]
    assert "FalsificationPolicy" in capabilities["demo_pipeline_components"]
    assert capabilities["demo_requires_user_text"] is False
    assert capabilities["demo_shows_cycles"] is True


def test_health_and_metadata_include_complete_json_capabilities(monkeypatch):
    monkeypatch.delenv("CAUSALGATE_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    assert health_payload()["capabilities"]["demo_full_pipeline"] is True
    assert health_payload()["capabilities"]["gemini_disabled"] is True
    assert metadata_payload()["capabilities"]["output_format"] == "json_only"
    assert metadata_payload()["capabilities"]["demo_default_mode"] == "complete_causal_json"
    assert metadata_payload()["capabilities"]["native_physics_math_full_pipeline"] is True


def test_demo_arguments_default_to_complete_causal_pipeline():
    args = _demo_arguments({"goal": "sleep -> productivity", "max_steps": 9})

    assert _demo_tool_name({}) == "causalgate_run_llm_dialogue"
    assert args["native_hypothesis_agent"] is False
    assert args["enable_identification"] is True
    assert args["gemini_language_only"] is False
    assert args["output_format"] == "json_only"
    assert args["demo_mode"] == "complete_causal_json"
    assert args["max_steps"] == 9
    assert args["max_iterations"] == 9
    assert args["hypothesis"]["treatment"] == "X"
    assert args["hypothesis"]["outcome"] == "Y"
    assert args["hypothesis"]["metadata"]["effect_estimate"] == 0.12


def test_demo_arguments_do_not_require_user_text():
    args = _demo_arguments({"max_steps": 6})

    assert args["goal"] == "Complete causal demo: Discovery/orchestration → Veto → SCM-ID → Estimation → claim audit"
    assert args["native_hypothesis_agent"] is False
    assert args["enable_identification"] is True
    assert args["output_format"] == "json_only"


def test_demo_arguments_keep_native_generative_mode_available_as_full_pipeline():
    args = _demo_arguments({"goal": "sleep -> productivity", "mode": "native_json_only"})

    assert _demo_tool_name({"mode": "native_json_only"}) == "causalgate_run_native_json_hypothesis"
    assert args["native_hypothesis_agent"] is True
    assert args["enable_identification"] is True
    assert args["full_pipeline"] is True
    assert "Physics/math native candidates pass through discovery" in args["pipeline_note"]
    assert args["gemini_language_only"] is False
    assert args["output_format"] == "json_only"
    assert args["demo_mode"] == "native_json_only"


def test_demo_arguments_can_explicitly_disable_identification_in_native_mode():
    args = _demo_arguments({"goal": "mathematical conjecture", "mode": "native_json_only", "enable_identification": False})

    assert _demo_tool_name({"mode": "native_json_only"}) == "causalgate_run_native_json_hypothesis"
    assert args["native_hypothesis_agent"] is True
    assert args["enable_identification"] is False
    assert args["full_pipeline"] is True


def test_demo_arguments_ignore_old_gemini_dialogue_mode_as_complete_pipeline():
    args = _demo_arguments({"goal": "sleep -> productivity", "mode": "gemini_dialogue"})

    assert _demo_tool_name({"mode": "gemini_dialogue"}) == "causalgate_run_llm_dialogue"
    assert args["native_hypothesis_agent"] is False
    assert args["enable_identification"] is True
    assert args["output_format"] == "json_only"
