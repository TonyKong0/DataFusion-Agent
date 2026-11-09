import pytest

from app.agent.multimodal_router import route_multimodal
from app.core.errors import AppError
from app.api import multimodal as multimodal_api
from app.main import app
from fastapi.testclient import TestClient


def test_multimodal_route_accepts_ten_documents():
    ids = [f'doc_{index:02}' for index in range(10)]

    result = route_multimodal('联合检索这些资料', ids)

    assert len(result['document_ids']) == 10
    assert result['route'] == 'MULTI_DOCUMENT'


def test_multimodal_route_deduplicates_before_enforcing_the_limit():
    ids = [f'doc_{index:02}' for index in range(10)]

    result = route_multimodal('联合检索这些资料', ids + [ids[0]])

    assert result['document_ids'] == ids


def test_multimodal_route_rejects_eleven_distinct_documents():
    ids = [f'doc_{index:02}' for index in range(11)]

    with pytest.raises(AppError) as error:
        route_multimodal('联合检索这些资料', ids)

    assert error.value.code == 'TOO_MANY_DOCUMENTS'
    assert error.value.status_code == 422


def test_multimodal_api_accepts_ten_document_ids(monkeypatch):
    ids = [f'doc_{index:02}' for index in range(10)]
    monkeypatch.setattr(multimodal_api, 'query', lambda question, selected: {
        'success': True, 'route': route_multimodal(question, selected)})

    response = TestClient(app).post('/api/multimodal/query', json={
        'question': '联合检索这些资料', 'document_ids': ids})

    assert response.status_code == 200
    assert len(response.json()['route']['document_ids']) == 10


def test_multimodal_api_rejects_eleven_distinct_document_ids():
    ids = [f'doc_{index:02}' for index in range(11)]

    response = TestClient(app).post('/api/multimodal/query', json={
        'question': '联合检索这些资料', 'document_ids': ids})

    assert response.status_code == 422
    assert response.json()['error']['code'] == 'TOO_MANY_DOCUMENTS'
