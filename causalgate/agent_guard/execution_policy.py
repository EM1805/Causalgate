from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Mapping, Set


EXECUTE = "execute"
EXECUTE_WITH_WARNING = "execute_with_warning"
ASK_USER = "ask_user"
BLOCK = "block"


@dataclass(frozen=True)
class ExecutionPolicy:
    """Maps an CausalGate DecisionPackage decision to an execution action.

    This is the hard boundary between causal decisioning and tool execution:
    tools are allowed to run only for decisions explicitly listed in
    ``execute_decisions``. Unknown decisions fail closed.
    """

    execute_decisions: Set[str] = field(default_factory=lambda: {"allow"})
    warning_decisions: Set[str] = field(default_factory=lambda: {"warn"})
    ask_decisions: Set[str] = field(default_factory=lambda: {"ask_clarification"})
    block_decisions: Set[str] = field(default_factory=lambda: {"abstain", "veto"})
    fail_closed: bool = True

    def action_for(self, decision: str) -> str:
        decision = str(decision or "").strip().lower()
        if decision in self.execute_decisions:
            return EXECUTE
        if decision in self.warning_decisions:
            return EXECUTE_WITH_WARNING
        if decision in self.ask_decisions:
            return ASK_USER
        if decision in self.block_decisions:
            return BLOCK
        return BLOCK if self.fail_closed else ASK_USER

    def to_dict(self) -> Dict[str, object]:
        return {
            "execute_decisions": sorted(self.execute_decisions),
            "warning_decisions": sorted(self.warning_decisions),
            "ask_decisions": sorted(self.ask_decisions),
            "block_decisions": sorted(self.block_decisions),
            "fail_closed": self.fail_closed,
        }


DEFAULT_EXECUTION_POLICY = ExecutionPolicy()


__all__ = [
    "ASK_USER",
    "BLOCK",
    "DEFAULT_EXECUTION_POLICY",
    "EXECUTE",
    "EXECUTE_WITH_WARNING",
    "ExecutionPolicy",
]
