from unittest.mock import patch
from app.agent.models import ToolResult
from app.agent.service import query
from fastapi.testclient import TestClient
from app.main import app


def test_clarification_prompt_is_returned_without_claims():
    with patch('app.agent.executor.call_tool', lambda n, q, c: ToolResult(n, True, {'question': '请说明数据源。'})), \
         patch('app.agent.service.list_documents', lambda: []):
        result = query('帮我看看。', allow_router_llm=False)
    assert result['route']['route'] == 'CLARIFICATION_REQUIRED'
    assert result['answer'] == '请说明数据源。'
    assert result['claims'] == []


def test_material_conversation_routes_short_person_question_to_selected_document():
    calls = []
    def tool(name, question, context):
        calls.append((name, question, context.get('document_ids')))
        return ToolResult(name, True, {'answer': '根据当前文档无法确定。', 'sources': []})
    with patch('app.agent.executor.call_tool', tool), \
         patch('app.agent.service.list_documents', lambda: []):
        result = query('欧阳修哪里人', document_ids=['doc_selected'],
                       force_document_route=True, allow_router_llm=False)
    assert result['route']['route'] == 'DOCUMENT_ONLY'
    assert calls == [('document_search', '欧阳修哪里人', ['doc_selected'])]


def test_cross_source_agent_routes_selected_material_reference_to_all_selected_documents():
    selected = ['doc_a', 'doc_b', 'doc_c']
    calls = []

    def tool(name, question, context):
        calls.append((name, context.get('document_ids')))
        return ToolResult(name, True, {'answer': '根据所选文档无法确定。', 'sources': []})

    with patch('app.agent.executor.call_tool', tool), \
         patch('app.agent.service.list_documents', lambda: []):
        result = query('这几篇分别讲什么？', document_ids=selected, allow_router_llm=False)

    assert result['route']['route'] == 'DOCUMENT_ONLY'
    assert calls == [('document_search', selected)]


def test_clarification_api_resumes_query(monkeypatch):
    monkeypatch.setattr('app.api.agent.resolve_clarification', lambda session_id, answer: {
        'question': '数据库里有多少客户？', 'cancelled': False})
    monkeypatch.setattr('app.agent.executor.call_tool', lambda n, q, c: ToolResult(n, True, {
        'sql': 'SELECT COUNT(*) AS n FROM Customer', 'columns': ['n'], 'rows': [[59]]}))
    monkeypatch.setattr('app.agent.service.list_documents', lambda: [])
    response = TestClient(app).post('/api/agent/clarify', json={'session_id': 'x', 'answer': '客户'})
    assert response.status_code == 200
    assert response.json()['route']['route'] == 'DATABASE_ONLY'
