
from __future__ import annotations

from runtime_env import configure_scientific_runtime
configure_scientific_runtime()


import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fs_utils import ensure_writable_dir, ensure_writable_parent, write_text_safe




def _default_out_dir_child(out_dir: str | os.PathLike, filename: str) -> str:
    return str(Path(out_dir) / filename)

def _default_scm_graph_path(out_dir: str | os.PathLike) -> str:
    return str(Path(out_dir) / "scm" / "scm_graph.json")

def _resolve_bridge_path(args: argparse.Namespace) -> str:
    explicit = getattr(args, "bridge", None)
    if explicit:
        return str(explicit)
    return _default_out_dir_child(args.out_dir, "discovery_estimation_bridge.csv")

def _resolve_scm_graph_path(args: argparse.Namespace) -> str:
    explicit = getattr(args, "graph", None)
    if explicit:
        return str(explicit)
    return _default_scm_graph_path(args.out_dir)

def _exists(path: Optional[os.PathLike | str]) -> bool:
    try:
        return bool(path) and Path(path).exists()
    except (OSError, TypeError, ValueError):
        return False


def _resolve_data_path(data: Optional[str | os.PathLike]) -> str:
    """Resolve relative data paths for direct zip/package-root and installed CLI runs."""
    if not data:
        return ""
    p = Path(data)
    if p.is_absolute() or p.exists():
        return str(p)
    root_candidate = Path(__file__).resolve().parent / p
    if root_candidate.exists():
        return str(root_candidate)
    return str(p)




_DISCOVERY_OPTIONAL_ARTIFACTS = (
    "discovery/pcmci_links.csv",
    "discovery/pcmci_scm_bridge.csv",
    "ranking/insights_level2.csv",
    "discovery_estimation_bridge.csv",
    "insights_level2.csv",
    "edges.csv",
)

_DISCOVERY_REUSE_MANIFEST = "discovery_reuse_manifest.json"
_DISCOVERY_REUSE_CONTRACT_VERSION = 1


def _artifact_nonempty(path: Path) -> bool:
    try:
        return path.exists() and path.stat().st_size > 0
    except OSError:
        return False


def _existing_discovery_artifacts(out_dir: str | os.PathLike) -> list[str]:
    out = Path(out_dir)
    found: list[str] = []
    for rel in _DISCOVERY_OPTIONAL_ARTIFACTS:
        path = out / rel
        if _artifact_nonempty(path):
            found.append(str(path))
    return found


def _safe_resolved_path(path: Optional[str | os.PathLike]) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).expanduser().resolve())
    except (OSError, TypeError, ValueError):
        return str(path)


def _file_sha256(path: Optional[str | os.PathLike]) -> str:
    if not path:
        return ""
    try:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return ""
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, TypeError, ValueError):
        return ""


def _discovery_reuse_manifest_path(out_dir: str | os.PathLike) -> Path:
    return Path(out_dir) / _DISCOVERY_REUSE_MANIFEST


def _effective_discovery_config_path(args: argparse.Namespace) -> str:
    explicit = getattr(args, "config", None)
    candidate = explicit if explicit else "pcb.json"
    if not candidate:
        return ""
    p = Path(candidate)
    if p.exists():
        return str(p)
    root_candidate = Path(__file__).resolve().parent / p
    if root_candidate.exists():
        return str(root_candidate)
    return str(candidate) if explicit else ""


def _discovery_reuse_signature(args: argparse.Namespace) -> dict[str, object]:
    data_path = str(getattr(args, "data", "") or "")
    config_path = _effective_discovery_config_path(args)
    return {
        "contract_version": _DISCOVERY_REUSE_CONTRACT_VERSION,
        "data_path": _safe_resolved_path(data_path),
        "data_hash": _file_sha256(data_path),
        "config_path": _safe_resolved_path(config_path) if config_path else "",
        "config_hash": _file_sha256(config_path) if config_path else "",
        "discovery_mode": str(getattr(args, "discovery_mode", "") or ""),
    }


def _load_discovery_reuse_manifest(out_dir: str | os.PathLike) -> dict[str, object]:
    path = _discovery_reuse_manifest_path(out_dir)
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _discovery_artifacts_match_current_inputs(args: argparse.Namespace, existing_artifacts: list[str]) -> tuple[bool, str, dict[str, object]]:
    """Return whether existing Discovery artifacts are safe to reuse for this run.

    `--discovery auto` must not silently reuse candidates generated from an older
    dataset. Reuse is allowed only when a sidecar manifest written by a prior
    successful Discovery run matches the current data hash, config hash, and
    discovery-mode preset. Legacy artifacts without this manifest are treated as
    stale and Discovery is recomputed.
    """
    if not existing_artifacts:
        return False, "no_existing_discovery_artifacts", {}
    current = _discovery_reuse_signature(args)
    if not current.get("data_hash"):
        return False, "current_data_hash_unavailable", {"current_signature": current}
    manifest = _load_discovery_reuse_manifest(args.out_dir)
    if not manifest:
        return False, "missing_discovery_reuse_manifest", {"current_signature": current}
    recorded = manifest.get("reuse_signature", {})
    if not isinstance(recorded, dict):
        return False, "invalid_discovery_reuse_manifest", {"current_signature": current}
    mismatches: dict[str, dict[str, object]] = {}
    for key in ("contract_version", "data_hash", "config_hash", "discovery_mode"):
        if recorded.get(key, "") != current.get(key, ""):
            mismatches[key] = {"recorded": recorded.get(key, ""), "current": current.get(key, "")}
    # Path changes with identical bytes are safe. Keep paths in the manifest for audit,
    # but do not block reuse purely because a file was moved or mounted elsewhere.
    if mismatches:
        return False, "discovery_reuse_signature_mismatch", {
            "current_signature": current,
            "recorded_signature": recorded,
            "mismatches": mismatches,
        }
    return True, "discovery_reuse_manifest_matches_current_inputs", {
        "current_signature": current,
        "recorded_signature": recorded,
        "manifest_path": str(_discovery_reuse_manifest_path(args.out_dir)),
    }


def _write_discovery_reuse_manifest(args: argparse.Namespace, discovery_argv: list[str], outputs_detected: list[str]) -> str:
    path = _discovery_reuse_manifest_path(args.out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "ok",
        "purpose": "Guards --discovery auto against reusing Discovery/bridge artifacts generated from a different dataset/config.",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reuse_signature": _discovery_reuse_signature(args),
        "discovery_argv": list(discovery_argv),
        "outputs_detected": list(outputs_detected),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(path)


def _resolve_discovery_policy(args: argparse.Namespace) -> str:
    policy = str(getattr(args, "discovery", "auto") or "auto").strip().lower()
    if bool(getattr(args, "skip_discovery", False)):
        policy = "skip"
    if policy not in {"auto", "run", "skip"}:
        policy = "auto"
    return policy


def _run_discovery_stage(args: argparse.Namespace) -> dict:
    """Run Discovery only when requested by policy.

    Discovery is an optional hypothesis generator. The downstream SCM/ID/estimation
    pipeline must be able to continue with an existing bridge/SCM artifact, or with
    empty schema-only artifacts when no discovery material is available.
    """
    policy = _resolve_discovery_policy(args)
    existing = _existing_discovery_artifacts(args.out_dir)
    if getattr(args, "scm_input", None) and policy == "auto":
        return {
            "status": "skipped",
            "policy": policy,
            "reason": "scm_input_supplied",
            "existing_artifacts": existing,
            "meaning": "Explicit SCM input is the structural prior; Discovery remains optional and was not required for this run.",
        }
    if policy == "skip":
        return {
            "status": "skipped",
            "policy": policy,
            "reason": "user_requested_skip_discovery",
            "existing_artifacts": existing,
            "meaning": "Discovery is optional; SCM/ID/estimation continue from existing or empty handoff artifacts.",
        }
    if policy == "auto" and existing:
        is_fresh, freshness_reason, freshness_details = _discovery_artifacts_match_current_inputs(args, existing)
        if is_fresh:
            return {
                "status": "skipped",
                "policy": policy,
                "reason": "existing_discovery_artifacts_fresh_for_current_inputs",
                "freshness_reason": freshness_reason,
                "freshness_details": freshness_details,
                "existing_artifacts": existing,
                "meaning": "Reused existing Discovery/bridge artifacts because their reuse manifest matches the current dataset/config signature. Use --discovery run to force recomputation.",
            }
        # Fall through and recompute. This is intentionally conservative: legacy
        # artifacts without a reuse manifest are treated as stale rather than trusted.
        stale_existing = existing
        stale_reason = freshness_reason
        stale_details = freshness_details
    else:
        stale_existing = []
        stale_reason = ""
        stale_details = {}

    from runtime_compat import assert_scientific_stack
    assert_scientific_stack()
    from offline.pcmci_core import cli as discovery_cli

    discovery_argv = ["--data", args.data, "--out-dir", args.out_dir]
    if getattr(args, "config", None):
        discovery_argv += ["--config", args.config]
    if getattr(args, "discovery_mode", None):
        discovery_argv += ["--discovery-mode", args.discovery_mode]
    discovery_rc = int(discovery_cli(discovery_argv) or 0)
    if discovery_rc != 0:
        return {
            "status": "failed",
            "policy": policy,
            "return_code": discovery_rc,
            "argv": discovery_argv,
            "reason": "discovery_stage_failed",
        }
    outputs_detected = _existing_discovery_artifacts(args.out_dir)
    reuse_manifest = _write_discovery_reuse_manifest(args, discovery_argv, outputs_detected)
    payload = {
        "status": "ok",
        "policy": policy,
        "return_code": 0,
        "argv": discovery_argv,
        "outputs_detected": outputs_detected,
        "reuse_manifest": reuse_manifest,
    }
    if stale_existing:
        payload.update({
            "recomputed_because": stale_reason,
            "stale_existing_artifacts": stale_existing,
            "stale_details": stale_details,
        })
    return payload

def _default_veto_authority_paths(args: argparse.Namespace) -> dict[str, str]:
    """Resolve default offline->runtime veto authority bridge paths for `causalgate run`."""
    out_dir = Path(args.out_dir)
    return {
        "graph": str(getattr(args, "veto_graph", None) or "operational_causal_graph.yaml"),
        "paths": str(getattr(args, "veto_paths", None) or "dangerous_paths.yaml"),
        "contract": str(Path(args.out_dir) / "causal_contract.csv"),
        "cards": str(getattr(args, "authority_cards_out", None) or out_dir / "veto" / "causal_authority_cards.jsonl"),
        "summary": str(getattr(args, "authority_summary_out", None) or out_dir / "veto" / "causal_authority_summary.json"),
        "effect_estimates": str(getattr(args, "authority_effect_estimates", None) or out_dir / "effect_estimates.csv"),
        "sensitivity_analysis": str(getattr(args, "authority_sensitivity_analysis", None) or out_dir / "sensitivity_analysis.csv"),
    }


def _build_veto_authority_if_requested(args: argparse.Namespace) -> dict:
    """Optionally build the runtime veto authority bridge after causal_contract.csv exists.

    The bridge is intentionally opt-in for `causalgate run`: it translates the
    offline causal contract into runtime authority cards, but it should not
    silently change bounded runtime veto behavior for existing users.
    """
    paths = _default_veto_authority_paths(args)
    if not getattr(args, "build_veto_authority", False):
        return {
            "status": "skipped",
            "reason": "not_requested",
            "how_to_enable": "rerun with --build-veto-authority",
            "expected_outputs": {
                "causal_authority_cards_jsonl": paths["cards"],
                "causal_authority_summary_json": paths["summary"],
            },
            "expected_evidence_inputs": {
                "effect_estimates_csv": paths["effect_estimates"],
                "sensitivity_analysis_csv": paths["sensitivity_analysis"],
            },
        }

    from contracts.causal_authority_for_veto import write_causal_authority_cards

    return write_causal_authority_cards(
        operational_graph_path=paths["graph"],
        path_library_path=paths["paths"],
        causal_contract_path=paths["contract"],
        out_jsonl=paths["cards"],
        out_summary=paths["summary"],
        effect_estimates_path=paths["effect_estimates"],
        sensitivity_analysis_path=paths["sensitivity_analysis"],
    )



def _cmd_run(args: argparse.Namespace) -> int:
    """Run the canonical CausalGate pipeline end-to-end.

    User-facing happy path:
        causalgate run --data data.csv --out-dir out

    Discovery/PCMCI remains hypothesis triage; SCM, identification,
    estimation planning, sensitivity, and the compact causal report are then
    synchronized in one command.
    """
    from scm_parts.builder import build_from_out_dir, build_from_scm_input
    from scm_parts.fit import fit_scm_models
    from scm_parts.identifier import write_identification_assets
    from contracts.causal_contract import write_causal_contract
    from estimation_parts.handoff_reader import load_estimation_handoff, write_estimation_plan
    from estimation_parts.sensitivity import write_sensitivity_analysis
    from estimation_parts.effect_estimates import write_effect_estimates
    from scm_parts.do_outputs import write_do_outputs
    from scm_parts.scm_counterfactual import write_scm_counterfactual_audit
    from contracts.gate_audit import write_unified_gate_audit
    from contracts.causal_report import write_causal_report
    from contracts.core_outputs import ensure_core_outputs

    args.out_dir = str(ensure_writable_dir(args.out_dir))
    args.data = _resolve_data_path(args.data)

    discovery_stage = _run_discovery_stage(args)
    if discovery_stage.get("status") == "failed":
        return int(discovery_stage.get("return_code") or 1)

    if getattr(args, "scm_input", None):
        built = build_from_scm_input(args.scm_input, out_dir=args.out_dir, data_path=args.data)
    else:
        built = build_from_out_dir(out_dir=args.out_dir, data_path=args.data)
    graph_path = built.get('scm_graph_json') or _default_scm_graph_path(args.out_dir)
    fitted = fit_scm_models(out_dir=args.out_dir, scm_graph_path=graph_path, data_path=args.data)
    identified = write_identification_assets(out_dir=args.out_dir, scm_graph_path=graph_path, bridge_csv_path=_resolve_bridge_path(args))
    contract = write_causal_contract(out_dir=args.out_dir)
    handoff = load_estimation_handoff(args.out_dir)
    estimation_plan = write_estimation_plan(handoff, args.out_dir)
    sensitivity_analysis = write_sensitivity_analysis(handoff, args.out_dir)
    effect_assets = write_effect_estimates(args.data, args.out_dir)
    do_assets = write_do_outputs(out_dir=args.out_dir, data_path=args.data)
    scm_counterfactual_assets = write_scm_counterfactual_audit(out_dir=args.out_dir, scm_graph_path=graph_path)
    gate_audit_assets = write_unified_gate_audit(out_dir=args.out_dir)
    causal_report = write_causal_report(out_dir=args.out_dir)
    core_outputs = ensure_core_outputs(args.out_dir)
    # Build the runtime authority bridge after estimation artifacts are mirrored
    # to the stable root-level public outputs. This keeps the runtime card
    # enriched but still avoids raw estimation reads at runtime.
    veto_authority = _build_veto_authority_if_requested(args)

    payload = {
        'status': 'ok',
        'command': 'run',
        'meaning': 'Canonical CausalGate pipeline: optional Discovery/PCMCI -> SCM -> ID algorithm -> causal contract -> do-estimation -> unified gate audit -> causal report.',
        'data': args.data,
        'out_dir': args.out_dir,
        'required_outputs': {
            'gate_audit_csv': core_outputs.get('gate_audit_csv', str(Path(args.out_dir) / 'gate_audit.csv')),
            'causal_report_csv': core_outputs.get('causal_report_csv', str(Path(args.out_dir) / 'causal_report.csv')),
            'causal_report_md': core_outputs.get('causal_report_md', str(Path(args.out_dir) / 'causal_report.md')),
            'estimation_plan_csv': core_outputs.get('estimation_plan_csv', estimation_plan),
            'sensitivity_analysis_csv': core_outputs.get('sensitivity_analysis_csv', sensitivity_analysis),
            'effect_estimates_csv': core_outputs.get('effect_estimates_csv', effect_assets.get('effect_estimates_csv')),
            'core_outputs_manifest_json': core_outputs.get('core_outputs_manifest_json'),
        },
        'discovery_stage': discovery_stage,
        'scm_assets': built,
        'scm_fit_assets': fitted,
        'scm_identification_assets': identified,
        'causal_contract_assets': contract,
        'veto_authority_assets': veto_authority,
        'do_estimate_assets': do_assets,
        'scm_counterfactual_assets': scm_counterfactual_assets,
        'gate_audit_assets': gate_audit_assets,
        'causal_report_assets': causal_report,
        'effect_estimate_assets': effect_assets,
        'core_outputs': core_outputs,
    }

    text = json.dumps(payload, indent=2)
    if getattr(args, 'out', None):
        write_text_safe(args.out, text)
    else:
        print(text)
    return 0

def _cmd_veto(args: argparse.Namespace) -> int:
    from runtime.veto_gateway import evaluate_action_request
    payload = json.loads(Path(args.input).read_text(encoding='utf-8'))
    if isinstance(payload, dict) and isinstance(payload.get('action_intent'), dict):
        nested = payload.get('action_intent') or {}
        if nested.get('action_name') and not payload.get('action_name'):
            payload = nested
    result = evaluate_action_request(
        payload,
        registry_path=args.registry,
        path_library_path=args.paths,
        graph_path=args.graph,
        event_log_path=args.events,
        validation_plan_path=args.validation_plan_path,
        authority_cards_path=getattr(args, 'authority_cards_path', 'out/veto/causal_authority_cards.jsonl'),
    )
    if args.out:
        write_text_safe(args.out, json.dumps(result, indent=2))
    else:
        print(json.dumps(result, indent=2))
    return 0


def _cmd_discover(args: argparse.Namespace) -> int:
    from runtime_compat import assert_scientific_stack
    assert_scientific_stack()
    from offline.pcmci_core import cli as discovery_cli
    args.out_dir = str(ensure_writable_dir(args.out_dir))
    args.data = _resolve_data_path(args.data)
    argv = ['--data', args.data, '--out-dir', args.out_dir]
    if args.config:
        argv += ['--config', args.config]
    if getattr(args, 'discovery_mode', None):
        argv += ['--discovery-mode', args.discovery_mode]
    rc = int(discovery_cli(argv) or 0)
    if rc == 0:
        _write_discovery_reuse_manifest(args, argv, _existing_discovery_artifacts(args.out_dir))
    return rc


def _cmd_draft_paths(args: argparse.Namespace) -> int:
    from runtime_compat import assert_scientific_stack
    assert_scientific_stack()
    from offline.discovery_to_dangerous_paths import generate_draft
    args.out = str(ensure_writable_parent(args.out))
    result = generate_draft(args.path_candidates, args.library, args.out, min_priority=args.min_priority)
    print(json.dumps(result, indent=2))
    return 0










def _parse_bool_like(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off"}:
        return False
    return value


def _load_action_events(path: str | os.PathLike) -> list[dict]:
    import csv
    path_obj = Path(path)
    if not path_obj.exists():
        raise FileNotFoundError(f"event log not found: {path_obj}")
    suffix = path_obj.suffix.lower()
    text = path_obj.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    if suffix == ".json":
        payload = json.loads(text)
        if isinstance(payload, list):
            return [dict(x) for x in payload if isinstance(x, dict)]
        if isinstance(payload, dict) and isinstance(payload.get("events"), list):
            return [dict(x) for x in payload["events"] if isinstance(x, dict)]
        raise ValueError(f"unsupported JSON event format: {path_obj}")
    rows: list[dict] = []
    with path_obj.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            event = dict(row)
            params = {}
            for key in ["recipient_scope", "resource_sensitivity", "attachment_present", "approval_present", "rollback_available", "blast_radius", "service_criticality", "novel_action"]:
                if key in event:
                    params[key] = _parse_bool_like(event.get(key))
                    event[key] = params[key]
            harms = str(event.get("observed_harms", "") or "").strip()
            event["observed_harms"] = [h.strip() for h in harms.replace(";", ",").split(",") if h.strip()] if harms else []
            event["params"] = {k: v for k, v in params.items() if v not in {"", None}}
            rows.append(event)
    return rows


def _cmd_causal_strata(args: argparse.Namespace) -> int:
    from runtime.causal_strata import build_causal_stratum, event_to_intent, path_treatment_status, summarize_strata, treated_control_design
    import csv
    events = _load_action_events(args.events)
    out_dir = ensure_writable_dir(args.out_dir)
    strata_csv = Path(args.strata_out) if args.strata_out else Path(out_dir) / "causal_strata.csv"
    summary_json = Path(args.summary_out) if args.summary_out else Path(out_dir) / "strata_summary.json"
    ensure_writable_parent(strata_csv)
    ensure_writable_parent(summary_json)
    path_ids = [p.strip() for p in str(args.path_id or "").split(",") if p.strip()] or [None]
    summary = {"status": "ok", "events_path": str(args.events), "n_events": len(events), "path_ids": [p for p in path_ids if p] or ["global"], "outputs": {"causal_strata_csv": str(strata_csv), "strata_summary_json": str(summary_json)}, "strata": {}}
    rows: list[dict] = []
    for path_id in path_ids:
        label = path_id or "global"
        summary["strata"][label] = summarize_strata([(e, 1.0) for e in events], path_id=path_id)
        counts: dict[tuple[str, str], int] = {}
        examples: dict[tuple[str, str], str] = {}
        for event in events:
            intent = event_to_intent(event)
            for key, value in event.items():
                if key not in intent and key != "params":
                    intent[key] = value
            if isinstance(event.get("params"), dict):
                intent.setdefault("params", {}).update(event.get("params") or {})
            stratum = build_causal_stratum(intent, path_id=path_id)
            status = path_treatment_status(intent, path_id) if path_id else "observed"
            k = (stratum, status)
            counts[k] = counts.get(k, 0) + 1
            examples.setdefault(k, str(event.get("event_id", "")))
        for (stratum, status), n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1])):
            rows.append({"path_id": label, "stratum_key": stratum, "treatment_status": status, "n_events": n, "example_event_id": examples.get((stratum, status), "")})
        if path_id:
            intent = event_to_intent(events[0]) if events else {"action_name": ""}
            summary["strata"][label]["treated_control_design"] = treated_control_design(intent, path_id)
    with strata_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["path_id", "stratum_key", "treatment_status", "n_events", "example_event_id"])
        writer.writeheader()
        writer.writerows(rows)
    payload = json.dumps(summary, indent=2, sort_keys=True)
    write_text_safe(summary_json, payload)
    if args.out:
        write_text_safe(args.out, payload)
    else:
        print(payload)
    return 0


def _load_json_or_yaml(path: str | os.PathLike) -> dict:
    text = Path(path).read_text(encoding='utf-8')
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
            return yaml.safe_load(text) or {}
        except (ImportError, ModuleNotFoundError, ValueError, TypeError):
            from runtime.action_registry_v2 import _minimal_yaml_load
            return _minimal_yaml_load(text) or {}

def _cmd_identify_graph(args: argparse.Namespace) -> int:
    from scm_parts.identifier import analyze_graph_query
    graph = _load_json_or_yaml(_resolve_scm_graph_path(args))
    conditioned = []
    if args.condition_on:
        conditioned = [c.strip() for c in str(args.condition_on).split(',') if c.strip()]
    result = analyze_graph_query(graph, args.treatment, args.outcome, conditioned=conditioned, max_adjustment_set=args.max_adjustment_set)
    payload = json.dumps(result, indent=2)
    if args.out:
        write_text_safe(args.out, payload)
    else:
        print(payload)
    return 0


def _cmd_scm_build(args: argparse.Namespace) -> int:
    from scm_parts.builder import build_from_out_dir, build_from_scm_input
    args.out_dir = str(ensure_writable_dir(args.out_dir))
    args.data = _resolve_data_path(args.data)
    if getattr(args, "scm_input", None):
        paths = build_from_scm_input(args.scm_input, out_dir=args.out_dir, data_path=args.data)
    else:
        paths = build_from_out_dir(out_dir=args.out_dir, data_path=args.data)
    payload = json.dumps({"status": "ok", "scm_assets": paths}, indent=2)
    if args.out:
        write_text_safe(args.out, payload)
    else:
        print(payload)
    return 0


def _cmd_scm_fit(args: argparse.Namespace) -> int:
    from scm_parts.fit import fit_scm_models
    args.out_dir = str(ensure_writable_dir(args.out_dir))
    args.data = _resolve_data_path(args.data)
    paths = fit_scm_models(out_dir=args.out_dir, scm_graph_path=_resolve_scm_graph_path(args), data_path=args.data)
    payload = json.dumps({"status": "ok", "scm_fit_assets": paths}, indent=2)
    if args.out:
        write_text_safe(args.out, payload)
    else:
        print(payload)
    return 0


def _cmd_scm_identify(args: argparse.Namespace) -> int:
    from scm_parts.identifier import write_identification_assets
    args.out_dir = str(ensure_writable_dir(args.out_dir))
    paths = write_identification_assets(out_dir=args.out_dir, scm_graph_path=_resolve_scm_graph_path(args), bridge_csv_path=_resolve_bridge_path(args))
    payload = json.dumps({"status": "ok", "scm_identification_assets": paths}, indent=2)
    if args.out:
        write_text_safe(args.out, payload)
    else:
        print(payload)
    return 0


def _cmd_scm_pipeline(args: argparse.Namespace) -> int:
    from scm_parts.builder import build_from_out_dir, build_from_scm_input
    from scm_parts.fit import fit_scm_models
    from scm_parts.identifier import write_identification_assets
    from scm_parts.scm_counterfactual import write_scm_counterfactual_audit
    args.out_dir = str(ensure_writable_dir(args.out_dir))
    args.data = _resolve_data_path(args.data)
    if getattr(args, "scm_input", None):
        built = build_from_scm_input(args.scm_input, out_dir=args.out_dir, data_path=args.data)
    else:
        built = build_from_out_dir(out_dir=args.out_dir, data_path=args.data)
    graph_path = built.get("scm_graph_json") or _resolve_scm_graph_path(args)
    fitted = fit_scm_models(out_dir=args.out_dir, scm_graph_path=graph_path, data_path=args.data)
    identified = write_identification_assets(out_dir=args.out_dir, scm_graph_path=graph_path, bridge_csv_path=_resolve_bridge_path(args))
    scm_counterfactual_assets = write_scm_counterfactual_audit(out_dir=args.out_dir, scm_graph_path=graph_path)
    payload = json.dumps({"status": "ok", "scm_assets": built, "scm_fit_assets": fitted, "scm_identification_assets": identified, "scm_counterfactual_assets": scm_counterfactual_assets}, indent=2)
    if args.out:
        write_text_safe(args.out, payload)
    else:
        print(payload)
    return 0


def _cmd_scm_counterfactual(args: argparse.Namespace) -> int:
    from scm_parts.scm_counterfactual import write_scm_counterfactual_audit, write_scm_counterfactual_outputs
    args.out_dir = str(ensure_writable_dir(args.out_dir))
    graph_path = _resolve_scm_graph_path(args)
    if getattr(args, "treatment", None) and getattr(args, "outcome", None):
        paths = write_scm_counterfactual_outputs(
            treatment=args.treatment,
            outcome=args.outcome,
            intervention_value=args.intervention_value,
            case_index=args.case_index,
            scm_graph=None if not _exists(graph_path) else json.loads(Path(graph_path).read_text(encoding="utf-8")),
            out_dir=args.out_dir,
            data_path=getattr(args, "data", None),
        )
    else:
        paths = write_scm_counterfactual_audit(
            out_dir=args.out_dir,
            scm_graph_path=graph_path if _exists(graph_path) else None,
            intervention_value=args.intervention_value,
            case_index=args.case_index,
        )
    payload = json.dumps({
        "status": "ok",
        "meaning": "SCM counterfactual authority is ID-gated: No ID -> no counterfactual authority.",
        "scm_counterfactual_assets": paths,
    }, indent=2)
    if args.out:
        write_text_safe(args.out, payload)
    else:
        print(payload)
    return 0


def _cmd_causal_align(args: argparse.Namespace) -> int:
    """Build the canonical PCMCI/SCM/estimation handoff contract."""
    from scm_parts.builder import build_from_out_dir, build_from_scm_input
    from scm_parts.fit import fit_scm_models
    from scm_parts.identifier import write_identification_assets
    from contracts.causal_contract import write_causal_contract
    args.out_dir = str(ensure_writable_dir(args.out_dir))
    args.data = _resolve_data_path(args.data)
    if getattr(args, "scm_input", None):
        built = build_from_scm_input(args.scm_input, out_dir=args.out_dir, data_path=args.data)
    else:
        built = build_from_out_dir(out_dir=args.out_dir, data_path=args.data)
    graph_path = built.get("scm_graph_json") or _resolve_scm_graph_path(args)
    fitted = fit_scm_models(out_dir=args.out_dir, scm_graph_path=graph_path, data_path=args.data)
    identified = write_identification_assets(out_dir=args.out_dir, scm_graph_path=graph_path, bridge_csv_path=_resolve_bridge_path(args))
    contract = write_causal_contract(out_dir=args.out_dir)
    from estimation_parts.handoff_reader import load_estimation_handoff, write_estimation_plan
    from estimation_parts.sensitivity import write_sensitivity_analysis
    from estimation_parts.effect_estimates import write_effect_estimates
    from scm_parts.do_outputs import write_do_outputs
    from scm_parts.scm_counterfactual import write_scm_counterfactual_audit
    handoff = load_estimation_handoff(args.out_dir)
    estimation_plan = write_estimation_plan(handoff, args.out_dir)
    sensitivity_analysis = write_sensitivity_analysis(handoff, args.out_dir)
    effect_assets = write_effect_estimates(args.data, args.out_dir)
    do_assets = write_do_outputs(out_dir=args.out_dir, data_path=args.data)
    scm_counterfactual_assets = write_scm_counterfactual_audit(out_dir=args.out_dir, scm_graph_path=graph_path)
    from contracts.causal_report import write_causal_report
    from contracts.core_outputs import ensure_core_outputs
    causal_report = write_causal_report(out_dir=args.out_dir)
    core_outputs = ensure_core_outputs(args.out_dir)
    payload = json.dumps({
        "status": "ok",
        "meaning": "PCMCI/Discovery, SCM identification, SCM fit, and estimation handoff are synchronized through causal_contract.csv",
        "scm_assets": built,
        "scm_fit_assets": fitted,
        "scm_identification_assets": identified,
        "causal_contract_assets": contract,
        "estimation_plan_csv": core_outputs.get("estimation_plan_csv", estimation_plan),
        "sensitivity_analysis_csv": core_outputs.get("sensitivity_analysis_csv", sensitivity_analysis),
        "effect_estimate_assets": effect_assets,
        "do_estimate_assets": do_assets,
        "scm_counterfactual_assets": scm_counterfactual_assets,
        "effect_estimates_csv": core_outputs.get("effect_estimates_csv", effect_assets.get("effect_estimates_csv")),
        "causal_report_assets": causal_report,
        "core_outputs": core_outputs,
    }, indent=2)
    if args.out:
        write_text_safe(args.out, payload)
    else:
        print(payload)
    return 0


def _cmd_estimate(args: argparse.Namespace) -> int:
    """Write the estimator handoff plan and sensitivity analysis.

    Conservative by default: this command writes estimator readiness artifacts
    from the causal handoff, without upgrading structural priors into effect claims.
    """
    from runtime_compat import assert_scientific_stack
    assert_scientific_stack()
    from estimation_parts.handoff_reader import load_estimation_handoff, write_estimation_plan
    from estimation_parts.sensitivity import write_sensitivity_analysis
    from estimation_parts.effect_estimates import write_effect_estimates
    from contracts.causal_report import write_causal_report
    from contracts.core_outputs import ensure_core_outputs

    args.out_dir = str(ensure_writable_dir(args.out_dir))
    args.data = _resolve_data_path(args.data)
    handoff = load_estimation_handoff(args.out_dir)
    estimation_plan = write_estimation_plan(handoff, args.out_dir)
    sensitivity_analysis = write_sensitivity_analysis(handoff, args.out_dir)
    effect_assets = write_effect_estimates(args.data, args.out_dir)
    causal_report = write_causal_report(out_dir=args.out_dir)
    core_outputs = ensure_core_outputs(args.out_dir)
    payload = {
        "status": "ok",
        "meaning": "Estimation planning is handoff-driven; plan and sensitivity analysis do not create causal effect authority.",
        "rows": int(len(handoff)) if hasattr(handoff, "__len__") else 0,
        "estimation_plan_csv": core_outputs.get("estimation_plan_csv", estimation_plan),
        "sensitivity_analysis_csv": core_outputs.get("sensitivity_analysis_csv", sensitivity_analysis),
        "effect_estimate_assets": effect_assets,
        "effect_estimates_csv": core_outputs.get("effect_estimates_csv", effect_assets.get("effect_estimates_csv")),
        "causal_report_assets": causal_report,
        "core_outputs": core_outputs,
    }

    text = json.dumps(payload, indent=2)
    if args.out:
        write_text_safe(args.out, text)
    else:
        print(text)
    return 0


def _cmd_graph_authority(args: argparse.Namespace) -> int:
    """Write the canonical graph authority manifest."""
    from contracts.graph_authority import write_graph_authority_manifest
    args.out_dir = str(ensure_writable_dir(args.out_dir))
    if args.out is None:
        args.out = str(Path(args.out_dir) / 'graph_authority_manifest.json')
    out_path = write_graph_authority_manifest(root='.', out_path=args.out, out_dir=args.out_dir)
    payload = json.dumps({
        "status": "ok",
        "meaning": "Canonical graph policy: one runtime graph, one offline SCM graph, one causal handoff contract.",
        "graph_authority_manifest": out_path,
    }, indent=2)
    print(payload)
    return 0


def _cmd_veto_authority(args: argparse.Namespace) -> int:
    """Write causal authority cards that bridge runtime paths to offline causal contracts."""
    from contracts.causal_authority_for_veto import write_causal_authority_cards
    summary = write_causal_authority_cards(
        operational_graph_path=args.graph,
        path_library_path=args.paths,
        causal_contract_path=args.contract,
        out_jsonl=args.out,
        out_summary=args.summary_out,
        effect_estimates_path=args.effect_estimates,
        sensitivity_analysis_path=args.sensitivity_analysis,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _cmd_causal_confidence(args: argparse.Namespace) -> int:
    from contracts.causal_confidence import write_causal_confidence_report
    args.out_dir = str(ensure_writable_dir(args.out_dir))
    paths = write_causal_confidence_report(out_dir=args.out_dir)
    payload = json.dumps({
        "status": "ok",
        "meaning": "Cross-layer confidence report; causal_contract remains the authority gate.",
        **paths,
    }, indent=2)
    if args.out:
        write_text_safe(args.out, payload)
    else:
        print(payload)
    return 0

def _cmd_causal_report(args: argparse.Namespace) -> int:
    from contracts.causal_report import write_causal_report
    from contracts.core_outputs import ensure_core_outputs
    args.out_dir = str(ensure_writable_dir(args.out_dir))
    paths = write_causal_report(out_dir=args.out_dir)
    core_outputs = ensure_core_outputs(args.out_dir)
    payload = json.dumps({
        "status": "ok",
        "meaning": "Compact cross-layer causal report; causal_contract remains the authority gate.",
        **paths,
        "core_outputs": core_outputs,
    }, indent=2)
    if args.out:
        write_text_safe(args.out, payload)
    else:
        print(payload)
    return 0


def _cmd_contract_validate(args: argparse.Namespace) -> int:
    """Validate causal contract integrity and downstream authority handoffs."""
    from contracts.contract_validator import validate_contract_integrity

    args.out_dir = str(ensure_writable_dir(args.out_dir))
    strict = not bool(getattr(args, "non_strict", False))
    report = validate_contract_integrity(
        out_dir=args.out_dir,
        strict=strict,
        write_report=bool(getattr(args, "write_report", False)) or bool(getattr(args, "report_out", None)),
        report_path=getattr(args, "report_out", None),
    )
    text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    if args.out:
        write_text_safe(args.out, text)
    else:
        print(text)
    return 0 if report.get("ok") else 2

def _cmd_scm_validate(args: argparse.Namespace) -> int:
    """Validate an explicit SCM-first JSON input without running the full pipeline."""
    from scm_parts.input_validator import validate_scm_input_file

    report = validate_scm_input_file(
        args.scm_input,
        data_path=getattr(args, "data", None),
        strict_data=bool(getattr(args, "strict_data", False)),
    )
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        write_text_safe(args.out, text)
    else:
        print(text)
    return 0 if report.get("ok") else 2


def _read_json_mapping(path: str | os.PathLike | None) -> dict:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return payload


def _cmd_guard(args: argparse.Namespace) -> int:
    """Evaluate a proposed AI-agent action through the public CausalGate firewall."""
    from causalgate import AgentCausalFirewall

    payload = _read_json_mapping(args.input) if getattr(args, "input", None) else {}
    tool_args = _read_json_mapping(args.tool_args) if getattr(args, "tool_args", None) else {}
    trusted_runtime_context = _read_json_mapping(args.trusted_context) if getattr(args, "trusted_context", None) else {}
    untrusted_llm_context = _read_json_mapping(args.llm_context) if getattr(args, "llm_context", None) else {}
    causal_evidence = _read_json_mapping(args.evidence) if getattr(args, "evidence", None) else payload.get("causal_evidence", {})

    # Inline flags override/complete the optional JSON input.  Runtime-sensitive
    # facts are sent through trusted_runtime_context by AgentCausalFirewall.evaluate.
    action = args.action or payload.get("action_name") or payload.get("candidate_action") or payload.get("tool_name") or ""
    tool_name = args.tool or payload.get("tool_name") or action
    if args.environment:
        trusted_runtime_context["environment"] = args.environment
    if args.risk_level:
        trusted_runtime_context["risk_level"] = args.risk_level
    if args.action_type:
        trusted_runtime_context["action_type"] = args.action_type
    if args.target_resource:
        trusted_runtime_context["target_resource"] = args.target_resource
    if args.approval_present:
        trusted_runtime_context["approval_present"] = True
    if args.rollback_available:
        trusted_runtime_context["rollback_available"] = True
    if args.recipient_external:
        trusted_runtime_context["recipient_external"] = True

    firewall = AgentCausalFirewall(
        policy=args.policy or None,
        enable_tool_guard=not bool(args.disable_tool_guard),
        audit_log_path=args.audit_log or None,
    )
    result = firewall.evaluate(
        action=str(action),
        tool_name=str(tool_name),
        tool_args=tool_args,
        risk_level=str(trusted_runtime_context.get("risk_level", payload.get("risk_level", "unknown"))),
        environment=str(trusted_runtime_context.get("environment", payload.get("environment", "unknown"))),
        action_type=str(trusted_runtime_context.get("action_type", payload.get("action_type", "unknown"))),
        target_resource=str(trusted_runtime_context.get("target_resource", payload.get("target_resource", ""))),
        approval_present=bool(trusted_runtime_context.get("approval_present", payload.get("approval_present", False))),
        rollback_available=bool(trusted_runtime_context.get("rollback_available", payload.get("rollback_available", False))),
        trusted_runtime_context=trusted_runtime_context,
        untrusted_llm_context=untrusted_llm_context,
        request_id=payload.get("request_id", ""),
        user_message=payload.get("user_message", ""),
        treatment=payload.get("treatment", ""),
        outcome=payload.get("outcome", ""),
        scm_graph=payload.get("scm_graph", {}),
        causal_query=payload.get("causal_query", {}),
        evidence=causal_evidence or None,
        require_causal_evidence=bool(args.require_causal_evidence) or bool(payload.get("require_causal_evidence", False)),
    )

    if getattr(args, "report_json", None):
        from causalgate.reports import write_json_report
        write_json_report(result, args.report_json)
    if getattr(args, "report_md", None):
        from causalgate.reports import write_markdown_report
        write_markdown_report(result, args.report_md)

    result = result.to_dict()
    text = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True)
    if args.out:
        write_text_safe(args.out, text)
    else:
        print(text)
    return 0



def _cmd_demo(args: argparse.Namespace) -> int:
    """Run the 60-second product demo and write reports."""
    from causalgate.demo import run_product_demo

    result = run_product_demo(
        out_dir=args.out_dir,
        policy=args.policy or None,
        enable_tool_guard=not bool(args.disable_tool_guard),
    )
    payload = result.to_dict()
    if getattr(args, "pretty", False):
        print("\nCausalGate demo complete")
        print("=" * 32)
        for case in payload["cases"]:
            score = case.get("authority_score")
            score_text = "n/a" if score is None else f"{score}/100"
            print(f"{case['case_id']:<32} {case['decision']:<10} authority={score_text}")
            print(f"  {case['title']}")
            print(f"  report: {case.get('report_html') or case.get('report_md')}\n")
        print(f"Summary: {payload['summary_md']}")
    else:
        print("CausalGate demo complete")
        print(f"summary_md: {payload['summary_md']}")
        print(f"summary_json: {payload['summary_json']}")
        for case in payload["cases"]:
            score = case.get("authority_score")
            score_text = "n/a" if score is None else f"{score}/100"
            print(f"- {case['case_id']}: {case['decision']} | authority={score_text} | {case['title']}")
    return 0



def _cmd_api(args: argparse.Namespace) -> int:
    """Run the commercial/product HTTP API server."""
    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"uvicorn is required for `causalgate api`. Install with: pip install -e .[server] ({exc})") from exc

    uvicorn.run(
        "causalgate.api.server:app",
        host=args.host,
        port=int(args.port),
        reload=bool(args.reload),
        log_level=args.log_level,
    )
    return 0

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='causalgate', description='CausalGate causal safety + PCMCI discovery CLI')
    sub = p.add_subparsers(dest='cmd', required=True)

    p_demo = sub.add_parser('demo', help='Run the 60-second CausalGate product demo and write reports')
    p_demo.add_argument('--out-dir', default='out/demo', help='Directory for generated demo reports')
    p_demo.add_argument('--policy', default='', help='Optional firewall policy YAML path')
    p_demo.add_argument('--disable-tool-guard', action='store_true', default=True, help='Keep ToolGuard disabled for a pure product demo')
    p_demo.add_argument('--enable-tool-guard', dest='disable_tool_guard', action='store_false', help='Enable ToolGuard in the demo')
    p_demo.add_argument('--pretty', action='store_true', help='Print a buyer-friendly table with report links')
    p_demo.set_defaults(func=_cmd_demo)

    p_api = sub.add_parser('api', help='Run the CausalGate product HTTP API server')
    p_api.add_argument('--host', default='0.0.0.0', help='Host/interface to bind')
    p_api.add_argument('--port', type=int, default=8000, help='Port to bind')
    p_api.add_argument('--reload', action='store_true', help='Enable uvicorn reload for local development')
    p_api.add_argument('--log-level', default='info', choices=['critical','error','warning','info','debug','trace'])
    p_api.set_defaults(func=_cmd_api)

    p_guard = sub.add_parser('guard', help='Evaluate an AI-agent action through the public causal firewall')
    p_guard.add_argument('--input', default='', help='Optional ActionPackage/tool-call JSON object')
    p_guard.add_argument('--action', default='', help='Proposed action name, for example deploy_config_change')
    p_guard.add_argument('--tool', default='', help='Tool name, if different from --action')
    p_guard.add_argument('--tool-args', default='', help='Optional JSON object file with tool arguments')
    p_guard.add_argument('--trusted-context', default='', help='Optional JSON object file with trusted runtime facts')
    p_guard.add_argument('--llm-context', default='', help='Optional JSON object file with untrusted LLM explanation/context')
    p_guard.add_argument('--evidence', default='', help='Optional CausalEvidence JSON file with identification/estimation/diagnostics evidence')
    p_guard.add_argument('--require-causal-evidence', action='store_true', help='Fail closed/review unless causal authority evidence is sufficient')
    p_guard.add_argument('--report-json', default='', help='Optional audit report JSON output path')
    p_guard.add_argument('--report-md', default='', help='Optional audit report Markdown output path')
    p_guard.add_argument('--environment', default='production')
    p_guard.add_argument('--risk-level', default='high')
    p_guard.add_argument('--action-type', default='mutation')
    p_guard.add_argument('--target-resource', default='')
    p_guard.add_argument('--approval-present', action='store_true')
    p_guard.add_argument('--rollback-available', action='store_true')
    p_guard.add_argument('--recipient-external', action='store_true')
    p_guard.add_argument('--policy', default='', help='Optional firewall policy YAML path')
    p_guard.add_argument('--audit-log', default='', help='Optional JSONL audit log path')
    p_guard.add_argument('--disable-tool-guard', action='store_true', help='Run policy-only evaluation')
    p_guard.add_argument('--out', help='Optional JSON output path')
    p_guard.set_defaults(func=_cmd_guard)

    p_firewall = sub.add_parser('firewall', help='Alias for guard')
    p_firewall.add_argument('--input', default='', help='Optional ActionPackage/tool-call JSON object')
    p_firewall.add_argument('--action', default='', help='Proposed action name')
    p_firewall.add_argument('--tool', default='', help='Tool name, if different from --action')
    p_firewall.add_argument('--tool-args', default='', help='Optional JSON object file with tool arguments')
    p_firewall.add_argument('--trusted-context', default='', help='Optional JSON object file with trusted runtime facts')
    p_firewall.add_argument('--llm-context', default='', help='Optional JSON object file with untrusted LLM explanation/context')
    p_firewall.add_argument('--evidence', default='', help='Optional CausalEvidence JSON file with identification/estimation/diagnostics evidence')
    p_firewall.add_argument('--require-causal-evidence', action='store_true', help='Fail closed/review unless causal authority evidence is sufficient')
    p_firewall.add_argument('--report-json', default='', help='Optional audit report JSON output path')
    p_firewall.add_argument('--report-md', default='', help='Optional audit report Markdown output path')
    p_firewall.add_argument('--environment', default='production')
    p_firewall.add_argument('--risk-level', default='high')
    p_firewall.add_argument('--action-type', default='mutation')
    p_firewall.add_argument('--target-resource', default='')
    p_firewall.add_argument('--approval-present', action='store_true')
    p_firewall.add_argument('--rollback-available', action='store_true')
    p_firewall.add_argument('--recipient-external', action='store_true')
    p_firewall.add_argument('--policy', default='', help='Optional firewall policy YAML path')
    p_firewall.add_argument('--audit-log', default='', help='Optional JSONL audit log path')
    p_firewall.add_argument('--disable-tool-guard', action='store_true', help='Run policy-only evaluation')
    p_firewall.add_argument('--out', help='Optional JSON output path')
    p_firewall.set_defaults(func=_cmd_guard)

    p_run = sub.add_parser('run', help='Run the canonical CausalGate pipeline end-to-end')
    p_run.add_argument('--data', default='data.csv')
    p_run.add_argument('--out-dir', default='out')
    p_run.add_argument('--config', default='pcb.json')
    p_run.add_argument('--bridge', default=None, help='Defaults to <out-dir>/discovery_estimation_bridge.csv')
    p_run.add_argument('--scm-input', default=None, help='Explicit SCM-first JSON input. When provided, it becomes the structural prior and Discovery is optional.')
    p_run.add_argument('--discovery-mode', choices=['conservative', 'balanced', 'exploratory'], default=None,
                       help='Discovery-only strictness preset; downstream causal safety gates remain separate')
    p_run.add_argument('--discovery', choices=['auto', 'run', 'skip'], default='auto',
                       help='Discovery stage policy for causalgate run. auto runs Discovery only when no existing Discovery/bridge artifacts are present; run forces PCMCI; skip runs SCM/ID/estimation without Discovery.')
    p_run.add_argument('--skip-discovery', action='store_true',
                       help='Alias for --discovery skip. Keeps Discovery as an optional hypothesis generator instead of a required pipeline stage.')
    p_run.add_argument('--build-veto-authority', action='store_true',
                       help='Also write offline->runtime veto authority cards from causal_contract.csv')
    p_run.add_argument('--veto-graph', default='operational_causal_graph.yaml',
                       help='Runtime operational graph for --build-veto-authority')
    p_run.add_argument('--veto-paths', default='dangerous_paths.yaml',
                       help='Runtime dangerous path library for --build-veto-authority')
    p_run.add_argument('--authority-cards-out', default=None,
                       help='Defaults to <out-dir>/veto/causal_authority_cards.jsonl')
    p_run.add_argument('--authority-summary-out', default=None,
                       help='Defaults to <out-dir>/veto/causal_authority_summary.json')
    p_run.add_argument('--authority-effect-estimates', default=None,
                       help='Optional effect_estimates.csv used to enrich --build-veto-authority cards; defaults to <out-dir>/effect_estimates.csv')
    p_run.add_argument('--authority-sensitivity-analysis', default=None,
                       help='Optional sensitivity_analysis.csv used to enrich --build-veto-authority cards; defaults to <out-dir>/sensitivity_analysis.csv')
    p_run.add_argument('--out', help='Optional JSON command summary output path')
    p_run.set_defaults(func=_cmd_run)

    p_veto = sub.add_parser('veto', help='Evaluate one action request through the runtime veto engine')
    p_veto.add_argument('--input', required=True, help='Action request JSON')
    p_veto.add_argument('--out', help='Where to write the JSON result')
    p_veto.add_argument('--registry', default='action_registry.yaml')
    p_veto.add_argument('--paths', default='dangerous_paths.yaml')
    p_veto.add_argument('--graph', default='operational_causal_graph.yaml')
    p_veto.add_argument('--events', default='historical_action_events.jsonl')
    p_veto.add_argument('--validation-plan-path', default='out/validation_plan_level2.csv',
                        help='Validation plan CSV used to guide path counterfactual matching')
    p_veto.add_argument('--authority-cards-path', default='out/veto/causal_authority_cards.jsonl',
                        help='Precomputed causal authority cards; labels causal-veto authority without changing bounded runtime behavior')
    p_veto.set_defaults(func=_cmd_veto)

    p_disc = sub.add_parser('discover', help='Run offline PCMCI-like causal hypothesis discovery')
    p_disc.add_argument('--data', default='data.csv')
    p_disc.add_argument('--out-dir', default='out')
    p_disc.add_argument('--config')
    p_disc.add_argument('--discovery-mode', choices=['conservative', 'balanced', 'exploratory'], default=None,
                        help='PCMCI discovery-only strictness preset; veto/policy safety stays unchanged')
    p_disc.set_defaults(func=_cmd_discover)

    p_draft = sub.add_parser('draft-paths', help='Generate dangerous path drafts from PCMCI discovery output')
    p_draft.add_argument('--path-candidates', default='out/path_candidates_level2.csv')
    p_draft.add_argument('--library', default='dangerous_paths.yaml')
    p_draft.add_argument('--out', default='out/dangerous_paths_discovery_draft.yaml')
    p_draft.add_argument('--min-priority', type=float, default=0.7)
    p_draft.set_defaults(func=_cmd_draft_paths)

    p_ident = sub.add_parser('identify-graph', help='Run explicit d-separation and adjustment-set analysis on an SCM graph')
    p_ident.add_argument('--out-dir', default='out')
    p_ident.add_argument('--graph', default=None, help='Defaults to <out-dir>/scm/scm_graph.json')
    p_ident.add_argument('--treatment', required=True)
    p_ident.add_argument('--outcome', required=True)
    p_ident.add_argument('--condition-on', default='')
    p_ident.add_argument('--max-adjustment-set', type=int, default=3)
    p_ident.add_argument('--out')
    p_ident.set_defaults(func=_cmd_identify_graph)


    p_scm_build = sub.add_parser('scm-build', help='Build SCM graph assets from discovery outputs')
    p_scm_build.add_argument('--out-dir', default='out')
    p_scm_build.add_argument('--data', default='data.csv', help='Dataset used to infer node families')
    p_scm_build.add_argument('--scm-input', default=None, help='Explicit SCM-first JSON input to build from instead of Discovery outputs')
    p_scm_build.add_argument('--out', help='Optional JSON summary output path')
    p_scm_build.set_defaults(func=_cmd_scm_build)

    p_scm_validate = sub.add_parser('scm-validate', help='Validate an explicit SCM-first JSON input without building the pipeline')
    p_scm_validate.add_argument('--scm-input', required=True, help='SCM-first JSON input to validate')
    p_scm_validate.add_argument('--data', default=None, help='Optional dataset path for observed-node column checks')
    p_scm_validate.add_argument('--strict-data', action='store_true', help='Treat observed SCM nodes missing from --data as validation errors instead of warnings')
    p_scm_validate.add_argument('--out', help='Optional JSON validation report output path')
    p_scm_validate.set_defaults(func=_cmd_scm_validate)

    p_scm_fit = sub.add_parser('scm-fit', help='Fit lightweight structural equations for the SCM graph')
    p_scm_fit.add_argument('--out-dir', default='out')
    p_scm_fit.add_argument('--graph', default=None, help='Defaults to <out-dir>/scm/scm_graph.json')
    p_scm_fit.add_argument('--data', default='data.csv')
    p_scm_fit.add_argument('--out', help='Optional JSON summary output path')
    p_scm_fit.set_defaults(func=_cmd_scm_fit)

    p_scm_identify = sub.add_parser('scm-identify', help='Write SCM identification assets from the SCM graph')
    p_scm_identify.add_argument('--out-dir', default='out')
    p_scm_identify.add_argument('--graph', default=None)
    p_scm_identify.add_argument('--bridge', default=None, help='Defaults to <out-dir>/discovery_estimation_bridge.csv')
    p_scm_identify.add_argument('--out', help='Optional JSON summary output path')
    p_scm_identify.set_defaults(func=_cmd_scm_identify)

    p_scm_pipeline = sub.add_parser('scm-pipeline', help='Run SCM build -> fit -> identify in order')
    p_scm_pipeline.add_argument('--out-dir', default='out')
    p_scm_pipeline.add_argument('--graph', default=None)
    p_scm_pipeline.add_argument('--data', default='data.csv')
    p_scm_pipeline.add_argument('--scm-input', default=None, help='Explicit SCM-first JSON input to build from instead of Discovery outputs')
    p_scm_pipeline.add_argument('--bridge', default=None, help='Defaults to <out-dir>/discovery_estimation_bridge.csv')
    p_scm_pipeline.add_argument('--out', help='Optional JSON summary output path')
    p_scm_pipeline.set_defaults(func=_cmd_scm_pipeline)

    p_scm_cf = sub.add_parser('scm-counterfactual', help='Write SCM/ID-gated counterfactual authority assets')
    p_scm_cf.add_argument('--out-dir', default='out')
    p_scm_cf.add_argument('--graph', default=None, help='Defaults to <out-dir>/scm/scm_graph.json')
    p_scm_cf.add_argument('--treatment', default='', help='Optional single treatment/action to evaluate')
    p_scm_cf.add_argument('--outcome', default='', help='Optional single outcome to evaluate')
    p_scm_cf.add_argument('--intervention-value', type=float, default=0.0)
    p_scm_cf.add_argument('--case-index', type=int, default=0)
    p_scm_cf.add_argument('--data', default='data.csv')
    p_scm_cf.add_argument('--out', help='Optional JSON summary output path')
    p_scm_cf.set_defaults(func=_cmd_scm_counterfactual)

    p_causal_align = sub.add_parser('causal-align', help='Synchronize PCMCI/Discovery, SCM, identification and estimation handoff')
    p_causal_align.add_argument('--out-dir', default='out')
    p_causal_align.add_argument('--graph', default=None)
    p_causal_align.add_argument('--data', default='data.csv')
    p_causal_align.add_argument('--scm-input', default=None, help='Explicit SCM-first JSON input to build from instead of Discovery outputs')
    p_causal_align.add_argument('--bridge', default=None, help='Defaults to <out-dir>/discovery_estimation_bridge.csv')
    p_causal_align.add_argument('--out', help='Optional JSON summary output path')
    p_causal_align.set_defaults(func=_cmd_causal_align)



    p_graph_authority = sub.add_parser('graph-authority', help='Write the canonical graph authority manifest')
    p_graph_authority.add_argument('--out-dir', default='out')
    p_graph_authority.add_argument('--out', default=None)
    p_graph_authority.set_defaults(func=_cmd_graph_authority)

    p_veto_authority = sub.add_parser('veto-authority', help='Write causal authority cards for runtime veto paths')
    p_veto_authority.add_argument('--graph', default='operational_causal_graph.yaml')
    p_veto_authority.add_argument('--paths', default='dangerous_paths.yaml')
    p_veto_authority.add_argument('--contract', default='out/causal_contract.csv')
    p_veto_authority.add_argument('--effect-estimates', default=None, help='Optional effect_estimates.csv for card enrichment')
    p_veto_authority.add_argument('--sensitivity-analysis', default=None, help='Optional sensitivity_analysis.csv for card enrichment')
    p_veto_authority.add_argument('--out', default='out/veto/causal_authority_cards.jsonl')
    p_veto_authority.add_argument('--summary-out', default='out/veto/causal_authority_summary.json')
    p_veto_authority.set_defaults(func=_cmd_veto_authority)

    p_conf = sub.add_parser('causal-confidence', help='Write cross-layer causal confidence report from Discovery/SCM/do artifacts')
    p_conf.add_argument('--out-dir', default='out')
    p_conf.add_argument('--out', help='Optional JSON command summary output path')
    p_conf.set_defaults(func=_cmd_causal_confidence)

    p_estimate = sub.add_parser('estimate', help='Write estimation_plan.csv, effect_estimates.csv and sensitivity analyses from the causal handoff')
    p_estimate.add_argument('--out-dir', default='out')
    p_estimate.add_argument('--data', default='data.csv', help='Dataset path used for diagnostic effect estimates')
    p_estimate.add_argument('--out', help='Optional JSON command summary output path')
    p_estimate.set_defaults(func=_cmd_estimate)

    p_report = sub.add_parser('causal-report', help='Write compact causal report from Discovery, SCM, identification and estimation artifacts')
    p_report.add_argument('--out-dir', default='out')
    p_report.add_argument('--out', help='Optional JSON command summary output path')
    p_report.set_defaults(func=_cmd_causal_report)


    p_contract_validate = sub.add_parser('contract-validate', help='Validate causal_contract.csv and downstream estimation/report authority handoffs')
    p_contract_validate.add_argument('--out-dir', default='out')
    p_contract_validate.add_argument('--non-strict', action='store_true', help='Downgrade missing canonical artifacts to warnings; useful before a full run exists')
    p_contract_validate.add_argument('--write-report', action='store_true', help='Write <out-dir>/contract_integrity_report.json')
    p_contract_validate.add_argument('--report-out', default=None, help='Optional JSON report path; implies --write-report')
    p_contract_validate.add_argument('--out', help='Optional JSON command output path')
    p_contract_validate.set_defaults(func=_cmd_contract_validate)

    p_strata = sub.add_parser('causal-strata', help='Build causal strata tables from action-event logs')
    p_strata.add_argument('--events', default='historical_action_events.jsonl', help='Action events as JSONL, JSON, or CSV')
    p_strata.add_argument('--path-id', default='', help='Optional dangerous path id, or comma-separated ids. Empty builds global strata.')
    p_strata.add_argument('--out-dir', default='out')
    p_strata.add_argument('--strata-out', default='', help='Optional causal_strata.csv output path')
    p_strata.add_argument('--summary-out', default='', help='Optional strata_summary.json output path')
    p_strata.add_argument('--out', help='Optional JSON command summary output path')
    p_strata.set_defaults(func=_cmd_causal_strata)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    # Some embedded Python environments keep shutdown hooks alive after the
    # command has already written its result. Flush explicitly and exit the
    # process so CLI smoke tests and CI jobs do not hang after successful work.
    # Also catch argparse's SystemExit so `causalgate --help` exits cleanly too.
    import os as _os
    import sys as _sys
    try:
        _rc = int(main())
    except SystemExit as _exc:
        _code = _exc.code
        if isinstance(_code, int):
            _rc = _code
        elif _code is None:
            _rc = 0
        else:
            _rc = 1
    try:
        _sys.stdout.flush()
        _sys.stderr.flush()
    finally:
        _os._exit(_rc)
