from app.agent.answer_composer import compose_answer
from app.agent.citation_guard import guard_claims
from app.agent.models import ToolResult


DB = {'evidence_id': 'ev_db', 'source_type': 'database', 'source_name': 'Chinook',
      'step_id': 'step_1', 'tool': 'database_query',
      'content': {'columns': ['count'], 'rows': [[3]], 'row_count': 1},
      'provenance': {'sql': 'SELECT COUNT(*) FROM Invoice', 'tables': ['Invoice']}}
DOC = {'evidence_id': 'ev_doc', 'source_type': 'document', 'source_name': 'rules.pdf',
       'step_id': 'step_2', 'tool': 'document_search',
       'content': '审核阈值为 500 元',
       'provenance': {'page': 2, 'heading_path': ['审核'], 'chunk_id': 'c1', 'text': '审核阈值为 500 元'}}


def test_database_and_document_claims_cited():
    output = compose_answer([DB, DOC], {'conflicts': [], 'missing': []})
    assert len(output['claims']) == 2
    assert output['claims'][0]['evidence_ids'] == ['ev_db']
    assert output['claims'][1]['evidence_ids'] == ['ev_doc']
    assert '第 2 页' in output['answer'] and output['sql'] == ['SELECT COUNT(*) FROM Invoice']


def test_database_answer_is_readable_and_keeps_evidence_ids_out_of_prose():
    evidence = {**DB, 'content': {'columns': ['customer_count'], 'rows': [[59]], 'row_count': 1}}
    result = ToolResult('database_query', True, data={
        'question': '数据库里有多少客户？', 'columns': ['customer_count'],
        'rows': [[59]], 'row_count': 1,
    })

    output = compose_answer([evidence], {'conflicts': [], 'missing': []}, {'step_1': result})

    assert output['answer'] == '数据库中共有 59位客户。'
    assert 'ev_db' not in output['answer']
    assert output['claims'][0]['evidence_ids'] == ['ev_db']


def test_unsupported_claim_dropped():
    valid, warnings = guard_claims([{'text': '不存在的事实', 'evidence_ids': ['ev_fake']}], [DB])
    assert valid == [] and warnings


def test_conflict_explicit_and_dual_citation():
    output = compose_answer([DB, DOC], {'conflicts': [{'topic': '阈值', 'values': [500, 600],
        'evidence_ids': ['ev_db', 'ev_doc']}], 'missing': []})
    assert output['claims'][-1]['evidence_ids'] == ['ev_db', 'ev_doc']
    assert '不一致' in output['answer']


def test_missing_evidence_not_fabricated():
    output = compose_answer([], {'conflicts': [], 'missing': ['缺少document证据']})
    assert output['claims'] == [] and '证据不足' in output['answer']


def test_existing_rag_answer_used_when_numbers_appear_in_original():
    result = ToolResult('document_search', True, {'answer': '审核阈值为 500 元'})
    output = compose_answer([DOC], {'conflicts': [], 'missing': []}, {'step_2': result})
    assert output['claims'][0]['text'] == '审核阈值为 500 元'


def test_rag_answer_with_uncited_number_does_not_dump_original():
    result = ToolResult('document_search', True, {'answer': '审核阈值为 900 元'})
    output = compose_answer([DOC], {'conflicts': [], 'missing': []}, {'step_2': result})
    assert '900' not in output['answer']
    assert '文档第' not in output['answer']
    assert output['warnings']


def test_numbered_document_summary_does_not_treat_list_indices_as_facts():
    result = ToolResult('document_search', True, {'answer': '1. 审核阈值为 500 元。\n2. 应先核对。'})
    output = compose_answer([DOC], {'conflicts': [], 'missing': []}, {'step_2': result})
    assert output['answer'].startswith('1. 审核阈值为 500 元')
