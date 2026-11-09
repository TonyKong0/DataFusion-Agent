from fastapi.testclient import TestClient

from app.api import rag as rag_api
from app.api import conversations as conversations_api
from app.conversation import store as conversation_store
from app.core.errors import AppError
from app.main import app


def test_legacy_single_document_request_keeps_working(monkeypatch):
    calls = []
    monkeypatch.setattr(rag_api, 'query', lambda *args: calls.append(args) or {
        'success': True, 'document_id': args[0], 'answer': 'legacy'})
    client = TestClient(app)

    response = client.post('/api/rag/query', json={
        'document_id': 'doc_' + 'a' * 32, 'question': '问题'})

    assert response.status_code == 200
    assert calls == [('doc_' + 'a' * 32, '问题', 5)]


def test_document_ids_scope_is_forwarded_and_deduplicated(monkeypatch):
    calls = []
    monkeypatch.setattr(rag_api, 'query_documents', lambda *args: calls.append(args) or {
        'success': True, 'document_ids': args[0], 'answer': 'scoped'})
    client = TestClient(app)

    response = client.post('/api/rag/query', json={
        'document_ids': ['doc_a', 'doc_b', 'doc_a'], 'question': '问题'})

    assert response.status_code == 200
    assert calls == [(['doc_a', 'doc_b'], '问题', 5)]


def test_rag_api_accepts_ten_distinct_document_ids(monkeypatch):
    ids = [f'doc_{index:02}' for index in range(10)]
    monkeypatch.setattr(rag_api, 'query_documents', lambda selected, question, top_k: {
        'success': True, 'document_ids': selected, 'answer': '十份资料'})

    response = TestClient(app).post('/api/rag/query', json={
        'document_ids': ids, 'question': '综合检索'})

    assert response.status_code == 200
    assert response.json()['document_ids'] == ids


def test_rag_api_rejects_eleven_distinct_document_ids():
    ids = [f'doc_{index:02}' for index in range(11)]

    response = TestClient(app).post('/api/rag/query', json={
        'document_ids': ids, 'question': '综合检索'})

    assert response.status_code == 422
    assert response.json()['error']['code'] == 'DOCUMENT_SELECTION_LIMIT'


def test_legacy_and_new_scope_are_accepted_only_when_equal(monkeypatch):
    ids = ['doc_' + 'c' * 32]
    calls = []
    monkeypatch.setattr(rag_api, 'query_documents', lambda *args: calls.append(args) or {
        'success': True, 'document_ids': args[0]})
    client = TestClient(app)

    accepted = client.post('/api/rag/query', json={
        'document_id': ids[0], 'document_ids': ids, 'question': '问题'})
    conflict = client.post('/api/rag/query', json={
        'document_id': ids[0], 'document_ids': [], 'question': '问题'})

    assert accepted.status_code == 200
    assert calls == [(ids, '问题', 5)]
    assert conflict.status_code == 422
    assert conflict.json()['error']['code'] == 'DOCUMENT_RANGE_CONFLICT'


def test_explicit_empty_scope_returns_clear_selection_error(monkeypatch):
    def no_scope(ids, question, top_k):
        raise AppError('DOCUMENT_SELECTION_REQUIRED', '请选择至少一份已索引文档后再提问', 422)

    monkeypatch.setattr(rag_api, 'query_documents', no_scope)
    response = TestClient(app).post('/api/rag/query', json={
        'document_ids': [], 'question': '问题'})

    assert response.status_code == 422
    assert response.json()['error']['code'] == 'DOCUMENT_SELECTION_REQUIRED'


def test_rag_conversation_can_be_created_before_document_selection(monkeypatch):
    monkeypatch.setattr(conversation_store, 'create', lambda owner, mode, document_id, document_name: {
        'id': 'f' * 32, 'owner_id': owner, 'mode': mode,
        'document_id': document_id, 'document_name': document_name})
    monkeypatch.setattr(conversations_api, 'load_document', lambda *_: (_ for _ in ()).throw(
        AssertionError('no document should be loaded')))

    response = TestClient(app).post('/api/conversations', json={'mode': 'rag'},
        headers={'X-Client-ID': 'client-id-123456789'})

    assert response.status_code == 200
    assert response.json()['document_id'] is None


def test_conversation_query_forwards_each_turn_document_ids(monkeypatch):
    calls = []
    monkeypatch.setattr(conversations_api.service, 'ask', lambda *args: calls.append(args) or {
        'success': True, 'document_ids': args[4], 'answer': 'ok'})
    ids = ['doc_' + '1' * 32, 'doc_' + '2' * 32]

    response = TestClient(app).post(f"/api/conversations/{'a' * 32}/query",
        json={'question': '比较两份资料', 'document_ids': ids},
        headers={'X-Client-ID': 'client-id-123456789'})

    assert response.status_code == 200
    assert calls[0][4] == ids
    assert calls[0][5] is None
    assert response.json()['document_ids'] == ids
