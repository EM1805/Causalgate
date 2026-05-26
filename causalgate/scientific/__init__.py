"""Scientific hypothesis layer for CausalGate.

This layer is separate from the agent action gate. It evaluates scientific
claims as hypothesis candidates and returns REVISE / TEST_MORE / BLOCK /
FINAL_CANDIDATE without allowing overclaiming.
"""

from .hypothesis_contract import ScientificHypothesisPackage, normalize_dag, normalize_scientific_hypothesis
from .claim_levels import (
    ScientificClaimLevel,
    CLAIM_LEVELS,
    normalize_claim_level,
    claim_level_payload,
    max_allowed_level_from_evidence,
    clamp_requested_claim_level,
    claim_level_audit,
)
from .hypothesis_veto import HypothesisVeto, HypothesisVetoResult, evaluate_hypothesis
from .falsification_policy import FalsificationAssessment, FalsificationPolicy, assess_falsification
from .evidence_requirements import EvidenceRequirementPlan, infer_evidence_requirements
from .revision_protocol import build_revision_protocol
from .hypothesis_expansion import EXPANSION_STATES, HypothesisExpansionEngine, HypothesisExpansionResult, expand_hypothesis
from .hypothesis_repair_agent import HypothesisRepairAgent, HypothesisRepairResult, repair_hypothesis
from .hypothesis_discovery_agent import HypothesisDiscoveryAgent, HypothesisDiscoveryResult, generate_hypothesis
from .tool_planner import PlannedToolCall, ScientificToolPlan, plan_scientific_tools
from .literature_sources import LiteratureRecord, search_scientific_literature
from .llm_dialogue import (
    DIALOGUE_TERMINAL_STATUSES,
    LLMAdapter,
    LLMDialogueOrchestrator,
    LLMDialogueResult,
    LLMDialogueTurn,
    run_llm_dialogue,
)
from .research_loop import ScientificResearchLoop, ResearchStepResult, run_research_step
from .research_cycle import ScientificResearchCycle, ResearchCycleResult, run_research_cycle
from .scientific_ledger import ScientificLedger, ScientificLedgerEvent, append_scientific_ledger_event, read_scientific_ledger
from .agent_state import NativeScientificAgentState, native_agent_safety_boundary
from .agent_router import NativeAgentRoute, route_next_step
from .native_agent import NativeScientificAgent, NativeScientificAgentResult, run_native_scientific_agent
from .langgraph_agent import (
    LangGraphScientificAgentResult,
    build_langgraph_scientific_graph,
    default_safety_boundary,
    langgraph_available,
    prepare_scientific_agent_state,
    run_langgraph_scientific_agent,
    run_stdlib_scientific_agent,
)

__all__ = [
    "ScientificHypothesisPackage",
    "ScientificClaimLevel",
    "CLAIM_LEVELS",
    "normalize_claim_level",
    "claim_level_payload",
    "max_allowed_level_from_evidence",
    "clamp_requested_claim_level",
    "claim_level_audit",
    "HypothesisVeto",
    "HypothesisVetoResult",
    "evaluate_hypothesis",
    "FalsificationAssessment",
    "FalsificationPolicy",
    "assess_falsification",
    "EvidenceRequirementPlan",
    "infer_evidence_requirements",
    "build_revision_protocol",
    "EXPANSION_STATES",
    "HypothesisExpansionEngine",
    "HypothesisExpansionResult",
    "expand_hypothesis",
    "HypothesisRepairAgent",
    "HypothesisRepairResult",
    "repair_hypothesis",
    "HypothesisDiscoveryAgent",
    "HypothesisDiscoveryResult",
    "generate_hypothesis",
    "PlannedToolCall",
    "ScientificToolPlan",
    "plan_scientific_tools",
    "LiteratureRecord",
    "search_scientific_literature",
    "DIALOGUE_TERMINAL_STATUSES",
    "LLMAdapter",
    "LLMDialogueOrchestrator",
    "LLMDialogueResult",
    "LLMDialogueTurn",
    "run_llm_dialogue",
    "normalize_dag",
    "normalize_scientific_hypothesis",
    "ScientificResearchLoop",
    "ResearchStepResult",
    "run_research_step",
    "ScientificResearchCycle",
    "ResearchCycleResult",
    "run_research_cycle",
    "ScientificLedger",
    "ScientificLedgerEvent",
    "append_scientific_ledger_event",
    "read_scientific_ledger",
    "NativeScientificAgentState",
    "native_agent_safety_boundary",
    "NativeAgentRoute",
    "route_next_step",
    "NativeScientificAgent",
    "NativeScientificAgentResult",
    "run_native_scientific_agent",
    "LangGraphScientificAgentResult",
    "build_langgraph_scientific_graph",
    "default_safety_boundary",
    "langgraph_available",
    "prepare_scientific_agent_state",
    "run_langgraph_scientific_agent",
    "run_stdlib_scientific_agent",
]
