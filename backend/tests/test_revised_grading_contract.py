"""Guard the dual-contract disclosure: no golden edits, no silent number swaps.

The revised grading contract lifts one inappropriate condition (requiring a
document-side note on pure database single-source questions).  These tests make
sure that (a) historical results stay reproducible under the legacy contract,
(b) the source files and the human-confirmed golden set are untouched, and
(c) both contracts are reported side by side in metrics.json.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import evaluate_agent_v5

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / 'docs'
GOLDEN = REPO_ROOT / 'backend' / 'tests' / 'golden_answers_v1.8.json'
REGRADE = DOCS / 'evaluation_agent_revised_contract_regrade.json'
BASELINE = DOCS / 'evaluation_agent_v1.8_live.json'
AFTER = DOCS / 'evaluation_agent_v1.8_revised_live.json'
TABLE = DOCS / 'metrics.json'

GOLDEN_SHA256 = 'd6ced24363de2b60e4b9959246c6349eaea7172ddab6f7344a258e71a2fa1399'


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_human_confirmed_golden_set_is_byte_identical():
    assert _sha256(GOLDEN) == GOLDEN_SHA256, '人工确认黄金集不得随口径修订改动'
    meta = _load(GOLDEN)
    assert meta['status'] == 'human-confirmed'
    assert len(meta['cases']) == 30


def test_unknown_contract_is_rejected():
    with pytest.raises(ValueError):
        evaluate_agent_v5.judge_answer('59', {'match_type': 'numeric',
                                              'golden_numeric': 59}, contract='invented')


def test_legacy_contract_reproduces_both_archived_runs():
    golden = evaluate_agent_v5.load_golden_cases(GOLDEN)
    for path in (BASELINE, AFTER):
        for row in _load(path)['execution_rows']:
            case = golden.get(row['question'])
            assert case is not None
            assert evaluate_agent_v5.judge_answer(
                row.get('answer') or '', case)['verdict'] == row['verdict']


def test_revised_contract_only_touches_database_single_source_cases():
    golden = evaluate_agent_v5.load_golden_cases(GOLDEN)
    for path in (BASELINE, AFTER):
        changed = []
        for row in _load(path)['execution_rows']:
            if row.get('layer') == 'S2-C' or row.get('verdict') is None:
                continue
            case = golden[row['question']]
            old = evaluate_agent_v5.judge_answer(row['answer'] or '', case)['verdict']
            new = evaluate_agent_v5.judge_answer(
                row['answer'] or '', case, contract='revised')['verdict']
            if old != new:
                changed.append((row['layer'], old, new,
                                evaluate_agent_v5._document_side_expected(case)))
        assert len(changed) == 6
        assert {item[0] for item in changed} == {'S2-A'}
        assert {item[1:3] for item in changed} == {('partial', 'correct')}
        assert not any(item[3] for item in changed)


def test_document_side_rule_uses_confirmed_criteria_only():
    assert not evaluate_agent_v5._document_side_expected(
        {'question': '数据库里有多少客户？', 'match_type': 'numeric'})
    assert evaluate_agent_v5._document_side_expected(
        {'question': '数据库里有多少客户，文档里记录了多少？'})
    assert evaluate_agent_v5._document_side_expected(
        {'question': '流派名称从哪里读取？', 'target_document': '07_store_faq.txt'})
    assert evaluate_agent_v5._document_side_expected(
        {'question': '示例手册中的门槛是多少？', 'expected_citation': '04_x.docx'})


def test_regrade_file_is_consistent_and_delta_is_constant():
    data = _load(REGRADE)
    summary = data['summary']
    assert summary['judged_cases'] == 26
    assert summary['revised_affected_cases'] == 6
    assert summary['legacy_baseline_accuracy'] == pytest.approx(0.1923076923077)
    assert summary['legacy_after_accuracy'] == pytest.approx(0.3461538461538)
    assert summary['revised_baseline_accuracy'] == pytest.approx(0.4230769230769)
    assert summary['revised_after_accuracy'] == pytest.approx(0.5769230769231)
    assert summary['delta_is_constant'] is True
    assert summary['acceptable_rate_unchanged'] is True
    for name in ('baseline', 'after'):
        run = data['runs'][name]
        assert run['regressions'] == []
        assert len(run['verdict_changes']) == 6
        assert _sha256(REPO_ROOT / run['source_file']) == run['source_sha256']


def test_both_contracts_coexist_in_truth_table():
    table = _load(TABLE)
    by_id = {item['id']: item for item in table['metrics']}
    legacy = by_id['agent_v18_answer_accuracy']
    contract = by_id['agent_contract_revised_baseline_accuracy']
    assert legacy['value'] < contract['value']
    assert legacy['source']['file'] == 'docs/evaluation_agent_v1.8_live.json'
    assert contract['source']['file'] == \
        'docs/evaluation_agent_revised_contract_regrade.json'
    for metric_id in ('agent_contract_revised_baseline_accuracy',
                      'agent_contract_revised_after_accuracy'):
        assert by_id[metric_id]['status'] == 'measured'
    conflict = next(item for item in table['conflicts'] if item['id'] == 'C9')
    assert '双口径' in conflict['resolution'] or '并列' in conflict['resolution']
