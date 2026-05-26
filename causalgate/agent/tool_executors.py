from __future__ import annotations

import json
import re
import shlex
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from .tool_registry import ToolRegistry, ToolSpec


_SAFE_SYMBOL = re.compile(r"^[A-Z0-9._:-]{1,24}$")
_ALLOWED_TEST_BINARIES = {"pytest"}
_ALLOWED_PYTHON_TEST_COMMANDS = {("python", "-m", "pytest"), ("python3", "-m", "pytest")}


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except Exception:
        return str(value)


@dataclass
class SandboxToolResult:
    """Structured result for one sandbox tool execution."""

    ok: bool
    tool_name: str
    sandboxed: bool = True
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SandboxToolExecutor:
    """Stdlib-only executor for safe demo/agent tools.

    This executor intentionally supports only bounded, local, non-live actions:
    safe file reads, draft-only writes, pytest in a sandboxed subprocess, and
    paper-trade logging. It never sends email, deploys, transfers money, calls a
    broker, or performs unrestricted shell execution.
    """

    def __init__(
        self,
        *,
        root_dir: str | Path = ".",
        out_dir: str | Path = "out",
        drafts_dir: str | Path | None = None,
        max_read_bytes: int = 64_000,
        max_output_bytes: int = 32_000,
        test_timeout_seconds: int = 30,
    ) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.out_dir = self._safe_dir(out_dir)
        self.drafts_dir = self._safe_dir(drafts_dir or Path(out_dir) / "agent_drafts")
        self.max_read_bytes = int(max_read_bytes)
        self.max_output_bytes = int(max_output_bytes)
        self.test_timeout_seconds = int(test_timeout_seconds)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.drafts_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, tool_name: str, args: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        name = _clean_str(tool_name)
        values = _as_dict(args)
        try:
            if name in {"read_file_safe", "read_file"}:
                return self.read_file_safe(values).to_dict()
            if name in {"write_draft_file", "write_file"}:
                return self.write_draft_file(values).to_dict()
            if name in {"run_tests_sandbox", "run_shell_command"}:
                return self.run_tests_sandbox(values).to_dict()
            if name in {"paper_trade_order", "paper_trade_limit_order"}:
                return self.paper_trade_order(values).to_dict()
            return SandboxToolResult(
                ok=False,
                tool_name=name,
                message="Tool is not supported by SandboxToolExecutor.",
                error={"type": "UnsupportedSandboxTool", "tool_name": name},
            ).to_dict()
        except Exception as exc:  # defensive sandbox boundary
            return SandboxToolResult(
                ok=False,
                tool_name=name,
                message="Sandbox tool failed safely.",
                error={"type": type(exc).__name__, "message": str(exc)},
            ).to_dict()

    def read_file_safe(self, args: Mapping[str, Any]) -> SandboxToolResult:
        path = self._safe_path(args.get("path"), base=self.root_dir)
        max_bytes = int(args.get("max_bytes") or self.max_read_bytes)
        max_bytes = max(1, min(max_bytes, self.max_read_bytes))
        raw = path.read_bytes()
        truncated = len(raw) > max_bytes
        raw = raw[:max_bytes]
        try:
            content = raw.decode(str(args.get("encoding") or "utf-8"), errors="replace")
        except LookupError:
            content = raw.decode("utf-8", errors="replace")
        return SandboxToolResult(
            ok=True,
            tool_name="read_file_safe",
            message="File read inside sandbox root.",
            data={
                "path": str(path.relative_to(self.root_dir)),
                "absolute_path": str(path),
                "bytes_read": len(raw),
                "truncated": truncated,
                "content": content,
            },
        )

    def write_draft_file(self, args: Mapping[str, Any]) -> SandboxToolResult:
        raw_path = _clean_str(args.get("path") or args.get("filename"), "draft.txt")
        # Draft writes are intentionally rooted under out/agent_drafts even if
        # the planner asks for a source path. This prevents silent code mutation.
        path = self._safe_path(raw_path, base=self.drafts_dir, allow_create=True)
        if path.exists() and not bool(args.get("allow_overwrite", False)):
            stem = path.stem or "draft"
            suffix = path.suffix or ".txt"
            path = path.with_name(f"{stem}_{int(time.time())}{suffix}")
        content = str(args.get("content") or args.get("draft_content") or "")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding=str(args.get("encoding") or "utf-8"))
        return SandboxToolResult(
            ok=True,
            tool_name="write_draft_file",
            message="Draft file written. Source files were not modified.",
            data={
                "draft_path": str(path),
                "draft_relative_path": str(path.relative_to(self.drafts_dir)),
                "bytes_written": len(content.encode("utf-8")),
                "source_files_modified": False,
            },
        )

    def run_tests_sandbox(self, args: Mapping[str, Any]) -> SandboxToolResult:
        tokens = self._test_command_tokens(args)
        timeout = int(args.get("timeout_seconds") or self.test_timeout_seconds)
        timeout = max(1, min(timeout, self.test_timeout_seconds))
        completed = subprocess.run(
            tokens,
            cwd=str(self.root_dir),
            text=True,
            capture_output=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
        stdout = (completed.stdout or "")[: self.max_output_bytes]
        stderr = (completed.stderr or "")[: self.max_output_bytes]
        return SandboxToolResult(
            ok=completed.returncode == 0,
            tool_name="run_tests_sandbox",
            message="Pytest command executed in sandbox subprocess.",
            data={
                "command": tokens,
                "cwd": str(self.root_dir),
                "exit_code": completed.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "stdout_truncated": len(completed.stdout or "") > len(stdout),
                "stderr_truncated": len(completed.stderr or "") > len(stderr),
            },
        )

    def paper_trade_order(self, args: Mapping[str, Any]) -> SandboxToolResult:
        symbol = _clean_str(args.get("symbol") or args.get("ticker") or args.get("instrument_symbol")).upper()
        side = _clean_str(args.get("side") or args.get("trade_side"), "buy").lower()
        order_type = _clean_str(args.get("order_type"), "limit").lower()
        if not _SAFE_SYMBOL.match(symbol):
            raise ValueError("symbol must be 1-24 uppercase alphanumeric/exchange characters")
        if side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        if order_type not in {"limit", "market", "stop"}:
            raise ValueError("order_type must be limit, market or stop")
        quantity = float(args.get("quantity") or args.get("qty") or 0)
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        limit_price = args.get("limit_price") or args.get("price")
        if order_type == "limit" and limit_price in {None, ""}:
            raise ValueError("limit paper orders require limit_price or price")
        order = {
            "order_id": f"paper-{int(time.time() * 1000)}",
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "order_type": order_type,
            "limit_price": float(limit_price) if limit_price not in {None, ""} else None,
            "time_in_force": _clean_str(args.get("time_in_force"), "day"),
            "created_at_epoch": time.time(),
            "live_trading": False,
            "real_money": False,
            "broker_called": False,
        }
        log_path = self.out_dir / "paper_trades.jsonl"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(order, sort_keys=True) + "\n")
        return SandboxToolResult(
            ok=True,
            tool_name="paper_trade_order",
            message="Paper trade recorded only. No broker or real-money system was called.",
            data={"order": order, "log_path": str(log_path)},
        )

    def _safe_dir(self, path: str | Path) -> Path:
        value = Path(path)
        if not value.is_absolute():
            value = self.root_dir / value
        resolved = value.resolve()
        self._ensure_inside(resolved, self.root_dir)
        return resolved

    def _safe_path(self, raw_path: Any, *, base: Path, allow_create: bool = False) -> Path:
        text = _clean_str(raw_path)
        if not text:
            raise ValueError("path is required")
        # Absolute paths are allowed only if they still resolve under base/root.
        path = Path(text)
        if not path.is_absolute():
            path = base / path
        resolved = path.resolve()
        self._ensure_inside(resolved, base)
        if not allow_create and not resolved.exists():
            raise FileNotFoundError(str(resolved))
        return resolved

    @staticmethod
    def _ensure_inside(path: Path, base: Path) -> None:
        try:
            path.relative_to(base.resolve())
        except ValueError as exc:
            raise PermissionError(f"sandbox path escape blocked: {path}") from exc

    def _test_command_tokens(self, args: Mapping[str, Any]) -> list[str]:
        raw = args.get("command") or args.get("args") or ["pytest"]
        if isinstance(raw, str):
            tokens = shlex.split(raw)
        elif isinstance(raw, Iterable):
            tokens = [str(item) for item in raw]
        else:
            tokens = ["pytest"]
        if not tokens:
            tokens = ["pytest"]
        prefix3 = tuple(tokens[:3])
        if tokens[0] in _ALLOWED_TEST_BINARIES:
            pass
        elif prefix3 in _ALLOWED_PYTHON_TEST_COMMANDS:
            pass
        else:
            raise PermissionError("run_tests_sandbox only allows pytest or python -m pytest commands")
        forbidden = {";", "&&", "||", "|", ">", "<", "`", "$()"}
        if any(token in forbidden for token in tokens):
            raise PermissionError("shell metacharacters are not allowed in sandbox test commands")
        return tokens


def build_sandbox_tool_registry(
    *,
    root_dir: str | Path = ".",
    out_dir: str | Path = "out",
    include_legacy_aliases: bool = True,
) -> ToolRegistry:
    """Build a registry of bounded demo tools backed by SandboxToolExecutor."""

    executor = SandboxToolExecutor(root_dir=root_dir, out_dir=out_dir)

    def run(name: str):
        return lambda args: executor.execute(name, args)

    tools = [
        ToolSpec(
            name="read_file_safe",
            executor=run("read_file_safe"),
            action_type="read",
            target_resource="file",
            risk_level="low",
            allowed_agent_modes=["code_agent"],
            side_effect_level="none",
            input_schema={"required": ["path"], "path": "string"},
            sandbox_required=True,
            requires_filesystem=True,
            description="Read a file inside the sandbox root.",
        ),
        ToolSpec(
            name="write_draft_file",
            executor=run("write_draft_file"),
            action_type="mutation",
            target_resource="draft_file",
            risk_level="medium",
            allowed_agent_modes=["code_agent"],
            side_effect_level="state_change",
            input_schema={"required": ["path", "content"], "path": "string", "content": "string"},
            sandbox_required=True,
            requires_filesystem=True,
            description="Write a draft under out/agent_drafts without modifying source files.",
        ),
        ToolSpec(
            name="run_tests_sandbox",
            executor=run("run_tests_sandbox"),
            action_type="code_execution",
            target_resource="pytest",
            risk_level="medium",
            allowed_agent_modes=["code_agent"],
            side_effect_level="sandboxed_process",
            input_schema={"command": "string"},
            sandbox_required=True,
            requires_filesystem=True,
            timeout_seconds=30,
            description="Run pytest only in a bounded subprocess.",
        ),
        ToolSpec(
            name="paper_trade_order",
            executor=run("paper_trade_order"),
            action_type="trade_execution",
            target_resource="paper_trade_ledger",
            risk_level="low",
            allowed_agent_modes=["finance_trading_agent"],
            side_effect_level="paper_only",
            input_schema={"quantity": "number", "symbol": "string", "instrument_symbol": "string", "side": "string", "trade_side": "string"},
            sandbox_required=True,
            requires_filesystem=True,
            description="Record a paper trade only; no broker or real-money execution.",
        ),
    ]
    registry = ToolRegistry(tools)
    if include_legacy_aliases:
        registry.register(ToolSpec(name="read_file", executor=run("read_file_safe"), action_type="read", risk_level="low", input_schema={"required": ["path"]}, allowed_agent_modes=["code_agent"], sandbox_required=True, requires_filesystem=True))
        registry.register(ToolSpec(name="write_file", executor=run("write_draft_file"), action_type="mutation", risk_level="medium", input_schema={"required": ["path", "content"]}, allowed_agent_modes=["code_agent"], sandbox_required=True, requires_filesystem=True, description="Alias to write_draft_file; never mutates source files."))
        registry.register(ToolSpec(name="run_shell_command", executor=run("run_tests_sandbox"), action_type="code_execution", risk_level="high", input_schema={"command": "string"}, allowed_agent_modes=["code_agent"], sandbox_required=True, requires_filesystem=True, description="Alias restricted to pytest commands only."))
        registry.register(ToolSpec(name="paper_trade_limit_order", executor=run("paper_trade_order"), action_type="trade_execution", risk_level="low", input_schema={"quantity": "number", "symbol": "string", "instrument_symbol": "string", "side": "string", "trade_side": "string"}, allowed_agent_modes=["finance_trading_agent"], sandbox_required=True, requires_filesystem=True, description="Alias to paper_trade_order."))
    return registry


__all__ = [
    "SandboxToolExecutor",
    "SandboxToolResult",
    "build_sandbox_tool_registry",
]
