import json
from pathlib import Path

import pytest

from app.core.version import APP_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLE_PATH = REPO_ROOT / 'docs' / 'metrics.json'


def _dig(node, dotted):
    for part in dotted.split('.'):
        node = node[part]
    return node


def _aggregate(items, spec):
    op = spec['op']
    if op == 'length':
        return len(items)
    values = [_dig(item, spec['field']) for item in items]
    if op == 'ratio_true':
        return round(sum(1 for value in values if value) / len(values), 4)
    if op == 'count_true':
        return sum(1 for value in values if value)
    if op == 'mean':
        return round(sum(values) / len(values), 1)
    raise AssertionError(f'unsupported aggregate op: {op}')


def _resolve(source):
    file = REPO_ROOT / source['file']
    if not file.exists():
        return None
    data = json.loads(file.read_text(encoding='utf-8'))
    node = _dig(data, source['path'])
    if 'aggregate' in source:
        return _aggregate(node, source['aggregate'])
    return node


def _table():
    return json.loads(TABLE_PATH.read_text(encoding='utf-8'))


def test_metrics_table_declares_current_app_version():
    assert _table()['app_version'] == APP_VERSION


def test_metric_ids_are_unique():
    ids = [metric['id'] for metric in _table()['metrics']]
    assert len(ids) == len(set(ids))


def test_measured_metrics_match_their_source_files():
    missing = []
    for metric in _table()['metrics']:
        if metric['status'] != 'measured':
            assert metric['value'] is None, metric['id']
            continue
        assert metric['source'], metric['id']
        source_file = REPO_ROOT / metric['source']['file']
        if not source_file.exists():
            assert metric['tracked'] is False, f"{metric['id']} 的来源未入库却标记为可追溯"
            missing.append(metric['id'])
            continue
        actual = _resolve(metric['source'])
        assert actual == pytest.approx(metric['value'], abs=1e-9), (
            f"{metric['id']} 真值表写 {metric['value']}，来源 {metric['source']['file']} 为 {actual}"
        )
    assert len(missing) <= 6, f'过多指标失去可核对来源：{missing}'


def test_unmeasured_metrics_are_not_backed_by_approximations():
    for metric in _table()['metrics']:
        if metric['status'] == 'unmeasured':
            assert metric['source'] is None
            assert metric.get('scope')


def test_every_conflict_has_resolution():
    conflicts = _table()['conflicts']
    assert {item['id'] for item in conflicts} >= {f'C{index}' for index in range(1, 7)}
    for item in conflicts:
        assert item['resolution'].strip()


V18_LIVE = 'docs/evaluation_agent_v1.8_live.json'


def _metric(metric_id):
    return next(item for item in _table()['metrics'] if item['id'] == metric_id)


def test_v18_indicators_are_measured_and_sourced():
    """The two long-standing unmeasured indicators now have a real source."""
    for metric_id in ('citation_accuracy', 'answer_faithfulness'):
        metric = _metric(metric_id)
        assert metric['status'] == 'measured'
        assert metric['value'] is not None
        assert metric['source']['file'] == V18_LIVE
        live = json.loads((REPO_ROOT / V18_LIVE).read_text(encoding='utf-8'))
        assert live['golden_set']['status'] == 'human-confirmed'
        assert live['golden_set']['metrics_eligible'] is True
        assert live['truncated'] is False


def test_v18_denominators_match_the_confirmed_layered_set():
    """26 answer cases / 4 clarification cases / 8 citation-criteria cases."""
    assert _metric('agent_v18_answer_judged_cases')['value'] == 26
    assert _metric('agent_v18_reject_judged_cases')['value'] == 4
    assert _metric('agent_v18_faithfulness_judged_cases')['value'] == 8
    assert _metric('agent_v18_execution_cases')['value'] == 30


def test_v18_citation_denominator_collapse_is_declared():
    """1 judged + 7 no-claim must stay visible; never present 1.0 as a 100% rate."""
    judged = _metric('agent_v18_citation_judged_cases')['value']
    no_claim = _metric('agent_v18_citation_no_claim_cases')['value']
    assert judged + no_claim == 8
    assert judged < 8, 'if all 8 cases cite, this guard must be revised with the report'
    scope = _metric('citation_accuracy')['scope']
    assert '不构成' in scope and 'no_claim' in scope


def test_v18_cross_version_conflict_is_resolved():
    conflict = next(item for item in _table()['conflicts'] if item['id'] == 'C7')
    assert '非同口径' in conflict['resolution']
    assert '趋势线' in conflict['resolution']
