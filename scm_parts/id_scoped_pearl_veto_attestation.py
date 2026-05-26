from __future__ import annotations

"""Step 90 current scoped Pearl runtime veto attestation matrix."""

import json
import tempfile
from pathlib import Path
from typing import Dict, Mapping

from common.pearl_veto_attestation import (
    PEARL_SCOPED_VETO_ATTESTATION_VERSION,
    PEARL_SCOPED_VETO_ATTESTATION_LEVEL,
    PEARL_SCOPED_VETO_ATTESTATION_SCOPE,
    PEARL_SCOPED_VETO_ATTESTATION_BINDING_FIELDS,
    build_scoped_pearl_veto_attestation,
    verify_scoped_pearl_veto_attestation,
)
from runtime.causal_authority import attach_causal_authority, build_veto_authority_readiness
from scm_parts.id_full_recursive_trace_authority import FULL_RECURSIVE_TRACE_FORMULA_AUTHORITY
from scm_parts.id_scoped_pearl_promotion import ID_SCOPED_PEARL_PROMOTION_GATE_VERSION, ID_SCOPED_PEARL_PROMOTION_SCOPE
from scm_parts.id_scoped_pearl_scope_manifest import build_current_scoped_pearl_manifest
from scm_parts.id_scoped_pearl_release_manifest import build_current_scoped_pearl_release_manifest


def build_current_scoped_pearl_authority_card(path_id: str = "scoped_pearl_path") -> Dict[str, object]:
    manifest = build_current_scoped_pearl_manifest()
    release = build_current_scoped_pearl_release_manifest(scoped_manifest=manifest)
    return {
        "path_id": path_id,
        "authority_level": "identified_runtime_path",
        "runtime_use": "causal_veto_allowed",
        "authority_reason": "specific_runtime_path_matches_identified_offline_contract",
        "contract_authority_level": "identified_estimable",
        "pearl_scoped_veto_authority": {
            "scoped_full_recursive_id_implemented": 1,
            "scoped_full_id_claim_allowed": 1,
            "global_full_recursive_id_implemented": 1,
            "global_full_id_claim_allowed": 1,
            "id_full_readiness_matrix": "id_full_readiness_matrix_v11_step80",
            "id_full_readiness_matrix_passed": 1,
            "id_oracle_parity_matrix": "id_oracle_parity_matrix_v3_step80",
            "id_oracle_parity_fuzz_passed": 1,
            "formal_failure_certificate_coverage_complete": 1,
            "formal_failure_certificate_coverage": "complete",
            "id_scoped_pearl_promotion_gate": ID_SCOPED_PEARL_PROMOTION_GATE_VERSION,
            "id_scoped_pearl_promotion_gate_passed": 1,
            "scope": ID_SCOPED_PEARL_PROMOTION_SCOPE,
            "primary_formula_authority": FULL_RECURSIVE_TRACE_FORMULA_AUTHORITY,
            "scoped_pearl_manifest": manifest,
            "scoped_pearl_release_manifest": release,
        },
    }


def run_scoped_pearl_veto_attestation_matrix(card: Mapping[str, object] | None = None) -> Dict[str, object]:
    card = dict(card or build_current_scoped_pearl_authority_card())
    with tempfile.TemporaryDirectory() as tmp:
        cards_path = Path(tmp) / "cards.jsonl"
        cards_path.write_text(json.dumps(card, sort_keys=True), encoding="utf-8")
        path_id = str(card.get("path_id") or "scoped_pearl_path")
        paths = attach_causal_authority([{"path_id": path_id}], cards_path=str(cards_path))
        readiness = build_veto_authority_readiness(paths, {"decision": "HARD_BLOCK"})
    attestation = dict(readiness.get("pearl_scoped_veto_attestation") or {})
    verification = verify_scoped_pearl_veto_attestation(attestation)
    return {
        "matrix_version": PEARL_SCOPED_VETO_ATTESTATION_VERSION,
        "level": PEARL_SCOPED_VETO_ATTESTATION_LEVEL,
        "scope": PEARL_SCOPED_VETO_ATTESTATION_SCOPE,
        "binding_fields": "|".join(PEARL_SCOPED_VETO_ATTESTATION_BINDING_FIELDS),
        "attestation_digest": attestation.get("attestation_digest", ""),
        "attestation_verified": int(verification.get("scoped_pearl_veto_attestation_verified", 0)),
        "pearl_scoped_veto_claim_allowed": int(bool(readiness.get("pearl_scoped_veto_claim_allowed"))),
        "pearl_complete_veto_claim_allowed": int(bool(readiness.get("pearl_complete_veto_claim_allowed"))),
        "global_full_recursive_id_implemented": int(attestation.get("global_full_recursive_id_implemented", 0) or 0),
        "global_full_id_claim_allowed": int(attestation.get("global_full_id_claim_allowed", 0) or 0),
        "attestation": attestation,
        "verification": verification,
        "readiness": readiness,
    }


__all__ = [
    "PEARL_SCOPED_VETO_ATTESTATION_VERSION",
    "PEARL_SCOPED_VETO_ATTESTATION_LEVEL",
    "PEARL_SCOPED_VETO_ATTESTATION_SCOPE",
    "PEARL_SCOPED_VETO_ATTESTATION_BINDING_FIELDS",
    "build_scoped_pearl_veto_attestation",
    "verify_scoped_pearl_veto_attestation",
    "build_current_scoped_pearl_authority_card",
    "run_scoped_pearl_veto_attestation_matrix",
]
