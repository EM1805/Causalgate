from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from causalgate.agent_firewall.gateway import AgentActionFirewall, AgentFirewallResult
from causalgate.agent_firewall.policy import PASS, REVIEW, HARD_BLOCK
from causalgate.evidence import CausalEvidence
from causalgate.reports import write_html_report, write_json_report, write_markdown_report


@dataclass(frozen=True)
class DemoCase:
    """One product demo scenario for CausalGate."""

    case_id: str
    title: str
    action: Dict[str, Any]
    evidence: Dict[str, Any] | None = None
    require_causal_evidence: bool = False
    expected_decision: str | None = None
    explanation: str = ""


@dataclass(frozen=True)
class DemoCaseResult:
    case_id: str
    title: str
    decision: str
    execution_action: str
    authority_score: int | None
    authority_level: str
    report_json: str
    report_md: str
    report_html: str
    summary: str
    expected_decision: str | None = None
    matched_expected: bool | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DemoRunResult:
    product: str = "CausalGate"
    demo: str = "agent_causal_firewall_showcase"
    output_dir: str = ""
    cases: list[DemoCaseResult] = field(default_factory=list)
    summary_json: str = ""
    summary_md: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product": self.product,
            "demo": self.demo,
            "output_dir": self.output_dir,
            "summary_json": self.summary_json,
            "summary_md": self.summary_md,
            "cases": [case.to_dict() for case in self.cases],
        }


def _repo_path(*parts: str) -> Path:
    return Path(__file__).resolve().parents[1].joinpath(*parts)


def _read_json(path: str | Path) -> Dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def load_showcase_cases() -> list[DemoCase]:
    """Return the three-case product demo: PASS, REVIEW, HARD_BLOCK."""

    marketing_action = _read_json(_repo_path("examples", "actions", "marketing_spend_increase.json"))
    weak_evidence = _read_json(_repo_path("examples", "evidence", "marketing_weak_evidence.json"))
    strong_evidence = _read_json(_repo_path("examples", "evidence", "marketing_strong_evidence.json"))

    return [
        DemoCase(
            case_id="01_read_only_pass",
            title="Low-risk read-only action is allowed",
            action={
                "request_id": "demo-read-only-001",
                "action_name": "summarize_dashboard",
                "tool_name": "summarize_dashboard",
                "action_type": "read",
                "target_resource": "metrics-dashboard",
                "risk_level": "low",
                "environment": "staging",
                "approval_present": False,
                "rollback_available": True,
            },
            evidence=None,
            require_causal_evidence=False,
            expected_decision=PASS,
            explanation="Read-only, low-risk actions do not need causal authority evidence.",
        ),
        DemoCase(
            case_id="02_weak_causal_claim_block",
            title="High-impact action with weak causal evidence is blocked",
            action=marketing_action,
            evidence=weak_evidence,
            require_causal_evidence=True,
            expected_decision=HARD_BLOCK,
            explanation="Correlation-only evidence is not enough for a high-impact spend change.",
        ),
        DemoCase(
            case_id="03_strong_evidence_review",
            title="Strong causal evidence routes high-impact action to review",
            action=marketing_action,
            evidence=strong_evidence,
            require_causal_evidence=True,
            expected_decision=REVIEW,
            explanation="Even strong evidence should not bypass approval for high-impact production actions.",
        ),
    ]


def _evaluate_case(firewall: AgentActionFirewall, case: DemoCase) -> AgentFirewallResult:
    action = dict(case.action)
    evidence = CausalEvidence.from_mapping(case.evidence) if case.evidence else None
    return firewall.evaluate(
        action=str(action.get("action_name") or action.get("candidate_action") or action.get("tool_name") or ""),
        tool_name=str(action.get("tool_name") or action.get("action_name") or ""),
        risk_level=str(action.get("risk_level") or action.get("trusted_runtime_context", {}).get("risk_level") or "unknown"),
        environment=str(action.get("environment") or action.get("trusted_runtime_context", {}).get("environment") or "unknown"),
        action_type=str(action.get("action_type") or action.get("trusted_runtime_context", {}).get("action_type") or "unknown"),
        target_resource=str(action.get("target_resource") or action.get("trusted_runtime_context", {}).get("target_resource") or ""),
        approval_present=bool(action.get("approval_present") or action.get("trusted_runtime_context", {}).get("approval_present", False)),
        rollback_available=bool(action.get("rollback_available") or action.get("trusted_runtime_context", {}).get("rollback_available", False)),
        trusted_runtime_context=dict(action.get("trusted_runtime_context") or {}),
        untrusted_llm_context=dict(action.get("untrusted_llm_context") or {}),
        request_id=action.get("request_id", ""),
        user_message=action.get("user_message", ""),
        treatment=str(action.get("treatment") or ""),
        outcome=str(action.get("outcome") or ""),
        causal_query=dict(action.get("causal_query") or {}),
        evidence=evidence,
        require_causal_evidence=bool(case.require_causal_evidence or action.get("require_causal_evidence", False)),
    )


def _render_summary_markdown(result: DemoRunResult) -> str:
    lines = [
        "# CausalGate 60-second product demo",
        "",
        "This demo shows the core product behavior: an AI agent proposes actions, CausalGate checks policy and causal authority, then returns `PASS`, `REVIEW`, or `HARD_BLOCK` with audit reports.",
        "",
        "| Case | Decision | Authority | Meaning |",
        "|---|---:|---:|---|",
    ]
    for case in result.cases:
        authority = "n/a" if case.authority_score is None else f"{case.authority_score}/100 ({case.authority_level})"
        lines.append(f"| {case.title} | `{case.decision}` | {authority} | {case.summary} |")
    lines.extend([
        "",
        "## Generated reports",
        "",
    ])
    for case in result.cases:
        lines.append(f"- `{case.case_id}`: `{case.report_md}`, `{case.report_json}` and `{case.report_html}`")
    lines.extend([
        "",
        "## Run it yourself",
        "",
        "```bash",
        "causalgate demo --out-dir out/demo",
        "```",
        "",
    ])
    return "\n".join(lines)


def run_product_demo(
    *,
    out_dir: str | Path = "out/demo",
    policy: str | Path | Mapping[str, Any] | None = None,
    enable_tool_guard: bool = False,
) -> DemoRunResult:
    """Run the CausalGate product showcase and write audit reports.

    ToolGuard is disabled by default for the demo so the output demonstrates the
    public firewall + causal-authority layer without requiring real tool
    executors. Production integrations can enable ToolGuard.
    """

    destination = Path(out_dir)
    destination.mkdir(parents=True, exist_ok=True)
    firewall = AgentActionFirewall(policy=policy, enable_tool_guard=enable_tool_guard)
    case_results: list[DemoCaseResult] = []

    for case in load_showcase_cases():
        result = _evaluate_case(firewall, case)
        case_dir = destination / case.case_id
        report_json = write_json_report(result, case_dir / "report.json")
        report_md = write_markdown_report(result, case_dir / "report.md")
        report_html = write_html_report(result, case_dir / "report.html")
        authority = dict(result.authority_evaluation or {})
        case_results.append(
            DemoCaseResult(
                case_id=case.case_id,
                title=case.title,
                decision=result.firewall_decision,
                execution_action=result.execution_action,
                authority_score=result.authority_score,
                authority_level=str(authority.get("authority_level") or "n/a"),
                report_json=report_json,
                report_md=report_md,
                report_html=report_html,
                summary=result.summary,
                expected_decision=case.expected_decision,
                matched_expected=(result.firewall_decision == case.expected_decision) if case.expected_decision else None,
            )
        )

    summary = DemoRunResult(output_dir=str(destination), cases=case_results)
    summary_json = destination / "summary.json"
    summary_md = destination / "summary.md"
    summary_json.write_text(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    summary = DemoRunResult(
        output_dir=str(destination),
        cases=case_results,
        summary_json=str(summary_json),
        summary_md=str(summary_md),
    )
    summary_md.write_text(_render_summary_markdown(summary), encoding="utf-8")
    return summary


__all__ = ["DemoCase", "DemoCaseResult", "DemoRunResult", "load_showcase_cases", "run_product_demo"]
