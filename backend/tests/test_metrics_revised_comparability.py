"""Guard the before/after claim: the two live runs must be same-calibre.

If anyone changes the golden set, the grader, the materials, or the model and
still calls the two results comparable, these assertions fail.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / 'docs' / 'evaluation_agent_v1.8_live.json'
REVISED = REPO_ROOT / 'docs' / 'evaluation_agent_v1.8_revised_live.json'
TABLE = REPO_ROOT / 'docs' / 'metrics.json'


def _load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def test_both_runs_exist_and_are_untruncated():
    before, after = _load(BASELINE), _load(REVISED)
    assert before['truncated'] is False and after['truncated'] is False
    assert before['live_execution_cases'] == after['live_execution_cases'] == 30
    assert before['golden_set']['status'] == after['golden_set']['status'] == 'human-confirmed'
    assert before['golden_set']['metrics_eligible'] is True
    assert after['golden_set']['metrics_eligible'] is True


def test_environment_and_question_set_are_identical():
    before, after = _load(BASELINE), _load(REVISED)
    for key in ('mysql', 'indexed_documents', 'model', 'evaluation_materials',
                'indexed_material_matches', 'fallback_document_id',
                'document_selection_rule'):
        assert before['environment'][key] == after['environment'][key], key
    q_before = {row['question'] for row in before['execution_rows']}
    q_after = {row['question'] for row in after['execution_rows']}
    assert q_before == q_after and len(q_after) == 30
    assert before['live_answer_judged_cases'] == after['live_answer_judged_cases'] == 26


def test_no_case_regressed_while_four_improved():
    before, after = _load(BASELINE), _load(REVISED)
    b = {r['question']: r['verdict'] for r in before['execution_rows']}
    a = {r['question']: r['verdict'] for r in after['execution_rows']}
    order = {'wrong': 0, 'partial': 1, 'correct': 2}
    regressed = [q for q in b if order[a[q]] < order[b[q]]]
    improved = [q for q in b if order[a[q]] > order[b[q]]]
    assert regressed == []
    assert len(improved) == 4


def test_baseline_and_revised_metrics_coexist_in_truth_table():
    table = _load(TABLE)
    by_id = {item['id']: item for item in table['metrics']}
    assert by_id['agent_v18_answer_accuracy']['value'] < by_id['agent_v18_revised_answer_accuracy']['value']
    assert (by_id['agent_v18_answer_acceptable_rate']['value']
            == by_id['agent_v18_revised_answer_acceptable_rate']['value'])
    assert by_id['agent_v18_answer_accuracy']['source']['file'] == 'docs/evaluation_agent_v1.8_live.json'
    for metric in (item for item in table['metrics']
                   if item['id'].startswith('agent_v18_revised_')):
        assert metric['status'] == 'measured'
        assert metric['source']['file'] == 'docs/evaluation_agent_v1.8_revised_live.json'


def test_citation_denominator_recovery_is_declared():
    table, before, after = _load(TABLE), _load(BASELINE), _load(REVISED)
    by_id = {item['id']: item for item in table['metrics']}
    assert by_id['agent_v18_citation_judged_cases']['value'] == 1
    assert by_id['agent_v18_revised_citation_judged_cases']['value'] == 7
    assert by_id['agent_v18_revised_citation_no_claim_cases']['value'] == 1
    assert (after['citation_judged_cases'] + after['citation_no_claim_cases']) == 8
    assert (before['citation_judged_cases'] + before['citation_no_claim_cases']) == 8
    conflict = next(item for item in table['conflicts'] if item['id'] == 'C8')
    assert '非受控观测' in conflict['resolution']
    assert '同口径前后对比' in conflict['resolution']
