from causalgate.agent import HierarchicalActionPlanner, LLMActionPlanner, PlannerConfig


def names(response):
    return [item["action_name"] for item in response.candidate_actions]


def by_name(response, action_name):
    for item in response.candidate_actions:
        if item["action_name"] == action_name:
            return item
    raise AssertionError(f"missing action {action_name}")


def test_hierarchical_planner_proposes_code_patch_with_safe_read_fallback():
    planner = HierarchicalActionPlanner(PlannerConfig(default_agent_mode="code_agent"))
    response = planner.propose_actions(
        "migliora il planner nel file causalgate/agent/planner.py",
        planner_context={"agent_mode": "code_agent"},
    )
    assert "write_file" in names(response)
    assert "read_file" in names(response)
    write = by_name(response, "write_file")
    assert write["agent_mode"] == "code_agent"
    assert write["action_registry_registered"] is True
    assert write["requires_user_confirmation"] is True
    assert "missing_inputs" in write


def test_hierarchical_planner_routes_live_trade_to_finance_mode_and_paper_fallback():
    planner = HierarchicalActionPlanner()
    response = planner.propose_actions(
        "buy AAPL market order",
        trusted_runtime_context={"live_trading": True, "real_money": True},
    )
    action_names = names(response)
    assert "place_market_order" in action_names
    assert "paper_trade_limit_order" in action_names
    live = by_name(response, "place_market_order")
    assert live["agent_mode"] == "finance_trading_agent"
    assert live["risk_level"] in {"high", "critical"}
    assert "risk_limits_present" in live.get("missing_inputs", [])


def test_llm_action_planner_normalizes_mock_candidates_and_registry_aliases():
    planner = LLMActionPlanner()
    response = planner.propose_actions("Cerca informazioni aggiornate su CausalGate")
    action_names = names(response)
    assert "search_information" in action_names or "browse_web" in action_names
    candidate = by_name(response, "search_information") if "search_information" in action_names else by_name(response, "browse_web")
    assert candidate["requires_tool"] is True
    assert candidate["action_registry_registered"] is True
    assert response.raw_model_output["planner"] == "LLMActionPlanner+HierarchicalActionPlanner"
