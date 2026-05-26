from causalgate.mcp.tools import call_tool, list_tools
from causalgate.scientific import LLMDialogueOrchestrator, run_llm_dialogue


def test_llm_dialogue_awaits_llm_when_no_hypothesis_or_adapter():
    result = run_llm_dialogue({
        "goal": "Discuss a candidate scientific hypothesis.",
        "max_steps": 2,
        "auto_expand": True,
        "enable_identification": False,
    })

    assert result["status"] == "AWAITING_LLM_PROPOSAL"
    assert result["should_continue"] is True
    assert result["turns"][0]["llm_context"]["role"] == "llm_propose_or_revise_hypothesis"
    assert "CausalGate remains the authority" in " ".join(result["turns"][0]["llm_context"]["hard_rules"])


def test_llm_dialogue_can_use_local_adapter_but_causalgate_keeps_authority():
    calls = []

    def adapter(context):
        calls.append(context)
        if context["step"] == 1:
            return {"hypothesis": {"hypothesis_id": "H-dialogue-1", "claim": "Sleep may affect productivity."}}
        return {"hypothesis": {
            "hypothesis_id": "H-dialogue-1-rev",
            "claim": "Increasing sleep duration from less than 6h to more than 7.5h may increase next-day completed tasks under stated assumptions.",
            "treatment": "sleep_duration_gt_7_5h",
            "outcome": "next_day_completed_tasks",
            "dag": {"nodes": ["sleep_duration_gt_7_5h", "next_day_completed_tasks"], "directed_edges": [["sleep_duration_gt_7_5h", "next_day_completed_tasks"]]},
            "assumptions": ["Sleep is measured before the outcome window."],
            "falsification_tests": ["Future sleep should not predict past productivity.", "Negative-control outcome should not change."],
            "negative_control_tests": ["Negative-control outcome should remain null."],
            "placebo_tests": ["Temporal placebo with future treatment."],
            "sensitivity_checks": ["Hidden-confounding sensitivity check."],
            "data_requirements": ["Time-ordered daily measurements of sleep and tasks."],
        }}

    result = LLMDialogueOrchestrator(llm_adapter=adapter, enable_identification=False).run({
        "goal": "Mature sleep/productivity hypothesis.",
        "max_steps": 3,
        "auto_expand": True,
    }).to_dict()

    assert calls
    assert result["status"] in {"FINAL_CANDIDATE", "MAX_STEPS_REACHED", "AWAITING_LLM_REVISION"}
    assert result["metadata"]["llm_adapter_present"] is True
    assert result["turns"]
    assert result["final_decision"] in {"FINAL_CANDIDATE", "REVISE", "TEST_MORE", "ABSTAIN"}


def test_mcp_exposes_llm_dialogue_tool():
    tools = {tool["name"] for tool in list_tools()["tools"]}
    assert "causalgate_run_llm_dialogue" in tools

    result = call_tool("causalgate_run_llm_dialogue", {
        "goal": "MCP LLM dialogue smoke test.",
        "max_steps": 1,
        "auto_expand": True,
        "enable_identification": False,
    })
    assert result["status"] == "AWAITING_LLM_PROPOSAL"
    assert result["metadata"]["orchestrator"] == "causalgate.scientific.llm_dialogue.LLMDialogueOrchestrator"
