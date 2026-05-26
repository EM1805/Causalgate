import json
import threading
from http.client import HTTPConnection
from causalgate.agent import AgentAPIConfig
from causalgate.agent.api import (
    CausalGateThreadingHTTPServer,
    decide_agent_request,
    make_agent_api_handler,
    record_agent_outcome_request,
    run_agent_request,
)
from causalgate.agent.types import AgentRunResult
from causalgate.learning import AuditLog


class StubAgent:
    def __init__(self):
        self.calls = []
        self.tool_registry = type("Registry", (), {"to_dict": lambda self_: {"safe_tool": {"executor": False}}})()

    def run(self, user_message, **kwargs):
        self.calls.append({"user_message": user_message, **kwargs})
        return AgentRunResult(
            status="respond",
            response_type="communication",
            user_message=user_message,
            selected_action="ask_clarification",
            decision="ask_clarification",
            executed=False,
            blocked=False,
            needs_user_confirmation=True,
        )


def test_decide_endpoint_forces_no_tool_execution_even_if_requested():
    agent = StubAgent()
    result = decide_agent_request(
        {
            "user_message": "delete prod",
            "execute_tools": True,
            "candidate_actions": [{"action_name": "delete_resource", "action_type": "tool_call"}],
        },
        agent=agent,
    )

    assert result["api"]["endpoint_mode"] == "decide"
    assert result["api"]["execute_tools_requested"] is True
    assert result["api"]["execute_tools_effective"] is False
    assert agent.calls[0]["execute_tools"] is False


def test_run_endpoint_still_defaults_to_no_execution():
    agent = StubAgent()
    config = AgentAPIConfig(default_execute_tools=False)
    result = run_agent_request(
        {
            "user_message": "safe utility action",
            "candidate_actions": [{"action_name": "safe_tool", "action_type": "tool_call"}],
        },
        agent=agent,
        config=config,
    )

    assert result["api"]["endpoint_mode"] == "run"
    assert result["api"]["execute_tools_requested"] is False
    assert result["api"]["execute_tools_effective"] is False
    assert agent.calls[0]["execute_tools"] is False


def test_run_endpoint_can_request_execution_but_only_opt_in():
    agent = StubAgent()
    result = run_agent_request(
        {
            "user_message": "run registered tool",
            "execute_tools": True,
            "candidate_actions": [{"action_name": "safe_tool", "action_type": "tool_call"}],
        },
        agent=agent,
    )

    assert result["api"]["execute_tools_requested"] is True
    assert result["api"]["execute_tools_effective"] is True
    assert agent.calls[0]["execute_tools"] is True


def test_record_agent_outcome_request_appends_learning_event(tmp_path):
    log_path = tmp_path / "agent_learning_events.jsonl"
    result = record_agent_outcome_request(
        {
            "audit_log_path": str(log_path),
            "decision_event_id": "decision-1",
            "request_id": "request-1",
            "selected_action": "safe_tool",
            "outcome": "success",
            "success": True,
            "harm": False,
            "user_satisfaction": 5,
            "latency_ms": 12,
        }
    )

    assert result["event_type"] == "outcome"
    rows = AuditLog(log_path).read_events()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "outcome"


def test_stdlib_http_handler_exposes_health_and_decide():
    agent = StubAgent()
    config = AgentAPIConfig(port=0)

    def factory(_config, _payload):
        return agent

    handler = make_agent_api_handler(config=config, agent_factory=factory)
    server = CausalGateThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address

        conn = HTTPConnection(host, port, timeout=5)
        try:
            conn.request("GET", "/health")
            response = conn.getresponse()
            body = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert response.getheader("Connection") == "close"
            assert body["status"] == "ok"
        finally:
            conn.close()

        conn = HTTPConnection(host, port, timeout=5)
        try:
            conn.request(
                "POST",
                "/agent/decide",
                body=json.dumps({"user_message": "should be reviewed", "execute_tools": True}),
                headers={"Content-Type": "application/json"},
            )
            response = conn.getresponse()
            body = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert response.getheader("Connection") == "close"
            assert body["api"]["endpoint_mode"] == "decide"
            assert body["api"]["execute_tools_effective"] is False
        finally:
            conn.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()
