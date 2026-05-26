from causalgate.agent.discovery_adapter import DiscoveryEvidenceAdapter


def test_discovery_adapter_prefers_layered_paths_before_legacy(tmp_path):
    out = tmp_path / "out"
    (out / "discovery").mkdir(parents=True)
    (out / "ranking").mkdir(parents=True)
    (out / "discovery" / "pcmci_links.csv").write_text(
        "source,target,lag,discovery_strength\nprice,conversion,1,0.72\n",
        encoding="utf-8",
    )
    (out / "edges.csv").write_text(
        "source,target,lag,discovery_strength\nlegacy_price,legacy_conversion,1,0.33\n",
        encoding="utf-8",
    )

    adapter = DiscoveryEvidenceAdapter(output_dir=out)
    resolved = [path.relative_to(out).as_posix() for path in adapter.paths]

    assert resolved[0] == "discovery/pcmci_links.csv"
    assert "edges.csv" in resolved
    assert resolved.index("discovery/pcmci_links.csv") < resolved.index("edges.csv")


def test_discovery_adapter_preserves_layered_source_key_and_safety(tmp_path):
    out = tmp_path / "out"
    (out / "discovery").mkdir(parents=True)
    (out / "discovery" / "pcmci_links.csv").write_text(
        "source,target,lag,discovery_strength\nprice,conversion,1,0.72\n",
        encoding="utf-8",
    )

    bundle = DiscoveryEvidenceAdapter(output_dir=out).read(
        {"treatment": "price", "outcome": "conversion"}
    ).to_dict()

    assert bundle["usable_for_autonomous_action"] is False
    assert bundle["matched_discovery_hypotheses"]
    row = bundle["matched_discovery_hypotheses"][0]
    assert row["_agent_discovery_source_key"] == "discovery/pcmci_links.csv"
    assert row["_agent_discovery_source_layer"] == "discovery_layered"
    assert row["requires_downstream_validation"] is True


def test_discovery_adapter_source_keys_do_not_collide(tmp_path):
    out = tmp_path / "out"
    (out / "ranking").mkdir(parents=True)
    (out / "ranking" / "insights_level2.csv").write_text(
        "source,target,lag\nprice,conversion,1\n",
        encoding="utf-8",
    )
    (out / "insights_level2.csv").write_text(
        "source,target,lag\nlegacy_price,legacy_conversion,1\n",
        encoding="utf-8",
    )

    bundle = DiscoveryEvidenceAdapter(output_dir=out).read(
        {"treatment": "price", "outcome": "conversion"}
    ).to_dict()

    assert "ranking/insights_level2.csv" in bundle["source_files"]
    assert "insights_level2.csv" in bundle["source_files"]
    assert len(bundle["source_files"]) == 2
