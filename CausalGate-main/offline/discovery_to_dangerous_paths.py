
from __future__ import annotations

from runtime_env import configure_scientific_runtime
configure_scientific_runtime()


import argparse
import json
from pathlib import Path

from fs_utils import ensure_writable_parent
from typing import Any, Dict, List

from runtime_compat import assert_scientific_stack
assert_scientific_stack()
import pandas as pd
import yaml

SEVERITY_BY_HARM = {
    'harm_leakage': 'critical',
    'harm_data_loss': 'critical',
    'harm_unauthorized_access': 'high',
    'harm_policy_bypass': 'high',
    'harm_operational_failure': 'medium',
    'harm_target_regression': 'medium',
}

REVERSIBILITY_BY_ACTION_TYPE = {
    'delete': 'low',
    'reduce': 'medium',
    'increase': 'medium',
    'change': 'medium',
    'share': 'low',
    'send': 'low',
}

TRIGGER_HINTS = {
    'increase': 'configuration_change',
    'reduce': 'service_change',
    'delete': 'delete_resource',
    'share': 'external_share',
    'send': 'external_send',
}

AMPLIFIER_HINTS = {
    'context_load': ['novel_action'],
    'tool_call_rate': ['production_environment'],
    'environment_risk': ['production_environment', 'high_blast_radius'],
    'blast_radius': ['high_blast_radius'],
}


def _slug(text: str) -> str:
    return str(text or '').strip().lower().replace(' ', '_').replace('-', '_')


def _load_existing_paths(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {'paths': {}}
    data = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
    if not isinstance(data, dict):
        return {'paths': {}}
    data.setdefault('paths', {})
    return data


def _required_contexts(row: pd.Series) -> List[str]:
    out: List[str] = []
    context_feature = str(row.get('context_feature_candidate', '') or '').strip()
    harm_node = str(row.get('harm_node_candidate', '') or '').strip()
    action_name = str(row.get('action_name', '') or '').strip()
    if 'environment_risk' in context_feature or 'operational_failure' in harm_node:
        out.append('production_environment')
    if 'context_load' in action_name or 'tool' in action_name:
        out.append('novel_action')
    return sorted(set(out))


def _amplifiers(row: pd.Series) -> List[str]:
    amps: List[str] = []
    mediator = str(row.get('mediator_candidate', '') or '').strip()
    context_feature = str(row.get('context_feature_candidate', '') or '').strip()
    amps.extend(AMPLIFIER_HINTS.get(mediator, []))
    amps.extend(AMPLIFIER_HINTS.get(context_feature, []))
    flags = str(row.get('risk_flags', '') or '')
    if 'LAGGED_SIGNAL' in flags:
        amps.append('novel_action')
    if 'ROLLING_STABILITY' in flags:
        amps.append('production_environment')
    return sorted(set(a for a in amps if a))


def _trigger(row: pd.Series) -> List[str]:
    action_type = _slug(row.get('action_type', ''))
    action_name = _slug(row.get('action_name', ''))
    trigger = TRIGGER_HINTS.get(action_type)
    if trigger:
        return [trigger]
    if 'environment_risk' in action_name or 'ops' in action_name:
        return ['service_change']
    return ['configuration_change']


def _description(row: pd.Series) -> str:
    action_name = str(row.get('action_name', '') or '').replace('_', ' ')
    harm_label = str(row.get('harm_label', '') or '').replace('_', ' ')
    mediator = str(row.get('mediator_candidate', '') or '').replace('_', ' ')
    if mediator:
        return f"{action_name} may influence {mediator} and increase risk of {harm_label}."
    return f"{action_name} may increase risk of {harm_label}."


def _draft_path_entry(row: pd.Series) -> Dict[str, Any]:
    harm_node = str(row.get('harm_node_candidate', '') or '').strip() or 'harm_operational_failure'
    action_type = _slug(row.get('action_type', ''))
    action_name = _slug(row.get('action_name', ''))
    strength = float(row.get('strength', 0.0) or 0.0)
    validation = float(row.get('validation_readiness_score', 0.0) or 0.0)
    structural = float(row.get('structural_risk_score', 0.0) or 0.0)
    severity = SEVERITY_BY_HARM.get(harm_node, 'medium')
    reversibility = REVERSIBILITY_BY_ACTION_TYPE.get(action_type, 'medium')
    evidence = 'weak'
    if strength >= 0.9 and validation >= 0.5:
        evidence = 'medium'
    if strength >= 0.95 and validation >= 0.6:
        evidence = 'strong'

    entry: Dict[str, Any] = {
        'description': _description(row),
        'graph_harm': harm_node,
        'triggers_any': _trigger(row),
        'severity': severity,
        'reversibility': reversibility,
        'default_evidence_strength': evidence,
        'candidate_source': 'discovery_v2',
        'candidate_action_name': action_name,
        'candidate_mediator': _slug(row.get('mediator_candidate', '')),
        'candidate_context_feature': _slug(row.get('context_feature_candidate', '')),
        'discovery_scores': {
            'strength': round(strength, 3),
            'priority_score': round(float(row.get('priority_score', 0.0) or 0.0), 3),
            'causal_plausibility_score': round(float(row.get('causal_plausibility_score', 0.0) or 0.0), 3),
            'validation_readiness_score': round(validation, 3),
            'structural_risk_score': round(structural, 3),
        },
        'review_notes': [
            str(row.get('path_statement', '') or '').strip(),
            str(row.get('harm_hypothesis', '') or '').strip(),
            f"trial_design_hint={str(row.get('trial_design_hint', '') or '').strip()}",
        ],
    }

    req = _required_contexts(row)
    if req:
        entry['required_context_any'] = req
    amps = _amplifiers(row)
    if amps:
        entry['amplifiers'] = amps
    if severity == 'critical' and reversibility == 'low':
        entry['hard_block_if'] = ['production_environment']
    return entry


def generate_draft(candidate_csv: str | Path, existing_paths_yaml: str | Path, out_yaml: str | Path, min_priority: float = 0.7) -> Dict[str, Any]:
    df = pd.read_csv(candidate_csv)
    existing = _load_existing_paths(existing_paths_yaml)
    existing_ids = set((existing.get('paths') or {}).keys())
    draft_paths: Dict[str, Any] = {}
    skipped: List[str] = []
    ranked = df.sort_values(['priority_score', 'causal_plausibility_score'], ascending=False).copy()
    effective_min_priority = float(min_priority)
    if len(ranked) > 0 and pd.to_numeric(ranked.get('priority_score'), errors='coerce').fillna(0.0).max() < effective_min_priority:
        # Backward-compatible fallback for demo / bridge flows: when no discovery
        # candidate reaches the caller threshold, still emit the best available
        # draft rather than returning an empty file.
        effective_min_priority = float(pd.to_numeric(ranked.get('priority_score'), errors='coerce').fillna(0.0).max())
    for _, row in ranked.iterrows():
        if float(row.get('priority_score', 0.0) or 0.0) < effective_min_priority:
            continue
        pid = str(row.get('path_id_candidate', '') or '').strip()
        if not pid:
            continue
        draft_id = _slug(pid)
        if draft_id in existing_ids:
            skipped.append(draft_id)
            continue
        draft_paths[draft_id] = _draft_path_entry(row)
    out = {
        'generated_from': str(candidate_csv),
        'existing_paths_source': str(existing_paths_yaml),
        'draft_paths': draft_paths,
        'skipped_existing_ids': skipped,
        'generated_count': len(draft_paths),
        'effective_min_priority': effective_min_priority,
    }
    out_p = Path(out_yaml)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(yaml.safe_dump(out, sort_keys=False, allow_unicode=True), encoding='utf-8')
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description='Generate dangerous path drafts from discovery path candidates.')
    ap.add_argument('--candidate-csv', default='out/path_candidates_level2.csv')
    ap.add_argument('--existing-paths-yaml', default='dangerous_paths.yaml')
    ap.add_argument('--out-yaml', default='out/dangerous_paths_discovery_draft.yaml')
    ap.add_argument('--min-priority', type=float, default=0.7)
    args = ap.parse_args()
    result = generate_draft(args.candidate_csv, args.existing_paths_yaml, args.out_yaml, min_priority=args.min_priority)
    print(json.dumps({'generated_count': result['generated_count'], 'out_yaml': args.out_yaml}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
