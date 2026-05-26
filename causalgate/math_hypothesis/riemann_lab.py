from __future__ import annotations

"""Small deterministic examples for RH-adjacent math-hypothesis critique."""

from typing import Dict


def riemann_overclaim_example() -> Dict[str, object]:
    return {
        "claim_id": "step99-riemann-overclaim-demo",
        "title": "Alleged proof of the Riemann Hypothesis",
        "problem_name": "Riemann Hypothesis",
        "claim": "I solved and proved the Riemann Hypothesis by a new symmetry of the zeta function.",
        "claim_level": "formal_proof_claimed",
        "definitions": ["zeta(s) denotes the Riemann zeta function after analytic continuation"],
        "proof_sketch": "A symmetry argument suggests non-trivial zeros should lie on the critical line.",
        "formal_system": "Lean4",
        "metadata": {"demo": "step99"},
    }


def finite_identity_example() -> Dict[str, object]:
    return {
        "claim_id": "step99-finite-identity-demo",
        "title": "Finite binomial identity proof obligation",
        "problem_name": "Binomial identity",
        "claim": "For natural n, sum_{k=0}^n binom(n,k)=2^n.",
        "claim_level": "proof_sketch_only",
        "definitions": ["n is a natural number", "binom(n,k) is the binomial coefficient"],
        "formal_statement": "theorem sum_choose_eq_two_pow (n : Nat) : (Finset.range (n+1)).sum (fun k => Nat.choose n k) = 2^n := by",
        "lemmas": ["Use the binomial theorem with x=1 and y=1"],
        "proof_sketch": "Apply the binomial theorem and simplify.",
        "formal_system": "Lean4",
        "metadata": {"demo": "step99"},
    }


__all__ = ["riemann_overclaim_example", "finite_identity_example"]
