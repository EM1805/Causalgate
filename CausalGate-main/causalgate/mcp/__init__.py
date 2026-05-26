"""MCP bridge for CausalGate.

Stdlib-only helpers that expose CausalGate's scientific veto and research loop as
tool-like functions for MCP clients.
"""

from .tools import call_tool, list_tools

__all__ = ["call_tool", "list_tools"]
