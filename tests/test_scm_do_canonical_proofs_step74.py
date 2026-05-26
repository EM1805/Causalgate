import json

from scm_parts.admg import admg_from_edges
from scm_parts.do_proof_engine import bounded_do_proof
from scm_parts.id_full import full_id
from scm_parts.do_canonical_proofs import DO_CANONICAL_PROOF_VERSION


def test_step74_backdoor_template_finds_adjustment_and_records_formula():
    g = admg_from_edges(["Z", "X", "Y"], [("Z", "X"), ("Z", "Y"), ("X", "Y")])
    result = bounded_do_proof(g, "X", "Y")
    payload = result.to_dict()
    assert result.status == "canonical_backdoor_template_proof_audit_only"
    assert result.authority == "audit_only"
    assert payload["terminal_observational"] == 1
    meta = payload["metadata"]["canonical_template"]
    assert meta["template_version"] == DO_CANONICAL_PROOF_VERSION
    assert meta["proof_family"] == "canonical_backdoor"
    assert meta["adjustment_set"] == ["Z"]
    assert meta["observational_formula"] == "sum_{Z} P(Y|X,Z) * P(Z)"
    assert meta["full_id_claim_allowed"] == 0


def test_step74_frontdoor_template_fires_when_backdoor_is_not_available():
    g = admg_from_edges(["X", "Z", "Y"], [("X", "Z"), ("Z", "Y")], [("X", "Y")])
    result = bounded_do_proof(g, "X", "Y")
    payload = result.to_dict()
    assert result.status == "canonical_frontdoor_template_proof_audit_only"
    meta = payload["metadata"]["canonical_template"]
    assert meta["proof_family"] == "canonical_frontdoor"
    assert meta["mediators"] == ["Z"]
    assert "sum_{Z}" in meta["observational_formula"]
    assert "P(Z|X)" in meta["observational_formula"]
    assert payload["terminal_observational"] == 1


def test_step74_unmediated_confounding_stays_unproven():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    result = bounded_do_proof(g, "X", "Y")
    assert result.status in {"search_exhausted_audit_only", "bounded_rewrite_progress_audit_only"}
    assert result.terminal_observational == 0
    assert "canonical_template" not in result.to_dict().get("metadata", {})


def test_step74_full_id_carries_canonical_do_template_metadata_without_authority_promotion():
    g = admg_from_edges(["Z", "X", "Y"], [("Z", "X"), ("Z", "Y"), ("X", "Y")])
    row = full_id(g, ["X"], ["Y"]).to_dict()
    assert row["do_proof_status"] == "canonical_backdoor_template_proof_audit_only"
    assert row["do_proof_authority"] == "audit_only"
    assert row["full_id_claim_allowed"] == 1
    proof_json = json.loads(row["do_proof_json"])
    assert proof_json["metadata"]["canonical_template"]["proof_family"] == "canonical_backdoor"
    assert proof_json["metadata"]["canonical_template"]["adjustment_set"] == ["Z"]
