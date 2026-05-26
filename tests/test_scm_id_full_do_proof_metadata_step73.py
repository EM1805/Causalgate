import json

from scm_parts.admg import admg_from_edges
from scm_parts.id_full import full_id, ID_FULL_INTERFACE_VERSION
from scm_parts.id_status import id_capability_flags


def test_step73_full_id_attaches_bounded_do_proof_metadata_without_authority():
    graph = admg_from_edges(["X", "Y"], [("X", "Y")], [])
    result = full_id(graph, "X", "Y").to_dict()

    assert result["interface_version"] == ID_FULL_INTERFACE_VERSION
    assert result["identified"] is True
    assert result["full_id_claim_allowed"] == 1
    assert result["do_proof_authority"] == "audit_only"
    assert result["do_proof_engine_version"] == "do_proof_engine_bounded_v2_step74_canonical_templates"
    assert result["do_proof_status"] in {
        "search_exhausted_audit_only",
        "bounded_rewrite_progress_audit_only",
        "proof_found_observational_audit_only",
        "canonical_backdoor_template_proof_audit_only",
    }
    assert result["do_proof_terminal_formula"] == "P(Y|X)"
    assert result["do_proof_terminal_observational"] == 1

    proof = json.loads(result["do_proof_json"])
    assert proof["authority"] == "audit_only"
    assert proof["proof"]["query"]["formula"] == "P(Y|do(X))"
    assert proof["proof"]["query"]["metadata"]["source"] == "id_full_step74_metadata"


def test_step73_invalid_full_id_query_reports_do_proof_not_run():
    graph = admg_from_edges(["X", "Y"], [("X", "Y")], [])
    result = full_id(graph, ["X"], ["X"]).to_dict()

    assert result["identified"] is False
    assert result["identification_status"] == "invalid_full_id_query"
    assert result["do_proof_status"] == "not_run_invalid_query"
    assert result["do_proof_json"] == ""
    assert result["do_proof_reason_codes"] == "DO_PROOF_METADATA_NOT_RUN"


def test_step73_capability_flag_is_visible():
    flags = id_capability_flags()
    assert flags["id_full_do_proof_metadata_step73_implemented"] == 1
    assert flags["full_recursive_id_implemented"] == 1
