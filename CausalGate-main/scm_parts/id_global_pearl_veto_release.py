from __future__ import annotations

"""Step 95 Global Pearl-complete veto runtime release matrix.

Step 94 makes the backend Global Full-ID claim green.  Step 95 connects that
claim to runtime veto wording by requiring a causal authority card that carries
the Step-94 controlled flip evidence and by emitting a digest-bound runtime
attestation for the top veto path.
"""

import json
import tempfile
from pathlib import Path
from typing import Dict, Mapping

from common.pearl_global_veto_attestation import (
    PEARL_GLOBAL_VETO_ATTESTATION_VERSION,
    PEARL_GLOBAL_VETO_ATTESTATION_LEVEL,
    PEARL_GLOBAL_VETO_ATTESTATION_SCOPE,
    PEARL_GLOBAL_VETO_ATTESTATION_BINDING_FIELDS,
    build_global_pearl_veto_attestation,
    verify_global_pearl_veto_attestation,
)
from runtime.causal_authority import attach_causal_authority, build_veto_authority_readiness
from scm_parts.id_full_promotion_gate import ID_FULL_PROMOTION_GATE_VERSION
from scm_parts.id_global_full_id_controlled_flip import ID_GLOBAL_FULL_ID_CONTROLLED_FLIP_VERSION

GLOBAL_PEARL_FORMULA_AUTHORITY = "full_recursive_id_canonical_formula_authority"


def build_current_global_pearl_authority_card(path_id: str = "global_pearl_path") -> Dict[str, object]:
    return {
        "path_id": path_id,
        "authority_level": "identified_runtime_path",
        "runtime_use": "causal_veto_allowed",
        "authority_reason": "specific_runtime_path_matches_identified_offline_contract",
        "contract_authority_level": "identified_estimable",
        "pearl_veto_authority": {
            "full_recursive_id_implemented": 1,
            "full_id_claim_allowed": 1,
            "id_full_readiness_matrix": "id_full_readiness_matrix_v11_step80",
            "id_full_readiness_matrix_passed": 1,
            "id_oracle_parity_matrix": "id_oracle_parity_matrix_v3_step80",
            "id_oracle_parity_fuzz_passed": 1,
            "formal_failure_certificate_coverage_complete": 1,
            "formal_failure_certificate_coverage": "complete",
            "id_full_promotion_gate": ID_FULL_PROMOTION_GATE_VERSION,
            "id_full_promotion_gate_passed": 1,
            "id_global_full_id_controlled_flip": ID_GLOBAL_FULL_ID_CONTROLLED_FLIP_VERSION,
            "id_global_full_id_controlled_flip_passed": 1,
            "global_full_id_controlled_flip_allowed": 1,
            "primary_formula_authority": GLOBAL_PEARL_FORMULA_AUTHORITY,
            "identification_status": "identified",
            "pearl_claim_source": "step95_global_pearl_runtime_release_card",
        },
    }


def run_global_pearl_veto_release_matrix(card: Mapping[str, object] | None = None) -> Dict[str, object]:
    card = dict(card or build_current_global_pearl_authority_card())
    with tempfile.TemporaryDirectory() as tmp:
        cards_path = Path(tmp) / "cards.jsonl"
        cards_path.write_text(json.dumps(card, sort_keys=True), encoding="utf-8")
        path_id = str(card.get("path_id") or "global_pearl_path")
        paths = attach_causal_authority([{"path_id": path_id}], cards_path=str(cards_path))
        readiness = build_veto_authority_readiness(paths, {"decision": "HARD_BLOCK"})
    attestation = dict(readiness.get("pearl_complete_veto_attestation") or {})
    verification = verify_global_pearl_veto_attestation(attestation)
    return {
        "matrix_version": PEARL_GLOBAL_VETO_ATTESTATION_VERSION,
        "level": PEARL_GLOBAL_VETO_ATTESTATION_LEVEL,
        "scope": PEARL_GLOBAL_VETO_ATTESTATION_SCOPE,
        "binding_fields": "|".join(PEARL_GLOBAL_VETO_ATTESTATION_BINDING_FIELDS),
        "global_pearl_veto_release_allowed": int(bool(readiness.get("pearl_complete_veto_claim_allowed"))),
        "pearl_complete_veto_claim_allowed": int(bool(readiness.get("pearl_complete_veto_claim_allowed"))),
        "causal_veto_claim_allowed": int(bool(readiness.get("causal_veto_claim_allowed"))),
        "attestation_digest": attestation.get("attestation_digest", ""),
        "attestation_verified": int(verification.get("global_pearl_veto_attestation_verified", 0)),
        "id_full_promotion_gate_passed": int(attestation.get("id_full_promotion_gate_passed", 0) or 0),
        "id_global_full_id_controlled_flip_passed": int(attestation.get("id_global_full_id_controlled_flip_passed", 0) or 0),
        "full_recursive_id_implemented": int(attestation.get("full_recursive_id_implemented", 0) or 0),
        "full_id_claim_allowed": int(attestation.get("full_id_claim_allowed", 0) or 0),
        "primary_formula_authority": attestation.get("primary_formula_authority", ""),
        "attestation": attestation,
        "verification": verification,
        "readiness": readiness,
    }


__all__ = [
    "PEARL_GLOBAL_VETO_ATTESTATION_VERSION",
    "PEARL_GLOBAL_VETO_ATTESTATION_LEVEL",
    "PEARL_GLOBAL_VETO_ATTESTATION_SCOPE",
    "PEARL_GLOBAL_VETO_ATTESTATION_BINDING_FIELDS",
    "GLOBAL_PEARL_FORMULA_AUTHORITY",
    "build_global_pearl_veto_attestation",
    "verify_global_pearl_veto_attestation",
    "build_current_global_pearl_authority_card",
    "run_global_pearl_veto_release_matrix",
]
