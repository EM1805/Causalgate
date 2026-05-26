from scm_parts.edge_authority import authority_from_row, build_scm_edge_row


def test_discovery_estimation_bridge_not_upgraded_by_conditioning_set():
    row = {
        "source": "price",
        "target": "conversion",
        "__source_artifact": "out/discovery_estimation_bridge.csv",
        "conditioning_set_used": "traffic,weekday",
    }
    auth = authority_from_row(row)
    assert auth["edge_authority_level"] == "bridge_candidate"
    assert auth["edge_source_layer"] == "discovery_bridge"
    assert "EXPLICIT_DISCOVERY_ESTIMATION_BRIDGE" in auth["authority_reason_codes"]


def test_generic_conditioning_set_alone_stays_raw_seed():
    row = {
        "source": "price",
        "target": "conversion",
        "conditioning_set_used": "traffic,weekday",
    }
    auth = authority_from_row(row)
    assert auth["edge_authority_level"] == "raw_discovery_seed_only"
    assert auth["eligible_for_identification"] is False


def test_pcmci_scm_bridge_artifact_keeps_structural_prior_authority():
    row = {
        "source": "price",
        "target": "conversion",
        "__source_artifact": "out/discovery/pcmci_scm_bridge.csv",
        "conditioning_set_used": "traffic,weekday",
    }
    auth = authority_from_row(row)
    assert auth["edge_authority_level"] == "pcmci_scm_structural_prior"
    assert auth["edge_source_layer"] == "pcmci_scm_bridge"


def test_build_edge_row_preserves_safe_bridge_authority():
    out = build_scm_edge_row(
        {
            "source": "price",
            "target": "conversion",
            "__source_artifact": "out/discovery_estimation_bridge.csv",
            "conditioning_set_used": "traffic,weekday",
        }
    )
    assert out is not None
    assert out["edge_authority_level"] == "bridge_candidate"
    assert out["conditioning_set_used"] == "traffic,weekday"
