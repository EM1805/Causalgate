from __future__ import annotations

"""Deterministic CausalGate-native hypothesis discovery agent.

The discovery agent creates a structured *candidate* from a user goal without
using an external LLM. It is intentionally conservative: it generates a
reviewable ScientificHypothesisPackage, not evidence, proof, or final truth.
"""

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Dict, Iterable, List, Mapping, Tuple
from uuid import uuid4

from .hypothesis_contract import normalize_scientific_hypothesis


_MATH_TERMS = ("theorem", "proof", "prove", "dimostra", "teorema", "congettura", "conjecture", "lemma", "equation", "formula", "identity", "mathematical", "matematic")
_PHYSICS_TERMS = ("physics", "fisica", "quantum", "qubit", "photon", "photonic", "laser", "optical", "plasma", "magnetic", "magnet", "superconduct", "semiconductor", "phonon", "electron", "ion", "neutron", "particle", "astrophysical", "cosmic", "gravity", "gravitational", "fluid", "turbulence", "viscosity", "thermal", "temperature", "conductivity", "resonator", "cavity", "interferometer", "spectroscopy", "field strength", "wavelength", "frequency", "pressure", "strain", "material", "metamaterial", "galaxy", "stellar", "accretion", "survey")
_CAUSAL_TERMS = ("effect", "impact", "causes", "cause", "causal", "improve", "reduce", "increase", "decrease", "influenza", "causa", "migliora", "riduce", "aumenta", "diminuisce", "associated", "association", "linked", "relazione", "associato", "associazione")
_ABSURD_TERMS = ("absurd", "impossible", "magic", "telepathy", "astrology", "levitation", "unicorn", "assurdo", "magia", "telepatia", "impossibile")
_ASTRO_TERMS = ("galaxy", "stellar", "accretion", "cosmic", "gravitational", "darkmatter", "dark matter", "survey", "catalog", "waveform", "cosmicray", "cosmic ray")


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


def _title_case_variable(text: str, fallback: str) -> str:
    text = _clean_str(text)
    if not text:
        return fallback
    words = re.findall(r"[A-Za-z0-9]+", text)
    if not words:
        return fallback
    return "".join(w[:1].upper() + w[1:] for w in words)[:64]


# Terms that intentionally behave as prefixes/stems. Keep this list small:
# generic substring matching caused empirical prompts such as "improve" to match
# the math term "prove", and words such as "education"/"reaction" to match
# the physics term "ion".
_PREFIX_TERMS = {"superconduct", "matematic"}


def _term_pattern(term: str) -> str:
    escaped = re.escape(term.lower())
    if "\\ " in escaped:
        # Multi-word phrases should match as complete phrases, not substrings
        # inside longer tokens.
        return rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"
    if term.lower() in _PREFIX_TERMS:
        return rf"(?<![a-z0-9]){escaped}[a-z0-9_-]*(?![a-z0-9])"
    return rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    low = text.lower()
    return any(re.search(_term_pattern(term), low) for term in terms)


def _strip_math_prefix(statement: str) -> str:
    text = _clean_str(statement, "A mathematical conjecture may hold under specified assumptions.")
    return re.sub(r"^\s*(candidate\s+)?mathematical\s+conjecture\s*:\s*", "", text, flags=re.IGNORECASE).strip() or text


def _split_goal(goal: str) -> Tuple[str, str]:
    text = _clean_str(goal)
    arrow = re.search(r"(.+?)\s*(?:->|→|=>|causes?|affects?|influences?|impact[s]?|reduces?|improves?|increases?|decreases?|is associated with|associated with|is linked to|linked to)\s+(.+)", text, flags=re.IGNORECASE)
    if arrow:
        rhs = re.split(r"\s+in\s+|\s+under\s+|\s+using\s+|\s+with\s+|\s+against\s+|\s+across\s+", arrow.group(2), maxsplit=1, flags=re.IGNORECASE)[0]
        return _title_case_variable(arrow.group(1), "Treatment"), _title_case_variable(rhs, "Outcome")
    separators = [" to ", " on ", " and ", " e ", " su ", ":"]
    for sep in separators:
        if sep in text.lower():
            parts = re.split(re.escape(sep), text, maxsplit=1, flags=re.IGNORECASE)
            if len(parts) == 2:
                return _title_case_variable(parts[0], "Treatment"), _title_case_variable(parts[1], "Outcome")
    words = re.findall(r"[A-Za-z0-9]+", text)
    if len(words) >= 2:
        midpoint = max(1, len(words) // 2)
        return _title_case_variable(" ".join(words[:midpoint]), "Treatment"), _title_case_variable(" ".join(words[midpoint:]), "Outcome")
    return "Treatment", "Outcome"


def _physics_control_measurement(name: str) -> str:
    low = name.lower()
    if "temperature" in low:
        return "Control or record sample and ambient temperature; report thermal drift and uncertainty."
    if "pressure" in low or "vacuum" in low:
        return "Control or record chamber pressure/vacuum level and sensor uncertainty."
    if "geometry" in low or "alignment" in low:
        return "Record apparatus geometry/alignment and repeat alignment checks across runs."
    if "calibration" in low:
        return "Run calibration standards before/after the experiment and propagate calibration uncertainty."
    if "selection" in low or "survey" in low:
        return "Model survey selection effects, catalog completeness, and instrumental response."
    if "material" in low or "sample" in low:
        return "Record sample composition, preparation batch, and material characterization metadata."
    return f"Control or record {name} with calibrated instrumentation and uncertainty propagation."


def _measurement_for(name: str) -> str:
    low = name.lower()
    if "temperature" in low:
        return "Measured continuously with calibrated thermometry and logged before each experimental run."
    if "pressure" in low:
        return "Measured with calibrated pressure sensors and recorded with uncertainty estimates."
    if "field" in low or "magnetic" in low:
        return "Measured with calibrated field probes or instrument/model settings, including uncertainty checks."
    if "geometry" in low or "dimension" in low or "thickness" in low:
        return "Measured by instrument geometry, microscopy, profilometry, or manufacturer calibration records."
    if "calibration" in low:
        return "Measured using pre-run and post-run instrument calibration checks."
    return f"Measured before treatment with a documented baseline variable for {name}."


@dataclass
class HypothesisDiscoveryResult:
    hypothesis_id: str = ""
    hypothesis: Dict[str, Any] = field(default_factory=dict)
    discovery_patch: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HypothesisDiscoveryAgent:
    def generate(self, payload: Mapping[str, Any]) -> HypothesisDiscoveryResult:
        data = _as_dict(payload)
        goal = _clean_str(data.get("goal") or data.get("research_goal") or data.get("objective") or data.get("claim"), "Generate a scientific hypothesis.")
        supplied = _as_dict(data.get("hypothesis"))
        if supplied and supplied.get("claim"):
            hypothesis = normalize_scientific_hypothesis(supplied).to_dict()
            hypothesis.setdefault("metadata", {})["discovery_agent"] = "input_hypothesis_normalized_only"
            return HypothesisDiscoveryResult(hypothesis_id=_clean_str(hypothesis.get("hypothesis_id")), hypothesis=hypothesis, discovery_patch={"mode": "normalized_supplied_hypothesis", "claim_level_changed": False}, warnings=["A supplied hypothesis was normalized; no new scientific evidence was added."])

        treatment = _clean_str(data.get("treatment"))
        outcome = _clean_str(data.get("outcome"))
        if treatment and outcome:
            treatment = _title_case_variable(treatment, "Treatment")
            outcome = _title_case_variable(outcome, "Outcome")
        else:
            treatment, outcome = _split_goal(goal)
        domain, kind, domain_diagnostic = self._diagnose_domain(goal, data)
        if kind == "mathematical_conjecture":
            hypothesis = self._math_candidate(goal, domain, kind, domain_diagnostic, data)
        elif domain == "mechanistic_physics":
            hypothesis = self._physics_candidate(goal, treatment, outcome, domain, kind, domain_diagnostic, data)
        else:
            hypothesis = self._empirical_candidate(goal, treatment, outcome, domain, kind, domain_diagnostic, data)

        normalized = normalize_scientific_hypothesis(hypothesis).to_dict()
        for key, value in hypothesis.items():
            normalized.setdefault(key, value)
        return HypothesisDiscoveryResult(
            hypothesis_id=normalized["hypothesis_id"],
            hypothesis=normalized,
            discovery_patch={"mode": "native_deterministic_generation", "goal": goal, "detected_domain": domain, "claim_level_changed": False, "source": "causalgate.scientific.hypothesis_discovery_agent"},
            warnings=["Generated candidate is structural only; CausalGate veto must review it before use.", "No external evidence was invented or checked by the native discovery agent."],
        )

    def _diagnose_domain(self, goal: str, data: Mapping[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
        explicit = _clean_str(data.get("domain")).lower()
        if explicit in {"mathematical", "math"} or _contains_any(goal, _MATH_TERMS):
            return "mathematical", "mathematical_conjecture", {"detected_domain": "mathematical", "domain_mismatch": False, "reason": "The goal uses proof/conjecture/mathematical language; empirical causal controls are not forced."}
        if explicit in {"mechanistic_physics", "mechanistic_science", "physics"} or _contains_any(goal, _PHYSICS_TERMS):
            return "mechanistic_physics", "empirical_hypothesis", {"detected_domain": "mechanistic_physics", "domain_mismatch": False, "reason": "The goal uses physical-science language; the protocol emphasizes mechanism, measurement uncertainty, calibration/selection controls, replication, and simulation."}
        if _contains_any(goal, _ABSURD_TERMS):
            return "absurd_or_unsupported", "empirical_hypothesis", {"detected_domain": "absurd_or_unsupported", "domain_mismatch": False, "reason": "The mechanism appears implausible; only weak observable claims may be tested."}
        if _contains_any(goal, _CAUSAL_TERMS) or "->" in goal or "→" in goal:
            return "empirical_causal", "empirical_hypothesis", {"detected_domain": "empirical_causal", "domain_mismatch": False, "reason": "The goal asks about an empirical relation between measurable variables."}
        return "empirical_causal", "empirical_hypothesis", {"detected_domain": "empirical_causal", "domain_mismatch": False, "reason": "Defaulted to a weak empirical-causal candidate because two measurable variables can be specified."}

    def _math_candidate(self, goal: str, domain: str, kind: str, diagnostic: Mapping[str, Any], data: Mapping[str, Any]) -> Dict[str, Any]:
        hid = "H_native_math_" + uuid4().hex[:10]
        statement = _strip_math_prefix(data.get("mathematical_statement") or goal)
        return {
            "hypothesis_id": hid,
            "domain": domain,
            "hypothesis_kind": kind,
            "domain_diagnostic": dict(diagnostic),
            "claim": f"Candidate mathematical conjecture: {statement}",
            "claim_level": "hypothesis_only",
            "treatment": "",
            "outcome": "Truth status of the conjecture",
            "verification_protocol": {"type": "proof_or_counterexample", "steps": ["formal_statement_review", "counterexample_search", "proof_attempt_or_reduction_to_known_results", "independent_formal_or_computational_verification"]},
            "dag": {"nodes": ["Conjecture", "ProofOrCounterexample"], "directed_edges": [["Conjecture", "ProofOrCounterexample"]]},
            "assumptions": ["Definitions and axioms must be stated explicitly before proof review."],
            "mechanism_plausible": "Not applicable: this is a mathematical conjecture, not an empirical mechanism.",
            "confounders": [],
            "adjustment_set": [],
            "observed_confounder_measurements": {},
            "identification_strategy": "Mathematical proof/counterexample protocol; no empirical causal identification claim is made.",
            "estimation_plan": "Search for a proof, counterexample, and independent formal or computational verification where applicable.",
            "counterfactual_query": "",
            "measurable_predictions": ["A proof or counterexample search will either derive the statement from the stated axioms or find a concrete counterexample."],
            "falsification_tests": ["Find one valid counterexample satisfying the definitions but violating the conjectured conclusion."],
            "negative_control_tests": ["Verify the proof method fails on a deliberately false analogous statement."],
            "placebo_tests": ["Run symbolic or computational checks on known false and known true benchmark statements."],
            "sensitivity_checks": ["Check whether the conjecture depends on hidden assumptions, boundary cases, or changed definitions."],
            "data_requirements": ["Formal statement, definitions, axioms, boundary conditions, and candidate examples/counterexamples."],
            "external_evidence_quality": {"status": "not_applicable", "reason": "External empirical evidence is not the validation route for a mathematical conjecture."},
            "test_plan": "Conduct proof review, counterexample search, and independent verification before any stronger conclusion.",
            "evidence_refs": [],
            "metadata": {"generated_by": "causalgate.scientific.hypothesis_discovery_agent", "math_protocol": True, "mathematical_statement": statement},
        }

    def _physics_candidate(self, goal: str, treatment: str, outcome: str, domain: str, kind: str, diagnostic: Mapping[str, Any], data: Mapping[str, Any]) -> Dict[str, Any]:
        hid = "H_native_physics_" + uuid4().hex[:10]
        meta = _as_dict(data.get("metadata"))
        components = _as_dict(meta.get("auto_hypothesis_components"))
        protocol = _clean_str(components.get("protocol"), "observational_or_simulation" if _contains_any(goal, _ASTRO_TERMS) else "laboratory")
        if protocol == "observational_or_simulation":
            controls = _str_list(data.get("confounders") or data.get("controls")) or ["InstrumentCalibration", "SurveySelectionFunction", "CatalogCompleteness", "ModelBoundaryConditions"]
            claim = f"Variation in {treatment} may correspond to a measurable change in {outcome} within calibrated observational or simulation constraints and stated uncertainty."
            identification = "Observational/simulation-backed physical comparison with survey, instrument-response, selection-effect, and model-boundary controls: " + ", ".join(controls) + "."
            estimation = f"Estimate the response of {outcome} to variation in {treatment} using calibrated catalogs or simulations, uncertainty propagation, selection-function controls, and comparison against a null astrophysical baseline model."
            counterfactual = f"Compare expected {outcome} under model/intervention settings where {treatment}=perturbed versus baseline, holding survey selection, calibration, and boundary conditions fixed."
            prediction2 = f"The relationship should remain reproducible across independent catalog splits, simulations, or survey subsets after calibration and selection-effect controls."
            test_plan = "Analyze calibrated observations and/or validated simulations, compare against a null astrophysical model, propagate uncertainty, test selection effects, and require independent catalog/simulation replication before claim upgrade."
            simulation_plan = "Run parameter sweeps or forward simulations with stated boundary conditions, instrument response, and selection effects, then compare predicted response curves with calibrated observations."
        else:
            controls = _str_list(data.get("confounders") or data.get("controls")) or ["Temperature", "PressureOrVacuumLevel", "InstrumentCalibration", "SampleGeometryOrAlignment"]
            claim = f"Changing {treatment} may produce a measurable change in {outcome} under controlled apparatus conditions and within stated measurement uncertainty."
            identification = "Controlled physical experiment or simulation-backed comparison with apparatus controls: " + ", ".join(controls) + "."
            estimation = f"Estimate the response of {outcome} to controlled variation in {treatment} using repeated trials, calibration correction, uncertainty propagation, and model comparison against a null/no-change baseline."
            counterfactual = f"Compare expected {outcome} under controlled {treatment}=higher/perturbed versus {treatment}=baseline, holding apparatus controls and boundary conditions fixed."
            prediction2 = f"The response curve for {outcome} should be reproducible across independent runs after controlling temperature, pressure/vacuum, calibration, and geometry/alignment."
            test_plan = "Run controlled experiments or validated simulations, compare against a null/baseline physical model, propagate uncertainty, execute sham/negative-control tests, and require independent replication before claim upgrade."
            simulation_plan = "Build a simple theory-driven or numerical simulation using stated boundary conditions, then compare predicted response curves with measured data before treating the mechanism as supported."
        measurements = {z: _physics_control_measurement(z) for z in controls}
        mechanism = f"A candidate physical mechanism should link {treatment} to {outcome} through known conservation laws, field interactions, transport processes, material response, gravity, or wave/particle dynamics; the mechanism remains unvalidated until reproduced experimentally, observationally, or by simulation."
        return {
            "hypothesis_id": hid,
            "domain": domain,
            "hypothesis_kind": kind,
            "domain_diagnostic": dict(diagnostic),
            "claim": claim,
            "claim_level": "hypothesis_only",
            "treatment": treatment,
            "outcome": outcome,
            "dag": {"nodes": [treatment, outcome, *controls], "directed_edges": [[treatment, outcome], *[[z, treatment] for z in controls], *[[z, outcome] for z in controls]]},
            "assumptions": ["The manipulated or modeled physical quantity is measured or specified before the outcome measurement window.", "Calibration, environmental/catalog conditions, and boundary conditions are recorded for every run or dataset subset.", "The candidate mechanism respects known physical constraints and is not treated as established without replication.", "Uncertainty propagation is reported for all primary measurements or simulated quantities."],
            "mechanism_plausible": mechanism,
            "confounders": controls,
            "adjustment_set": controls,
            "observed_confounder_measurements": measurements,
            "identification_strategy": identification,
            "estimation_plan": estimation,
            "counterfactual_query": counterfactual,
            "measurable_predictions": [f"A controlled, modeled, or observed variation in {treatment} should produce a directionally specified, detectable change in {outcome} that exceeds noise, calibration, or selection uncertainty.", prediction2],
            "falsification_tests": [f"The observed or simulated change in {outcome} remains physically indistinguishable from the null/baseline model across controlled levels of {treatment}.", f"The apparent relationship between {treatment} and {outcome} disappears after calibration correction, environmental/catalog controls, or boundary-condition checks.", "A predicted scaling law, threshold, resonance, or monotonic trend fails under pre-specified boundary conditions."],
            "negative_control_tests": ["Vary a setting or catalog feature expected to be physically irrelevant and verify it does not reproduce the target response.", "Measure an outcome channel not predicted by the mechanism and verify no target-like response appears."],
            "placebo_tests": ["Run sham perturbation, blinded trigger trials, or label-randomized catalog/simulation comparisons where the nominal treatment is not physically applied.", "Randomize or permute treatment labels to check whether the response survives label-shuffling artifacts."],
            "sensitivity_checks": ["Repeat analysis with alternate calibration curves, noise models, and outlier rules.", "Check robustness across apparatus alignment, sample batch, survey selection, boundary-condition, and numerical-solver settings.", "Compare experimental/observational results against dimensional analysis, baseline theory, or simulation predictions."],
            "data_requirements": [f"Raw and processed measurements for {treatment}, {outcome}, and all physical controls.", "Calibration logs, sensor/instrument uncertainty, sampling rate or catalog selection, instrument settings, and environmental conditions.", "Sample/material characterization or catalog/model metadata, geometry/alignment records, and boundary-condition metadata.", "Pre-registered analysis plan, null model, uncertainty propagation method, and replication criteria.", *[f"{z}: {measurements[z]}" for z in controls]],
            "external_evidence_quality": {"status": "not_checked", "reason": "No external physics literature or independent replication evidence was checked by this deterministic generator."},
            "test_plan": test_plan,
            "simulation_plan": simulation_plan,
            "evidence_refs": [],
            "metadata": {"generated_by": "causalgate.scientific.hypothesis_discovery_agent", "source_goal": goal, "physics_protocol": True, "physics_protocol_type": protocol},
        }

    def _empirical_candidate(self, goal: str, treatment: str, outcome: str, domain: str, kind: str, diagnostic: Mapping[str, Any], data: Mapping[str, Any]) -> Dict[str, Any]:
        hid = "H_native_empirical_" + uuid4().hex[:10]
        confounders = _str_list(data.get("confounders")) or ["BaselineOutcome", "Age", "SocioeconomicStatus"]
        measurements = {z: _measurement_for(z) for z in confounders}
        mechanism = "The proposed mechanism is not accepted as plausible; only a weak observable association may be screened and should be expected to fail under controls." if domain == "absurd_or_unsupported" else f"A plausible mechanism should connect {treatment} to {outcome} through measurable pathways; this mechanism remains unvalidated."
        claim = f"Changes in {treatment} may be associated with directional changes in {outcome}, under stated assumptions and after adjusting for observed confounders."
        return {"hypothesis_id": hid, "domain": domain, "hypothesis_kind": kind, "domain_diagnostic": dict(diagnostic), "claim": claim, "claim_level": "hypothesis_only", "treatment": treatment, "outcome": outcome, "dag": {"nodes": [treatment, outcome, *confounders], "directed_edges": [[treatment, outcome], *[[z, treatment] for z in confounders], *[[z, outcome] for z in confounders]]}, "assumptions": ["Temporal order is defined so treatment/exposure is measured before the outcome window.", "All listed adjustment variables are measured before treatment or at baseline.", "No stronger causal or law-like claim is made without external validation."], "mechanism_plausible": mechanism, "confounders": confounders, "adjustment_set": confounders, "observed_confounder_measurements": measurements, "identification_strategy": "Back-door adjustment using observed confounders: " + ", ".join(confounders) + ".", "estimation_plan": f"Estimate the adjusted association/effect of {treatment} on {outcome} using a pre-specified regression or causal-estimation model with the adjustment set.", "counterfactual_query": f"Compare expected {outcome} under do({treatment}=higher/exposed) versus do({treatment}=lower/unexposed), holding the adjustment set fixed.", "measurable_predictions": [f"Within the pre-specified follow-up window, higher measured {treatment} is predicted to correspond to a directional, measurable change in {outcome} compared with the control/comparison condition, after adjustment."], "falsification_tests": [f"The adjusted association between {treatment} and {outcome} is null, reversed, or unstable across pre-specified model choices.", f"A future value of {treatment} predicts baseline {outcome}, suggesting leakage, reverse causality, or unmeasured confounding."], "negative_control_tests": ["A pre-specified outcome not plausibly affected by the treatment should show no adjusted association.", "A pre-specified exposure not plausibly related to the outcome should show no adjusted association."], "placebo_tests": ["A sham/permuted exposure label should not reproduce the target association.", "Future-treatment placebo: later exposure should not predict earlier outcome after baseline adjustment."], "sensitivity_checks": ["Repeat estimation with alternate functional forms and adjustment subsets.", "Assess robustness to unmeasured confounding using bounds or E-value-style sensitivity analysis."], "data_requirements": [f"Unit-level records for {treatment}, {outcome}, and all adjustment variables.", "Baseline measurement timestamp and follow-up outcome timestamp.", *[f"{z}: {measurements[z]}" for z in confounders]], "external_evidence_quality": {"status": "not_checked", "reason": "No external evidence was supplied or checked by this deterministic generator."}, "test_plan": "Run the empirical design, estimate the adjusted association/effect, report uncertainty, and execute falsification, negative-control, placebo/leakage, and sensitivity checks before claim upgrade.", "simulation_plan": "Optionally simulate data from the stated DAG to check whether the planned adjustment recovers the target effect under known assumptions.", "evidence_refs": [], "metadata": {"generated_by": "causalgate.scientific.hypothesis_discovery_agent", "source_goal": goal}}


def generate_hypothesis(payload: Mapping[str, Any]) -> Dict[str, Any]:
    return HypothesisDiscoveryAgent().generate(payload).to_dict()


__all__ = ["HypothesisDiscoveryAgent", "HypothesisDiscoveryResult", "generate_hypothesis"]
