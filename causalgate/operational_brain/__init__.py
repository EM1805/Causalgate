"""Operational Brain facade package.

Step 2 adds the online orchestrator that evaluates multiple LLM/agent
candidate actions through the DecisionGate and selects the safest useful next
action.
"""

from .orchestrator import BrainRun, OperationalBrain, run_operational_brain
from causalgate.contracts import ActionPackage, DecisionPackage
from causalgate.gate import DecisionGate

__all__ = [
    "ActionPackage",
    "BrainRun",
    "DecisionGate",
    "DecisionPackage",
    "OperationalBrain",
    "run_operational_brain",
]
