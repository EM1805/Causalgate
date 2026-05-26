from __future__ import annotations

"""Canonical schema for mathematical hypothesis dialogue claims.

This module is intentionally conservative and stdlib-only.  It does not try to
prove mathematics.  It normalizes an LLM's mathematical claim into a reviewable
contract so downstream veto, recommendation, and proof-obligation modules can
classify the claim without allowing proof overclaim.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping


MATH_CLAIM_LEVELS = {
    "informal_idea",
    "conjecture_candidate",
    "proof_sketch_only",
    "numerical_evidence_only",
    "proof_obligation_candidate",
    "formal_proof_claimed",
    "formally_verified_theorem",
    "counterexample_candidate",
}


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Iterable) and not isinstance(value, (Mapping, bytes, bytearray)):
        return list(value)
    return [value]


def _str_list(value: Any) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in _as_list(value):
        text = _clean_str(item)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _normalized_level(value: Any) -> str:
    raw = _clean_str(value, "conjecture_candidate").lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "proved": "formal_proof_claimed",
        "proven": "formal_proof_claimed",
        "proof": "formal_proof_claimed",
        "theorem": "formal_proof_claimed",
        "verified": "formally_verified_theorem",
        "lean_verified": "formally_verified_theorem",
        "numeric": "numerical_evidence_only",
        "numerical": "numerical_evidence_only",
        "experiment": "numerical_evidence_only",
        "sketch": "proof_sketch_only",
        "conjecture": "conjecture_candidate",
        "idea": "informal_idea",
    }
    raw = aliases.get(raw, raw)
    return raw if raw in MATH_CLAIM_LEVELS else "conjecture_candidate"


@dataclass
class MathClaimPackage:
    claim_id: str = ""
    title: str = ""
    claim: str = ""
    domain: str = "mathematics"
    problem_name: str = ""
    claim_type: str = "conjecture"
    claim_level: str = "conjecture_candidate"
    definitions: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    proof_sketch: str = ""
    proof_steps: List[str] = field(default_factory=list)
    lemmas: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    formal_system: str = ""
    formal_statement: str = ""
    lean_code: str = ""
    proof_checker_result: Dict[str, Any] = field(default_factory=dict)
    numerical_evidence: List[str] = field(default_factory=list)
    counterexamples: List[str] = field(default_factory=list)
    known_obstructions: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    requested_output: str = "review"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.domain = _clean_str(self.domain, "mathematics")
        self.problem_name = _clean_str(self.problem_name)
        self.claim_type = _clean_str(self.claim_type, "conjecture")
        self.claim_level = _normalized_level(self.claim_level)
        self.definitions = _str_list(self.definitions)
        self.assumptions = _str_list(self.assumptions)
        self.proof_steps = _str_list(self.proof_steps)
        self.lemmas = _str_list(self.lemmas)
        self.dependencies = _str_list(self.dependencies)
        self.numerical_evidence = _str_list(self.numerical_evidence)
        self.counterexamples = _str_list(self.counterexamples)
        self.known_obstructions = _str_list(self.known_obstructions)
        self.references = _str_list(self.references)
        self.proof_checker_result = _as_dict(self.proof_checker_result)
        self.metadata = _as_dict(self.metadata)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def missing_core_items(self) -> List[str]:
        missing: List[str] = []
        if not _clean_str(self.claim):
            missing.append("claim")
        if not self.definitions:
            missing.append("definitions")
        if not _clean_str(self.formal_statement):
            missing.append("formal_statement")
        if self.claim_level in {"formal_proof_claimed", "formally_verified_theorem"} and not (_clean_str(self.lean_code) or self.proof_checker_result):
            missing.append("formal_proof_or_checker_attestation")
        return missing


def normalize_math_claim(payload: Mapping[str, Any] | MathClaimPackage | None) -> MathClaimPackage:
    if isinstance(payload, MathClaimPackage):
        return payload
    data = _as_dict(payload)
    if isinstance(data.get("math_claim"), Mapping):
        data = _as_dict(data["math_claim"])
    if isinstance(data.get("hypothesis"), Mapping):
        # Allow reuse of the existing scientific-hypothesis wrapper.
        data = {**_as_dict(data["hypothesis"]), **{k: v for k, v in data.items() if k != "hypothesis"}}
    return MathClaimPackage(
        claim_id=_clean_str(data.get("claim_id") or data.get("hypothesis_id") or data.get("id")),
        title=_clean_str(data.get("title")),
        claim=_clean_str(data.get("claim") or data.get("statement")),
        domain=_clean_str(data.get("domain"), "mathematics"),
        problem_name=_clean_str(data.get("problem_name") or data.get("problem")),
        claim_type=_clean_str(data.get("claim_type") or data.get("hypothesis_kind"), "conjecture"),
        claim_level=_normalized_level(data.get("claim_level") or data.get("requested_claim_level")),
        definitions=_str_list(data.get("definitions")),
        assumptions=_str_list(data.get("assumptions")),
        proof_sketch=_clean_str(data.get("proof_sketch") or data.get("proof") or data.get("argument")),
        proof_steps=_str_list(data.get("proof_steps") or data.get("steps")),
        lemmas=_str_list(data.get("lemmas")),
        dependencies=_str_list(data.get("dependencies")),
        formal_system=_clean_str(data.get("formal_system")),
        formal_statement=_clean_str(data.get("formal_statement") or data.get("lean_statement")),
        lean_code=_clean_str(data.get("lean_code") or data.get("formal_proof")),
        proof_checker_result=_as_dict(data.get("proof_checker_result") or data.get("verification_result")),
        numerical_evidence=_str_list(data.get("numerical_evidence") or data.get("computational_evidence")),
        counterexamples=_str_list(data.get("counterexamples")),
        known_obstructions=_str_list(data.get("known_obstructions")),
        references=_str_list(data.get("references") or data.get("evidence_refs")),
        requested_output=_clean_str(data.get("requested_output"), "review"),
        metadata=_as_dict(data.get("metadata")),
    )


__all__ = ["MATH_CLAIM_LEVELS", "MathClaimPackage", "normalize_math_claim"]
