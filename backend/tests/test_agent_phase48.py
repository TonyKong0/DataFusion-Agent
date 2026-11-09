from fastapi.testclient import TestClient
from app.main import app
from app.agent.models import ToolResult


def test_agent_api_has_explainable_trace(monkeypatch):
    def fake_call(name, question, context):
        return ToolResult(name, True, {'sql': 'SELECT COUNT(*) AS n FROM Customer',
            'columns': ['n'], 'rows': [[59]], 'row_count': 1})
    monkeypatch.setattr('app.agent.executor.call_tool', fake_call)
    monkeypatch.setattr('app.agent.service.list_documents', lambda: [])
    response = TestClient(app).post('/api/agent/query', json={'question': '数据库里有多少客户？'})
    assert response.status_code == 200
    data = response.json()
    assert data['route']['route'] == 'DATABASE_ONLY'
    assert len(data['plan']['steps']) == 1
    assert data['execution']['trace'][0]['tool'] == 'database_query'
    assert data['evidence'][0]['provenance']['tables'] == ['Customer']
    assert 'Chain-of-Thought' not in str(data)
