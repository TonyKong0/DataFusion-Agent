"""Regression for the post-v1.8 material-coverage and routing revision.

The golden set and the grader are deliberately untouched: these tests assert
that the *system output* now states what the retrieved materials do not record,
and that a selected material is treated as an explicit source cue.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from app.agent.answer_composer import compose_answer
from app.agent.material_coverage import (
    absence_subject, material_coverage_note, needs_material_coverage,
)
from app.agent.models import ToolResult
from app.agent.router import route_query
from app.services import rag_service

DB = {'evidence_id': 'ev_db', 'source_type': 'database', 'source_name': 'Chinook',
      'step_id': 'step_1', 'tool': 'database_query',
      'content': {'columns': ['customer_count'], 'rows': [[59]], 'row_count': 1},
      'provenance': {'sql': 'SELECT COUNT(*) FROM customer', 'tables': ['customer']}}
DB_TOOL = ToolResult('database_query', True, data={
    'question': '数据库里有多少客户，文档里记录了多少？', 'columns': ['customer_count'],
    'rows': [[59]], 'row_count': 1,
})
DOCUMENT_MISSING = {'conflicts': [], 'missing': ['缺少document证据']}


def _grader():
    """Load the unchanged v1.8 grader directly, without importing test modules."""
    backend = Path(__file__).resolve().parents[1]
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    if str(backend / 'tests') not in sys.path:
        sys.path.insert(0, str(backend / 'tests'))
    path = backend / 'scripts' / 'evaluate_agent_v5.py'
    spec = importlib.util.spec_from_file_location('eval_v5_coverage_check', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_absence_subject_names_the_asked_item():
    assert absence_subject('文档规定的审核阈值是多少，数据库里有多少订单超过这个值？') == '审核阈值'
    assert absence_subject('') == '本次所问信息'


def test_note_states_absence_without_inventing_a_value():
    note = material_coverage_note('文档规定的金额上限是多少', has_claims=True)
    assert '所检索材料中未记载' in note
    assert '无法' in note and '证据不足' in note
    assert '仅来自数据库' in note
    assert not any(char.isdigit() for char in note)


def test_needs_coverage_only_when_document_evidence_is_missing():
    assert needs_material_coverage(DOCUMENT_MISSING, '数据库中共有 59位客户。')
    assert not needs_material_coverage({'missing': []}, '数据库中共有 59位客户。')
    assert not needs_material_coverage(DOCUMENT_MISSING, '所检索材料中未记载审核阈值。')


def test_cross_source_answer_explicitly_states_material_absence():
    output = compose_answer([DB], DOCUMENT_MISSING, {'step_1': DB_TOOL},
                            question='数据库里有多少客户，文档里记录了多少？')
    assert '数据库中共有 59位客户。' in output['answer']
    assert '所检索材料中未记载' in output['answer']
    assert '无法据此形成文档结论' in output['answer']
    assert output['claims'][0]['evidence_ids'] == ['ev_db']
    assert not output['sql'] == []


def test_generic_refusal_is_replaced_but_keeps_insufficient_wording():
    output = compose_answer([], DOCUMENT_MISSING)
    assert output['claims'] == []
    assert '证据不足' in output['answer']
    assert '所检索材料中未记载' in output['answer']


def test_existing_explicit_absence_is_not_duplicated():
    output = compose_answer([DB], DOCUMENT_MISSING, {'step_1': DB_TOOL},
                            question='文档规定的审核阈值是多少')
    assert output['answer'].count('所检索材料中未记载') == 1


def test_single_source_database_answer_is_unchanged():
    output = compose_answer([DB], {'conflicts': [], 'missing': []}, {'step_1': DB_TOOL})
    assert output['answer'] == '数据库中共有 59位客户。'


def test_selected_material_routes_concept_question_to_documents():
    for question in ('流派名称从哪里读取？', '曲目属于哪张专辑应沿什么字段关联？',
                     '这些服务规则是真实门店政策吗？', '发票金额超过 5 美元是否代表退款已批准？'):
        routed = route_query(question, allow_llm=False, selected_document_count=1)
        assert routed['route'] == 'DOCUMENT_ONLY', question
        assert routed['required_tools'] == ['document_search']


def test_no_selected_material_keeps_previous_database_routing():
    routed = route_query('流派名称从哪里读取？', allow_llm=False)
    assert routed['route'] == 'DATABASE_ONLY'


def test_cross_source_and_clarification_routes_are_unchanged():
    cross = route_query('文档规定的审核阈值是多少，数据库里有多少订单超过这个值？',
                        allow_llm=False, selected_document_count=1)
    assert cross['route'] == 'CROSS_SOURCE'
    clarify = route_query('帮我看看。', allow_llm=False)
    assert clarify['route'] == 'CLARIFICATION_REQUIRED'


def test_rag_keeps_explicit_absence_instead_of_generic_unknown(monkeypatch):
    monkeypatch.setattr(rag_service, 'load_document', lambda _: {'status': 'indexed'})
    monkeypatch.setattr(rag_service, 'ready', lambda _: True)
    monkeypatch.setattr(rag_service, 'search', lambda *args: [
        {'chunk_id': 'c1', 'document_id': 'doc_a', 'filename': 'demo.pdf', 'page': 3,
         'text': '文档只提到复核筛选条件。', 'score': .8}])
    monkeypatch.setattr(rag_service, 'chat_json', lambda *args: {
        'answer': '所检索材料中未记载审核阈值，材料只提到复核筛选条件。',
        'used_chunk_ids': []})
    result = rag_service.query('doc_a', '审核阈值是多少？', 5)
    assert '未记载审核阈值' in result['answer']
    assert result['answer'] != rag_service.UNKNOWN
    assert result['sources'] == []


def test_unchanged_grader_now_marks_the_revised_answer_correct():
    judge = _grader().judge_answer
    case = {'match_type': 'numeric', 'golden_numeric': 59, 'golden': '59'}
    before = '数据库中共有 59位客户。'
    after = before + '\n\n' + material_coverage_note('文档里记录了多少客户', has_claims=True)
    assert judge(before, case)['verdict'] == 'partial'
    assert judge(after, case)['verdict'] == 'correct'
