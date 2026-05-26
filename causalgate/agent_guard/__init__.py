"""Execution guard for AI-agent tool calls.

This package enforces CausalGate decisions before tool execution.
"""

from .blocked_response import build_blocked_response
from .execution_policy import (
    ASK_USER,
    BLOCK,
    DEFAULT_EXECUTION_POLICY,
    EXECUTE,
    EXECUTE_WITH_WARNING,
    ExecutionPolicy,
)

__all__ = [
    "ASK_USER",
    "BLOCK",
    "DEFAULT_EXECUTION_POLICY",
    "EXECUTE",
    "EXECUTE_WITH_WARNING",
    "ExecutionPolicy",
    "ToolGuard",
    "ToolGuardResult",
    "build_blocked_response",
    "guard_tool_call",
]


def __getattr__(name: str):
    if name in {"ToolGuard", "ToolGuardResult", "guard_tool_call"}:
        from .tool_guard import ToolGuard, ToolGuardResult, guard_tool_call

        values = {
            "ToolGuard": ToolGuard,
            "ToolGuardResult": ToolGuardResult,
            "guard_tool_call": guard_tool_call,
        }
        return values[name]
    raise AttributeError(name)
