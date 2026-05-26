from causalgate.mcp.tools import call_tool
from causalgate.scientific import generate_hypothesis


def test_native_discovery_generates_empirical_candidate_with_required_fields():
    result = generate_hypothesis({"goal": "green space visits -> stress levels"})
    hypothesis = result["hypothesis"]

    assert result["discovery_patch"]["mode"] == "native_deterministic_generation"
    assert hypothesis["hypothesis_kind"] == "empirical_hypothesis"
    assert hypothesis["domain_diagnostic"]["detected_domain"] == "empirical_causal"
    assert hypothesis["identification_strategy"].startswith("Back-door adjustment")
    assert hypothesis["observed_confounder_measurements"]
    assert hypothesis["external_evidence_quality"]["status"] == "not_checked"
    assert hypothesis["claim_level"] == "hypothesis_only"


def test_native_discovery_uses_math_protocol_for_conjectures():
    result = generate_hypothesis({"goal": "prove a theorem about prime gaps"})
    hypothesis = result["hypothesis"]

    assert hypothesis["hypothesis_kind"] == "mathematical_conjecture"
    assert hypothesis["identification_strategy"].startswith("Mathematical proof")
    assert hypothesis["adjustment_set"] == []
    assert hypothesis["external_evidence_quality"]["status"] == "not_applicable"


def test_mcp_generate_hypothesis_tool_available():
    result = call_tool("causalgate_generate_hypothesis", {"goal": "meditation -> stress"})

    assert result["hypothesis"]["metadata"]["generated_by"] == "causalgate.scientific.hypothesis_discovery_agent"
    assert result["hypothesis"]["claim_level"] == "hypothesis_only"


def test_native_discovery_does_not_match_math_or_physics_terms_inside_words():
    sleep = generate_hypothesis({"goal": "Does longer sleep improve cognitive performance?"})
    education = generate_hypothesis({"goal": "Does education increase income?"})
    reaction = generate_hypothesis({"goal": "Does intervention affect reaction time?"})

    assert sleep["hypothesis"]["domain"] == "empirical_causal"
    assert sleep["hypothesis"]["hypothesis_kind"] == "empirical_hypothesis"
    assert education["hypothesis"]["domain"] == "empirical_causal"
    assert reaction["hypothesis"]["domain"] == "empirical_causal"


def test_native_discovery_still_detects_explicit_math_and_physics_terms():
    math = generate_hypothesis({"goal": "prove a theorem about prime gaps"})
    physics = generate_hypothesis({"goal": "ion trap laser cooling -> qubit coherence"})

    assert math["hypothesis"]["domain"] == "mathematical"
    assert physics["hypothesis"]["domain"] == "mechanistic_physics"
