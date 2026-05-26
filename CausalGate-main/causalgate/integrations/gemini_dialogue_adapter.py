from __future__ import annotations

"""Backward-compatible native JSON dialogue adapter.

The legacy Gemini-named public entry points are kept so existing callers do not
break, but this module does not call Gemini. Generic automatic runs intentionally
produce only physics/mechanistic-science or mathematical conjecture candidates.
"""

from dataclasses import asdict, dataclass, field
import json
import os
import random
import re
from typing import Any, Callable, Dict, Mapping, Optional

from causalgate.scientific.hypothesis_discovery_agent import generate_hypothesis
from causalgate.scientific.llm_dialogue import run_llm_dialogue

GeminiTransport = Callable[[str, Mapping[str, str], Mapping[str, Any], float], Mapping[str, Any]]

_HYPOTHESIS_FAMILIES = [
    {"family": "quantum_and_photonics", "domain": "mechanistic_physics", "exposures": ["laser detuning", "cavity mirror reflectivity", "single-photon pump power", "magnetic field strength", "qubit drive amplitude", "optical lattice depth"], "outcomes": ["photon-count correlation", "resonance linewidth", "qubit dephasing rate", "interference fringe visibility", "transition probability", "spectral peak shift"], "populations": ["cryogenic optical cavity setups", "superconducting qubit devices", "trapped-ion experiments", "single-photon interferometers", "ultracold atom systems"], "protocol": "laboratory"},
    {"family": "materials_and_condensed_matter", "domain": "mechanistic_physics", "exposures": ["thin-film annealing temperature", "lattice strain", "dopant concentration", "magnetic field strength", "sample thickness", "gate voltage"], "outcomes": ["electrical conductivity", "critical temperature", "magnetoresistance", "phonon scattering rate", "surface defect density", "Hall coefficient"], "populations": ["semiconductor thin films", "2D material devices", "superconducting samples", "magnetic nanostructures", "metamaterial arrays"], "protocol": "laboratory"},
    {"family": "plasma_and_fields", "domain": "mechanistic_physics", "exposures": ["plasma density", "radio-frequency drive power", "magnetic confinement strength", "gas pressure", "electric field gradient", "ion beam energy"], "outcomes": ["ion energy distribution", "plasma confinement time", "electron temperature", "instability growth rate", "emission spectral intensity", "particle flux"], "populations": ["low-temperature plasma chambers", "magnetized plasma devices", "ion-beam test stands", "laboratory discharge tubes", "fusion-relevant plasma simulations"], "protocol": "laboratory"},
    {"family": "fluid_and_thermal_physics", "domain": "mechanistic_physics", "exposures": ["Reynolds number", "boundary-layer roughness", "temperature gradient", "fluid viscosity", "acoustic forcing frequency", "channel geometry"], "outcomes": ["turbulence onset threshold", "heat-transfer coefficient", "vortex shedding frequency", "pressure-drop scaling", "mixing efficiency", "thermal boundary-layer thickness"], "populations": ["wind-tunnel flows", "microfluidic channels", "heated convection cells", "pipe-flow experiments", "computational fluid-dynamics simulations"], "protocol": "laboratory"},
    {"family": "astrophysics_and_gravity", "domain": "mechanistic_physics", "exposures": ["stellar metallicity", "magnetic field topology", "orbital eccentricity", "dark-matter halo concentration", "accretion disk viscosity", "cosmic ray flux"], "outcomes": ["spectral line broadening", "flare frequency", "gravitational-wave waveform residual", "galaxy rotation-curve deviation", "disk luminosity variability", "particle shower rate"], "populations": ["stellar observation catalogs", "binary compact-object simulations", "galaxy survey samples", "cosmic-ray detector arrays", "accretion disk models"], "protocol": "observational_or_simulation"},
    {"family": "number_theory", "domain": "mathematical", "objects": ["integer sequences", "prime gaps", "modular residue classes", "Diophantine equations", "multiplicative functions", "continued fractions"], "properties": ["eventual boundedness", "density threshold behavior", "existence of counterexamples", "asymptotic growth constraints", "equidistribution under stated conditions", "factorization-pattern restrictions"], "scopes": ["positive integers", "square-free integers", "large prime-indexed subsequences", "bounded-degree polynomial families", "coprime integer pairs"]},
    {"family": "graph_theory_and_combinatorics", "domain": "mathematical", "objects": ["sparse graphs", "planar graph families", "hypergraph matchings", "random graph processes", "edge-colored graphs", "finite lattice paths"], "properties": ["chromatic-number bounds", "extremal edge-count thresholds", "Hamiltonian-cycle existence", "matching-size lower bounds", "forbidden-substructure constraints", "enumeration recurrences"], "scopes": ["finite simple graphs", "bounded-degree graph classes", "large-n asymptotic regimes", "uniform hypergraphs", "minor-closed families"]},
    {"family": "analysis_and_dynamical_systems", "domain": "mathematical", "objects": ["nonlinear recurrence relations", "Fourier-series coefficients", "compact-operator spectra", "ordinary differential equation flows", "ergodic transformations", "Sobolev-space functions"], "properties": ["stability under perturbation", "convergence-rate bounds", "existence and uniqueness", "spectral-gap estimates", "regularity thresholds", "invariant-measure constraints"], "scopes": ["bounded domains", "smooth initial conditions", "compact metric spaces", "parameterized operator families", "weak-solution regimes"]},
    {"family": "geometry_and_topology", "domain": "mathematical", "objects": ["compact manifolds", "simplicial complexes", "knot invariants", "metric spaces", "minimal surfaces", "algebraic varieties"], "properties": ["classification constraints", "curvature-bound implications", "homology-group restrictions", "embedding-obstruction criteria", "rigidity under deformation", "singularity-structure bounds"], "scopes": ["low-dimensional cases", "orientable compact spaces", "bounded-curvature settings", "finite triangulations", "smooth deformation classes"]},
]

_PHYSICS_QUALIFIERS = [
    "under controlled laboratory boundary conditions",
    "using calibrated instrumentation and uncertainty propagation",
    "across repeated experimental runs",
    "against a null physical baseline model",
    "with simulation-backed parameter sweeps",
    "under pre-registered apparatus settings",
]

_ASTROPHYSICS_QUALIFIERS = [
    "using calibrated survey selection functions",
    "with simulation-backed comparison models",
    "under observational catalog quality cuts",
    "against a null astrophysical baseline model",
    "with instrument-response and selection-effect controls",
    "across independent survey or simulation subsets",
]

_MATH_QUALIFIERS = [
    "with explicit definitions and boundary cases",
    "using proof search and counterexample search",
    "under stated axioms and assumptions",
    "with computational checks on finite cases",
    "through reduction to known lemmas or benchmark theorems",
    "with independent formal-verification hooks",
]

_GENERIC = {
    "genera e migliora una ipotesi scientifica",
    "genera e migliora un ipotesi scientifica",
    "genera una ipotesi scientifica",
    "genera un ipotesi scientifica",
    "generate and improve a scientific hypothesis",
    "generate a scientific hypothesis",
    "create and improve a scientific hypothesis",
    "create a scientific hypothesis",
}

_RECENT_AUTO_GOALS: list[str] = []


@dataclass
class GeminiDialogueAdapterConfig:
    api_key: str = ""
    model: str = "causalgate-native-json"
    base_url: str = ""
    timeout_seconds: float = 0.0
    min_steps: int = 6
    generation_config: Dict[str, Any] = field(default_factory=dict)

    @property
    def configured(self) -> bool:
        return False

    @classmethod
    def from_env(cls, prefix: str = "CAUSALGATE_GEMINI") -> "GeminiDialogueAdapterConfig":
        raw = os.getenv(f"{prefix}_MIN_STEPS") or os.getenv("CAUSALGATE_DEMO_MAX_STEPS") or "6"
        try:
            min_steps = max(1, min(25, int(raw)))
        except Exception:
            min_steps = 6
        return cls(min_steps=min_steps)

    def safe_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["api_key"] = ""
        data["native_json_mode"] = True
        return data


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _boolish(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _intish(value: Any, default: int, minimum: int = 1, maximum: int = 25) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _goal(payload: Mapping[str, Any]) -> str:
    return _clean(payload.get("goal") or payload.get("research_goal") or payload.get("objective") or payload.get("claim"))


def _is_generic(goal: str) -> bool:
    normalized = re.sub(r"[^a-z0-9àèéìòù]+", " ", goal.lower()).strip()
    if not normalized or normalized in _GENERIC:
        return True
    if any(marker in normalized for marker in (" su ", " on ", " about ", " riguardo ", "->", "→")):
        return False
    words = set(normalized.split())
    instruction_words = {"genera", "generate", "crea", "create", "migliora", "improve", "ipotesi", "hypothesis", "scientifica", "scientific", "valuta", "review"}
    return bool(words) and words.issubset(instruction_words)


def _compose_scientific_goal(rng: random.Random) -> Dict[str, str]:
    family = rng.choice(_HYPOTHESIS_FAMILIES)
    domain = family.get("domain", "mechanistic_physics")
    if domain == "mathematical":
        obj = rng.choice(family["objects"])
        prop = rng.choice(family["properties"])
        scope = rng.choice(family["scopes"])
        qualifier = rng.choice(_MATH_QUALIFIERS)
        statement = f"{prop} for {obj} in {scope} {qualifier}"
        return {"goal": f"mathematical conjecture: {statement}", "family": family["family"], "domain": domain, "exposure": obj, "outcome": prop, "population": scope, "qualifier": qualifier, "object": obj, "property": prop, "scope": scope, "mathematical_statement": statement}

    exposure = rng.choice(family["exposures"])
    outcome = rng.choice(family["outcomes"])
    population = rng.choice(family["populations"])
    protocol = family.get("protocol", "laboratory")
    qualifier = rng.choice(_ASTROPHYSICS_QUALIFIERS if protocol == "observational_or_simulation" else _PHYSICS_QUALIFIERS)
    return {"goal": f"{exposure} -> {outcome} in {population} {qualifier}", "family": family["family"], "domain": domain, "protocol": protocol, "exposure": exposure, "outcome": outcome, "population": population, "qualifier": qualifier}


def _choose_scientific_goal() -> Dict[str, str]:
    rng = random.SystemRandom()
    selected = _compose_scientific_goal(rng)
    for _ in range(24):
        candidate = _compose_scientific_goal(rng)
        if candidate["goal"] not in _RECENT_AUTO_GOALS:
            selected = candidate
            break
    _RECENT_AUTO_GOALS.append(selected["goal"])
    del _RECENT_AUTO_GOALS[:-50]
    return selected


def _payload_for_native_discovery(payload: Mapping[str, Any]) -> Dict[str, Any]:
    data = dict(payload)
    original = _goal(data)
    if _is_generic(original):
        selected = _choose_scientific_goal()
        data["goal"] = selected["goal"]
        data["research_goal"] = selected["goal"]
        if selected.get("domain") == "mechanistic_physics":
            data["treatment"] = selected["exposure"]
            data["outcome"] = selected["outcome"]
            data["domain"] = "mechanistic_physics"
        elif selected.get("domain") == "mathematical":
            data["domain"] = "mathematical"
            data["mathematical_statement"] = selected.get("mathematical_statement", selected["goal"])
        meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        meta["original_generic_goal"] = original
        meta["auto_selected_scientific_goal"] = selected["goal"]
        meta["auto_hypothesis_generator"] = "dynamic_combinatorial_v3_physics_math_only"
        meta["auto_hypothesis_components"] = selected
        data["metadata"] = meta
    return data


def _payload_with_min_steps(payload: Mapping[str, Any], min_steps: int) -> Dict[str, Any]:
    data = dict(payload)
    requested = _intish(data.get("max_steps") or data.get("max_iterations"), min_steps)
    data["max_steps"] = max(requested, min_steps)
    data["max_iterations"] = data["max_steps"]
    return data


class GeminiDialogueAdapter:
    def __init__(self, config: GeminiDialogueAdapterConfig, *, transport: Optional[GeminiTransport] = None) -> None:
        self.config = config
        self.transport = transport

    def __call__(self, context: Mapping[str, Any]) -> Dict[str, Any]:
        return {}


class GeminiGoalNormalizer:
    def __init__(self, config: GeminiDialogueAdapterConfig, *, transport: Optional[GeminiTransport] = None) -> None:
        self.config = config
        self.transport = transport

    def normalize(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        data = _payload_for_native_discovery(payload)
        return {"language_normalization": {"needs_clarification": False, "research_goal": _goal(data), "user_intent": "generate_hypothesis"}}


class GeminiLanguageRenderer:
    def __init__(self, config: GeminiDialogueAdapterConfig, *, transport: Optional[GeminiTransport] = None) -> None:
        self.config = config
        self.transport = transport

    def render(self, reviewed_result: Mapping[str, Any]) -> Dict[str, Any]:
        return {}


def build_gemini_goal_normalization_prompt(payload: Mapping[str, Any]) -> str:
    return json.dumps({"native_json_mode": True, "payload": _as_dict(payload)}, ensure_ascii=False)


def build_gemini_dialogue_prompt(context: Mapping[str, Any]) -> str:
    return json.dumps({"native_json_mode": True, "context": _as_dict(context)}, ensure_ascii=False)


def build_gemini_language_render_prompt(result: Mapping[str, Any]) -> str:
    return json.dumps({"native_json_mode": True, "result": _as_dict(result)}, ensure_ascii=False)


def make_gemini_dialogue_adapter_from_env(prefix: str = "CAUSALGATE_GEMINI") -> None:
    return None


def run_gemini_llm_dialogue(payload: Mapping[str, Any], *, prefix: str = "CAUSALGATE_GEMINI") -> Dict[str, Any]:
    config = GeminiDialogueAdapterConfig.from_env(prefix=prefix)
    discovery_payload = _payload_for_native_discovery(payload)
    discovery = generate_hypothesis(discovery_payload)
    hypothesis = _as_dict(discovery.get("hypothesis"))
    dialogue_payload = _payload_with_min_steps({**discovery_payload, "hypothesis": hypothesis, "llm_actor": "causalgate_native_hypothesis_agent", "auto_expand": _boolish(discovery_payload.get("auto_expand"), True), "agent_repair": _boolish(discovery_payload.get("agent_repair"), True)}, config.min_steps)
    result = run_llm_dialogue(dialogue_payload, llm_adapter=None, enable_identification=_boolish(dialogue_payload.get("enable_identification"), True))
    result.setdefault("metadata", {})
    result["metadata"].update({"native_hypothesis_agent": True, "external_llm_used": False, "gemini_disabled": True, "gemini_role": "disabled", "output_format": "json_only", "discovery_patch": discovery.get("discovery_patch", {}), "auto_hypothesis_generator": discovery_payload.get("metadata", {}).get("auto_hypothesis_generator", ""), "auto_hypothesis_components": discovery_payload.get("metadata", {}).get("auto_hypothesis_components", {})})
    result["native_discovery"] = discovery
    return result


def run_native_json_hypothesis_dialogue(payload: Mapping[str, Any]) -> Dict[str, Any]:
    return run_gemini_llm_dialogue(payload)


__all__ = ["GeminiDialogueAdapter", "GeminiDialogueAdapterConfig", "GeminiGoalNormalizer", "GeminiLanguageRenderer", "GeminiTransport", "build_gemini_dialogue_prompt", "build_gemini_goal_normalization_prompt", "build_gemini_language_render_prompt", "make_gemini_dialogue_adapter_from_env", "run_gemini_llm_dialogue", "run_native_json_hypothesis_dialogue"]
