import csv
import json
from pathlib import Path

from causalgate.agent import CausalGateAgent, DiscoveryEvidenceAdapter, ToolRegistry, ToolSpec
from causalgate.agent.evidence_reader import AgentEvidenceReader
from causalgate.contracts import DecisionPackage


def _write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_action_registry(path: Path, actions):
    path.write_text(json.dumps({"actions": actions}, indent=2, sort_keys=True), encoding="utf-8")


class StubBrain:
    def __init__(self, selected):
        self.selected = selected
        self.last_payload = None

    def run(self, payload):
        self.last_payload = payload

        class Run:
            def __init__(self, selected, payload):
                self.selected = selected
                self.payload = payload

            def to_dict(self):
                return {
                    "mode": "test",
                    "selected": self.selected.to_dict(),
                    "evaluated_actions": [self.selected.to_dict()],
                    "input_package": self.payload,
                    "notes": [],
                }

        return Run(self.selected, payload)


class StubGuard:
    def __init__(self):
        self.calls = []

    def guard_tool_call(self, action_payload, *, tool_executor=None, tool_args=None, tool_name="", **kwargs):
        self.calls.append({"payload": action_payload, "tool_name": tool_name})
        return type("Result", (), {"to_dict": lambda self_: {
            "status": "executed" if tool_executor else "permitted_not_executed",
            "executed": bool(tool_executor),
            "blocked": False,
            "needs_user_confirmation": False,
            "tool_name": tool_name,
            "tool_result": tool_executor(dict(tool_args or {})) if tool_executor else None,
            "decision_package": {"decision": "allow"},
        }})()


def test_discovery_adapter_reads_edges_as_hypothesis_only(tmp_path):
    out = tmp_path / "out"
    _write_csv(out / "edges.csv", [
        {
            "source": "price_discount",
            "target": "conversion_rate",
            "lag": "1",
            "strength": "0.64",
            "method": "pcmci",
        }
    ])

    bundle = DiscoveryEvidenceAdapter(output_dir=out).read({
        "action_name": "price_discount",
        "treatment": "price_discount",
        "outcome": "conversion_rate",
    })

    assert bundle.matched_discovery_hypotheses
    row = bundle.matched_discovery_hypotheses[0]
    assert row["evidence_status"] == "hypothesis_only"
    assert row["allowed_use"] == "recommendation_only"
    assert row["usable_for_autonomous_action"] is False
    assert row["recommended_next_validation"] == "estimation_or_scm_id"


def test_evidence_reader_includes_discovery_but_marks_it_weak(tmp_path):
    out = tmp_path / "out"
    _write_csv(out / "insights_level2.csv", [
        {
            "source": "page_speed",
            "target": "conversion_rate",
            "lag": "1",
            "strength": "0.71",
            "stability_score": "0.8",
        }
    ])

    bundle = AgentEvidenceReader(output_dir=out).read({
        "action_name": "page_speed",
        "treatment": "page_speed",
        "outcome": "conversion_rate",
    })

    assert bundle.matched_discovery_hypotheses
    assert bundle.evidence_tier == "weak"
    assert bundle.usable_for_autonomous_action is False
    assert "discovery_hypothesis" in bundle.evidence_present
    assert bundle.decision_hints["autonomous_execution"] == "discovery_hypothesis_only"
    assert any("Discovery-only" in warning for warning in bundle.evidence_warnings)


def test_agent_blocks_discovery_only_autonomous_tool_execution(tmp_path):
    out = tmp_path / "out"
    _write_csv(out / "edges.csv", [
        {
            "source": "price_discount",
            "target": "conversion_rate",
            "lag": "1",
            "strength": "0.64",
            "method": "pcmci",
        }
    ])
    action_registry = tmp_path / "action_registry.json"
    _write_action_registry(action_registry, {
        "price_discount": {
            "action_type": "state_change",
            "domain": "general",
            "risk_level": "low",
            "autonomous_allowed": True,
            "allowed_modes": ["general_agent"],
            "requires_approval": False,
        }
    })

    calls = []

    def change_price(args):
        calls.append(args)
        return {"changed": True}

    registry = ToolRegistry([ToolSpec(name="price_discount", executor=change_price)])
    brain = StubBrain(DecisionPackage(decision="allow", selected_action="price_discount"))
    guard = StubGuard()

    result = CausalGateAgent(
        brain=brain,
        tool_guard=guard,
        tool_registry=registry,
        evidence_output_dir=out,
        action_registry_path=action_registry,
    ).run(
        "Abbassa il prezzo del 20%.",
        candidate_actions=[
            {
                "action_name": "price_discount",
                "candidate_action": "price_discount",
                "action_type": "state_change",
                "risk_level": "low",
                "treatment": "price_discount",
                "outcome": "conversion_rate",
            }
        ],
        execute_tools=True,
    ).to_dict()

    assert result["status"] == "discovery_review_required"
    assert result["executed"] is False
    assert result["blocked"] is True
    assert result["needs_user_confirmation"] is True
    assert result["evidence_tier"] == "weak"
    assert result["evidence_bundle"]["matched_discovery_hypotheses"]
    assert result["registry_policy_result"]["status"] == "registry_policy_allowed"
    assert calls == []
    assert guard.calls == []
