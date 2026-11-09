from fastapi.testclient import TestClient

from app.api import schema as schema_api
from app.main import app
from tests.test_schema_phase24 import linked_schema as schema_fixture


def test_link_endpoint_returns_explainable_real_schema(monkeypatch):
    snapshot = schema_fixture.__wrapped__()
    monkeypatch.setattr(schema_api, 'get_metadata', lambda: snapshot)
    response = TestClient(app).post('/api/schema/link', json={
        'question': '每个客户消费了多少钱', 'elements': [
            {'type': 'entity', 'canonical_value': 'Customer', 'raw_value': '客户'}]})
    assert response.status_code == 200
    data = response.json()
    assert data['success']
    assert set(data['selected_tables']) == {'customer', 'invoice'}
    assert 'invoice.Total' in data['selected_columns']
    assert data['candidate_tables'] and data['candidate_columns']


def test_link_endpoint_validates_question():
    assert TestClient(app).post('/api/schema/link', json={'question': ''}).status_code == 422
