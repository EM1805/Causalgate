from pathlib import Path

import pytest

import cli


@pytest.mark.core
def test_run_parser_accepts_skip_discovery_policy():
    args = cli.build_parser().parse_args([
        "run",
        "--data",
        "data.csv",
        "--out-dir",
        "out",
        "--discovery",
        "skip",
    ])
    assert args.discovery == "skip"
    assert args.skip_discovery is False


@pytest.mark.core
def test_skip_discovery_alias_resolves_to_skip_policy():
    args = cli.build_parser().parse_args([
        "run",
        "--data",
        "data.csv",
        "--out-dir",
        "out",
        "--skip-discovery",
    ])
    assert cli._resolve_discovery_policy(args) == "skip"


@pytest.mark.core
def test_skip_discovery_stage_does_not_require_discovery_outputs(tmp_path):
    args = cli.build_parser().parse_args([
        "run",
        "--data",
        "data.csv",
        "--out-dir",
        str(tmp_path / "out"),
        "--skip-discovery",
    ])
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    stage = cli._run_discovery_stage(args)
    assert stage["status"] == "skipped"
    assert stage["policy"] == "skip"
    assert stage["reason"] == "user_requested_skip_discovery"


@pytest.mark.core
def test_auto_discovery_reuses_existing_fresh_bridge_artifact(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    data = tmp_path / "data.csv"
    data.write_text("date,A,B\n2026-01-01,1,2\n", encoding="utf-8")
    bridge = out / "discovery_estimation_bridge.csv"
    bridge.write_text("source,target,lag\nA,B,1\n", encoding="utf-8")
    args = cli.build_parser().parse_args([
        "run",
        "--data",
        str(data),
        "--out-dir",
        str(out),
        "--discovery",
        "auto",
    ])
    cli._write_discovery_reuse_manifest(
        args,
        ["--data", str(data), "--out-dir", str(out)],
        [str(bridge)],
    )

    stage = cli._run_discovery_stage(args)

    assert stage["status"] == "skipped"
    assert stage["reason"] == "existing_discovery_artifacts_fresh_for_current_inputs"
    assert stage["freshness_reason"] == "discovery_reuse_manifest_matches_current_inputs"
    assert str(bridge) in stage["existing_artifacts"]
