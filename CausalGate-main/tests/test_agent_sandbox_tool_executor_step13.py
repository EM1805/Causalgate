from pathlib import Path

from causalgate.agent import CausalGateAgent, SandboxToolExecutor, build_sandbox_tool_registry
from causalgate.contracts import DecisionPackage


class StubBrain:
    def __init__(self, selected):
        self.selected = selected

    def run(self, payload):
        selected = self.selected

        class Run:
            def to_dict(self):
                return {"selected": selected.to_dict(), "evaluated_actions": [selected.to_dict()], "notes": []}

        return Run()


class StubGuard:
    def __init__(self):
        self.calls = []

    def guard_tool_call(self, action_payload, *, tool_executor=None, tool_args=None, tool_name="", **kwargs):
        self.calls.append({"tool_name": tool_name, "tool_args": dict(tool_args or {})})
        return type("Result", (), {"to_dict": lambda self_: {
            "status": "executed" if tool_executor else "permitted_not_executed",
            "executed": bool(tool_executor),
            "blocked": False,
            "needs_user_confirmation": False,
            "tool_name": tool_name,
            "tool_args": dict(tool_args or {}),
            "tool_result": tool_executor(dict(tool_args or {})) if tool_executor else None,
            "decision_package": {"decision": "allow"},
        }})()


def test_step13_sandbox_registry_exposes_safe_tools(tmp_path):
    registry = build_sandbox_tool_registry(root_dir=tmp_path, out_dir="out")
    names = set(registry.names())
    assert {"read_file_safe", "write_draft_file", "run_tests_sandbox", "paper_trade_order"}.issubset(names)
    assert {"read_file", "write_file", "run_shell_command", "paper_trade_limit_order"}.issubset(names)


def test_step13_agent_can_execute_safe_file_read(tmp_path):
    (tmp_path / "README.md").write_text("hello sandbox", encoding="utf-8")
    agent = CausalGateAgent(
        brain=StubBrain(DecisionPackage(decision="allow", selected_action="read_file_safe")),
        tool_guard=StubGuard(),
        enable_sandbox_tools=True,
        sandbox_root_dir=tmp_path,
        sandbox_out_dir="out",
        enable_evidence_reader=False,
    )
    result = agent.run(
        "read README",
        agent_mode="code_agent",
        candidate_actions=[{"action_name": "read_file_safe"}],
        tool_args={"path": "README.md"},
        execute_tools=True,
    ).to_dict()
    assert result["executed"] is True
    assert result["tool_result"]["ok"] is True
    assert result["tool_result"]["data"]["content"] == "hello sandbox"


def test_step13_write_file_alias_writes_draft_not_source(tmp_path):
    source = tmp_path / "module.py"
    source.write_text("old", encoding="utf-8")
    agent = CausalGateAgent(
        brain=StubBrain(DecisionPackage(decision="allow", selected_action="write_file")),
        tool_guard=StubGuard(),
        enable_sandbox_tools=True,
        sandbox_root_dir=tmp_path,
        sandbox_out_dir="out",
        enable_evidence_reader=False,
    )
    result = agent.run(
        "write file",
        agent_mode="code_agent",
        candidate_actions=[{"action_name": "write_file"}],
        tool_args={"path": "module.py", "content": "new"},
        execute_tools=True,
    ).to_dict()
    assert result["executed"] is True
    assert result["tool_result"]["tool_name"] == "write_draft_file"
    assert result["tool_result"]["data"]["source_files_modified"] is False
    assert source.read_text(encoding="utf-8") == "old"
    assert Path(result["tool_result"]["data"]["draft_path"]).read_text(encoding="utf-8") == "new"


def test_step13_run_tests_sandbox_blocks_non_pytest_command(tmp_path):
    executor = SandboxToolExecutor(root_dir=tmp_path, out_dir="out")
    result = executor.execute("run_tests_sandbox", {"command": "rm -rf ."})
    assert result["ok"] is False
    assert result["error"]["type"] in {"PermissionError", "UnsupportedSandboxTool"}


def test_step13_paper_trade_records_no_real_money_order(tmp_path):
    executor = SandboxToolExecutor(root_dir=tmp_path, out_dir="out")
    result = executor.execute(
        "paper_trade_order",
        {"instrument_symbol": "AAPL", "trade_side": "buy", "quantity": 1, "limit_price": 100.0},
    )
    assert result["ok"] is True
    order = result["data"]["order"]
    assert order["symbol"] == "AAPL"
    assert order["real_money"] is False
    assert order["broker_called"] is False
