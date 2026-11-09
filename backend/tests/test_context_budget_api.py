from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api import conversations
from app.main import app


def test_context_budget_config_exposes_default_and_supported_range(monkeypatch):
    monkeypatch.setattr(conversations, 'get_settings', lambda: SimpleNamespace(max_context_tokens=12000))
    response = TestClient(app).get('/api/conversations/context-budget')

    assert response.status_code == 200
    assert response.json() == {
        'success': True,
        'default_tokens': 12000,
        'minimum_tokens': 1000,
        'maximum_tokens': 50000,
    }


def test_conversation_query_forwards_optional_budget_and_keeps_legacy_client(monkeypatch):
    calls = []
    monkeypatch.setattr(conversations.service, 'ask', lambda *args: (
        calls.append(args) or {'success': True, 'answer': 'ok'}))
    client = TestClient(app)
    headers = {'X-Client-ID': 'client-id-1234567890'}

    response = client.post('/api/conversations/' + 'a' * 32 + '/query', headers=headers,
                           json={'question': '提问', 'context_limit_tokens': 24000})
    legacy = client.post('/api/conversations/' + 'a' * 32 + '/query', headers=headers,
                         json={'question': '旧请求'})

    assert response.status_code == 200
    assert legacy.status_code == 200
    assert calls[0][-1] == 24000
    assert calls[1][-1] is None


def test_conversation_query_rejects_context_budget_outside_supported_range():
    response = TestClient(app).post('/api/conversations/' + 'a' * 32 + '/query',
        headers={'X-Client-ID': 'client-id-1234567890'},
        json={'question': '提问', 'context_limit_tokens': 50001})

    assert response.status_code == 422


def test_clarification_forwards_context_budget(monkeypatch):
    calls = []
    monkeypatch.setattr(conversations.service, 'clarify', lambda *args: (
        calls.append(args) or {'success': True, 'answer': 'ok'}))

    response = TestClient(app).post('/api/conversations/' + 'a' * 32 + '/clarify',
        headers={'X-Client-ID': 'client-id-1234567890'},
        json={'answer': '补充', 'context_limit_tokens': 17000})

    assert response.status_code == 200
    assert calls == [('client-id-1234567890', 'a' * 32, '补充', 17000)]


def test_service_applies_browser_budget_and_returns_peak_context_usage(monkeypatch):
    from app.conversation import service
    from app.agent.budget import current_budget

    saved = []
    conversation = {'id': 'b' * 32, 'mode': 'database', 'document_id': None,
                    'summary': '', 'state': {}}
    monkeypatch.setattr(service.store, 'get', lambda *_: conversation)
    monkeypatch.setattr(service.store, 'recent_turns', lambda *_: [])
    monkeypatch.setattr(service.store, 'memory_turns', lambda *_: [])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: saved.append(args))

    def execute(*_args, **_kwargs):
        budget = current_budget()
        budget.consume('当前问题', system='固定系统提示')
        budget.record_usage(31, 7)
        return {'success': True, 'answer': 'ok'}

    monkeypatch.setattr(service, '_run', execute)

    result = service.ask('owner', 'b' * 32, '当前问题', context_limit_tokens=24000)

    assert result['context_usage']['budget_tokens'] == 24000
    assert result['context_usage']['measurement'] == 'provider'
    assert result['context_usage']['used_tokens'] == 31
    assert result['context_usage']['remaining_tokens'] == 23969
    assert result['context_usage']['breakdown']['system_prompt'] > 0
    assert saved[0][4]['context_usage'] == result['context_usage']
