from causalgate.llm_interface import MockLLMClient, extract_candidate_actions, llm_response_to_brain_payload, propose_and_decide


def test_mock_llm_extracts_clarification_for_ambiguous_message():
    response = MockLLMClient().propose_actions("Non funziona, sistemalo.", context={"environment": "development"})
    names = [item["action_name"] for item in response.candidate_actions]

    assert "ask_clarification" in names
    assert "answer_directly" in names
    assert response.context["ambiguity"] == "high"


def test_prompt_adapter_builds_operational_brain_payload():
    response = MockLLMClient().propose_actions("Cerca informazioni aggiornate.", context={})
    payload = llm_response_to_brain_payload(response)
    names = [item["action_name"] for item in payload["candidate_actions"]]

    assert payload["user_message"] == "Cerca informazioni aggiornate."
    assert "search_information" in names
    assert payload["source"] == "mock_llm_client"


def test_mock_llm_to_operational_brain_prefers_clarification_when_ambiguous():
    result = propose_and_decide("Non funziona, sistemalo.", context={"environment": "development"})
    assert result["selected"]["selected_action"] == "ask_clarification"
    assert result["selected"]["decision"] in {"allow", "warn", "ask_clarification"}
    assert "llm_response" in result


def test_mock_llm_to_operational_brain_vetoes_destructive_prod_candidate_and_selects_safe_alternative():
    result = propose_and_decide(
        "Delete the production dataset if it looks wrong.",
        context={
            "environment": "production",
            "risk_level": "high",
            "ambiguity": "high",
            "approval_present": False,
            "rollback_available": False,
            "resource_sensitivity": "high",
        },
    )

    evaluated = {item["selected_action"]: item for item in result["evaluated_actions"]}
    assert "delete_resource" in evaluated
    assert evaluated["delete_resource"]["decision"] == "veto"
    assert result["selected"]["selected_action"] == "ask_clarification"
