"""Causal Core adapters for CausalGate.

The causal_core package exposes stable facades over existing backend modules.
Identification wraps SCM-ID; Estimation provides a lightweight stdlib-first
boundary for existing/supplied effect estimates and CSV diagnostics.
"""

from .identification import (
    IdentificationEngine,
    IdentificationQuery,
    IdentificationResult,
    identify_effect,
    identify_many,
)
from .estimation import (
    EstimationEngine,
    EstimationQuery,
    EstimationResult,
    estimate_effect,
    estimate_many as estimate_many_effects,
)
from .counterfactual import (
    CounterfactualEngine,
    CounterfactualQuery,
    CounterfactualResult,
    compare_actions,
    compare_many as compare_many_actions,
)

__all__ = [
    "IdentificationEngine",
    "IdentificationQuery",
    "IdentificationResult",
    "identify_effect",
    "identify_many",
    "EstimationEngine",
    "EstimationQuery",
    "EstimationResult",
    "estimate_effect",
    "estimate_many_effects",
    "CounterfactualEngine",
    "CounterfactualQuery",
    "CounterfactualResult",
    "compare_actions",
    "compare_many_actions",
]
