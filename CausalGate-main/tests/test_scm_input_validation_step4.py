from __future__ import annotations

import json
from pathlib import Path

import cli
from scm_parts.input_validator import validate_scm_input_file, validate_scm_input_payload


def test_scm_validate_parser_accepts_command():
    args = cli.build_parser().parse_args([
        "scm-validate",
        "--scm-input",
        "examples/scm_templates/scm_input.template.generic.json",
        "--data",
        "data.csv",
    ])
    assert args.scm_input.endswith("scm_input.template.generic.json")
    assert args.func.__name__ == "_cmd_scm_validate"


def test_scm_input_templates_pass_structural_validation():
    root = Path(__file__).resolve().parents[1]
    template_dir = root / "examples" / "scm_templates"
    templates = sorted(template_dir.glob("scm_input.template.*.json"))
    assert templates
    for path in templates:
        report = validate_scm_input_file(path, data_path=str(root / "data.csv"))
        assert report["ok"], (path.name, report["issues"])
        assert report["query_count"] >= 1
        assert report["edge_count"] >= 1


def test_scm_input_validator_rejects_unknown_query_treatment():
    payload = {
        "schema_version": "causalgate.scm_input.v1",
        "nodes": [
            {"id": "action", "role": "treatment", "observed": True},
            {"id": "harm", "role": "outcome", "observed": True},
        ],
        "edges": [["action", "harm"]],
        "queries": [{"id": "q_bad", "treatment": "missing_action", "outcome": "harm"}],
        "assumptions": [{"id": "a_reviewed", "status": "required"}],
        "structural_equations": {"action": "f(U_action)", "harm": "f(action, U_harm)"},
        "exogenous": {"U_action": {"observed": False}, "U_harm": {"observed": False}},
        "data_path": "data.csv",
        "safety_policy": {"require_identification": True},
    }
    report = validate_scm_input_payload(payload)
    assert not report["ok"]
    assert "query_treatment_unknown" in {i["code"] for i in report["issues"] if i["severity"] == "error"}


def test_scm_input_validator_detects_cycles():
    payload = {
        "schema_version": "causalgate.scm_input.v1",
        "nodes": [
            {"id": "a", "role": "treatment", "observed": True},
            {"id": "b", "role": "outcome", "observed": True},
        ],
        "edges": [["a", "b"], ["b", "a"]],
        "queries": [{"id": "q_ab", "treatment": "a", "outcome": "b"}],
        "assumptions": [{"id": "a_reviewed", "status": "required"}],
        "structural_equations": {"a": "f(b, U_a)", "b": "f(a, U_b)"},
        "exogenous": {"U_a": {"observed": False}, "U_b": {"observed": False}},
        "data_path": "data.csv",
        "safety_policy": {"require_identification": True},
    }
    report = validate_scm_input_payload(payload)
    assert not report["ok"]
    assert "cycle_detected" in {i["code"] for i in report["issues"] if i["severity"] == "error"}


def test_scm_validate_command_writes_report(tmp_path):
    root = Path(__file__).resolve().parents[1]
    out = tmp_path / "validation.json"
    rc = cli.main([
        "scm-validate",
        "--scm-input",
        str(root / "examples" / "scm_templates" / "scm_input.template.generic.json"),
        "--data",
        str(root / "data.csv"),
        "--out",
        str(out),
    ])
    report = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0
    assert report["ok"] is True
    assert report["errors_count"] == 0
