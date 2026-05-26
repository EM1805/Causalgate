"""CausalGate public API.

CausalGate is a causal firewall for AI agents.  The default import path is kept
small and product-oriented: create a firewall, evaluate an agent action, receive
PASS / REVIEW / HARD_BLOCK plus causal-authority evidence and an audit report.
"""

from causalgate.agent_firewall import AgentActionFirewall, AgentFirewallResult, evaluate_tool_call
from causalgate.authority import CausalAuthorityResult, score_causal_authority
from causalgate.evidence import CausalEvidence
from causalgate.reports import render_markdown_report, write_json_report, write_markdown_report
from causalgate.demo import run_product_demo

AgentCausalFirewall = AgentActionFirewall
CausalGateResult = AgentFirewallResult

__version__ = "0.6.1.demo-polish"

__all__ = [
    "AgentActionFirewall",
    "AgentCausalFirewall",
    "AgentFirewallResult",
    "CausalGateResult",
    "CausalEvidence",
    "CausalAuthorityResult",
    "score_causal_authority",
    "render_markdown_report",
    "write_json_report",
    "write_markdown_report",
    "run_product_demo",
    "evaluate_tool_call",
    "__version__",
]
