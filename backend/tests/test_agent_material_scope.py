from app.agent import service
from app.core.errors import AppError
from app.agent.multimodal_router import route_multimodal
from app.agent.tools import document_tool
import pytest
from fastapi.testclient import TestClient
from app.api import agent as agent_api
from app.main import app


def test_material_tool_routes_chart_database_question_to_both_sources():
    routed = route_multimodal(
        '数据库中各季度销售额与材料折线图趋势是否一致？', ['doc_' + 'a' * 32])

    assert routed['route'] == 'CROSS_SOURCE'
    assert routed['required_tools'] == ['chart_analyze', 'database_query']


def test_agent_query_routes_table_questions_to_material_tools(monkeypatch):
    calls = []
    monkeypatch.setattr('app.agent.multimodal_service.query',
                        lambda question, ids: calls.append((question, ids)) or {'answer': '表格答案'})

    result = service.query('表格中2025年销售额是多少？',
                           document_ids=['doc_' + 'b' * 32])

    assert result['answer'] == '表格答案'
    assert calls == [('表格中2025年销售额是多少？', ['doc_' + 'b' * 32])]


def test_stateless_agent_api_accepts_compatible_and_per_turn_material_fields(monkeypatch):
    calls = []
    monkeypatch.setattr(agent_api, 'query', lambda question, document_id=None,
                        formula_id=None, document_ids=None: calls.append(
                            (document_id, document_ids)) or {'success': True, 'answer': 'ok'})
    selected = ['doc_' + 'a' * 32, 'doc_' + 'b' * 32]

    response = TestClient(app).post('/api/agent/query', json={
        'question': '查询已选择的材料', 'document_id': selected[0], 'document_ids': selected})

    assert response.status_code == 200
    assert calls == [(selected[0], selected)]


def test_document_tool_searches_the_exact_multi_material_scope(monkeypatch):
    ids = ['doc_' + 'a' * 32, 'doc_' + 'b' * 32]
    calls = []
    monkeypatch.setattr(document_tool, 'query_documents',
                        lambda selected, question, top_k: calls.append((selected, question, top_k)) or {
                            'answer': '材料答案', 'sources': []})

    result = document_tool.document_search('两份材料都讲了什么？', {'document_ids': ids})

    assert result.success is True
    assert calls == [(ids, '两份材料都讲了什么？', 5)]


def test_document_tool_does_not_guess_when_explicit_scope_is_empty(monkeypatch):
    monkeypatch.setattr(document_tool, 'list_documents', lambda: [
        {'document_id': 'doc_' + 'c' * 32, 'status': 'indexed'}])

    with pytest.raises(AppError) as error:
        document_tool.document_search('材料中写了什么？', {'document_ids': []})

    assert error.value.code == 'DOCUMENT_SELECTION_REQUIRED'
