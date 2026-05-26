import csv
import json
from pathlib import Path

from causalgate.agent.evidence_reader import AgentEvidenceReader
from causalgate.agent.runner import run_agent


def _write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as fh:
        for row in rows:
            fh.write(json.dumps(row) + '\n')


def _evidence_dir(tmp_path: Path) -> Path:
    out = tmp_path / 'out'
    _write_csv(out / 'effect_estimates.csv', [
        {
            'treatment': 'price_discount',
            'outcome': 'conversion_rate',
            'effect_estimate': '0.12',
            'ci_low': '0.03',
            'ci_high': '0.20',
            'support_n': '120',
            'estimator_used': 'provided_effect',
            'robustness_status': 'pass',
            'negative_control_status': 'pass',
            'placebo_status': 'pass',
            'sensitivity_status': 'pass',
            'effect_claim_status': 'validated_effect',
        }
    ])
    _write_csv(out / 'sensitivity_analysis.csv', [
        {'treatment': 'price_discount', 'outcome': 'conversion_rate', 'sensitivity_status': 'pass', 'sensitivity_risk': 'low'}
    ])
    _write_csv(out / 'causal_contract.csv', [
        {
            'treatment': 'price_discount',
            'outcome': 'conversion_rate',
            'allowed_use': 'recommendation_only',
            'forbidden_use': 'autonomous_execution',
            'requires_review': 'true',
        }
    ])
    _write_jsonl(out / 'veto' / 'causal_authority_cards.jsonl', [
        {
            'treatment': 'price_discount',
            'outcome': 'conversion_rate',
            'evidence_strength': 'strong',
            'decision_authority': 'allow',
            'veto_ready': True,
        }
    ])
    return out


def test_evidence_reader_builds_bundle_from_structured_outputs(tmp_path):
    out = _evidence_dir(tmp_path)
    reader = AgentEvidenceReader(output_dir=out)
    bundle = reader.read({'action_name': 'price_discount', 'treatment': 'price_discount', 'outcome': 'conversion_rate'})

    assert bundle.evidence_tier in {'medium', 'strong'}
    assert bundle.matched_effect_estimates
    assert bundle.best_estimation_query['effect_estimate'] == 0.12
    assert bundle.usable_for_autonomous_action is False
    assert 'causal_contract' in bundle.evidence_present
    assert bundle.decision_hints['autonomous_execution'] == 'forbidden_by_contract'


def test_agent_attaches_evidence_and_blocks_contract_only_autonomy(tmp_path):
    out = _evidence_dir(tmp_path)
    result = run_agent(
        'Abbassa il prezzo del 20% per aumentare conversioni',
        candidate_actions=[
            {
                'action_name': 'price_discount',
                'candidate_action': 'price_discount',
                'action_type': 'state_change',
                'target_resource': 'pricing',
                'treatment': 'price_discount',
                'outcome': 'conversion_rate',
                'trusted_runtime_context': {
                    'environment': 'production',
                    'risk_level': 'high',
                    'approval_present': False,
                    'rollback_available': False,
                },
            }
        ],
        evidence_output_dir=out,
        execute_tools=False,
    )

    assert result['evidence_tier'] in {'medium', 'strong'}
    assert result['usable_for_autonomous_action'] is False
    assert result['status'] == 'evidence_review_required'
    assert result['executed'] is False
    assert result['blocked'] is True
    assert result['needs_user_confirmation'] is True
    assert result['brain_result']['selected']['causal_estimation']['estimated'] is True
