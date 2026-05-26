from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import cli
from scm_parts.builder import build_from_scm_input


@pytest.mark.core
def test_run_parser_accepts_explicit_scm_input():
    args = cli.build_parser().parse_args([
        "run",
        "--scm-input",
        "examples/scm_templates/scm_input.template.generic.json",
        "--data",
        "data.csv",
        "--out-dir",
        "out",
    ])
    assert args.scm_input.endswith("scm_input.template.generic.json")


@pytest.mark.core
def test_scm_input_makes_discovery_optional_in_auto_mode(tmp_path):
    args = cli.build_parser().parse_args([
        "run",
        "--scm-input",
        "examples/scm_templates/scm_input.template.generic.json",
        "--data",
        "data.csv",
        "--out-dir",
        str(tmp_path / "out"),
    ])
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    stage = cli._run_discovery_stage(args)
    assert stage["status"] == "skipped"
    assert stage["reason"] == "scm_input_supplied"


@pytest.mark.core
def test_build_from_scm_input_writes_queries_and_skips_exogenous_do_rows(tmp_path):
    root = Path(__file__).resolve().parents[1]
    scm_input = root / "examples" / "scm_templates" / "scm_input.template.agent_ai.json"
    out = tmp_path / "out"
    paths = build_from_scm_input(str(scm_input), out_dir=str(out), data_path=str(root / "data.csv"))

    graph = json.loads(Path(paths["scm_graph_json"]).read_text(encoding="utf-8"))
    assert graph["type"] == "scm_input_domain_prior"
    assert {q["id"] for q in graph["queries"]} >= {"q_action_harm_effect", "q_intensity_harm_effect"}

    audit = pd.read_csv(paths["id_algorithm_audit_csv"])
    assert "scm_query" in set(audit["audit_source"])
    assert "U_harm" not in set(audit["treatment"])

    edges = pd.read_csv(paths["scm_edges_csv"])
    assert "domain_scm_prior" in set(edges["edge_authority_level"])
    exogenous_edges = edges[edges["edge_kind"] == "exogenous_noise"]
    assert not exogenous_edges.empty
    assert set(exogenous_edges["eligible_for_identification"].astype(str).str.lower()) <= {"false", "0"}
