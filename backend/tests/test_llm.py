import pytest
import httpx
from types import SimpleNamespace
from pydantic import SecretStr
from app.llm import deepseek_client as client
from app.llm.usage import collect_usage
from app.core.errors import AppError


def test_json_response(monkeypatch):
    monkeypatch.setattr(client, 'chat', lambda *args, **kwargs: '{"answer":"ok"}')
    assert client.chat_json('system', 'user')['answer'] == 'ok'


@pytest.mark.parametrize('content', ['invalid', '[]', 'null'])
def test_invalid_json(monkeypatch, content):
    monkeypatch.setattr(client, 'chat', lambda *args, **kwargs: content)
    with pytest.raises(AppError) as error:
        client.chat_json('system', 'user')
    assert error.value.code == 'LLM_INVALID_RESPONSE'


def test_chat_retries_transient_upstream_error(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(1)
        request = httpx.Request('POST', 'https://example.test/chat/completions')
        if len(calls) == 1:
            response = httpx.Response(503, request=request)
        else:
            response = httpx.Response(200, request=request,
                                      json={'choices': [{'message': {'content': 'ok'}}]})
        return response

    monkeypatch.setattr(client._client, 'post', fake_post)
    monkeypatch.setattr(client.time, 'sleep', lambda _: None)
    monkeypatch.setattr(client, 'get_settings', lambda: SimpleNamespace(
        deepseek_api_key=SecretStr('test'), deepseek_model='deepseek-chat',
        deepseek_base_url='https://example.test'))
    assert client.chat('system', 'user') == 'ok'
    assert len(calls) == 2


def test_request_usage_capture_records_provider_tokens_without_content(monkeypatch):
    def fake_post(*args, **kwargs):
        request = httpx.Request('POST', 'https://example.test/chat/completions')
        return httpx.Response(200, request=request, json={
            'choices': [{'message': {'content': 'ok'}}],
            'usage': {'prompt_tokens': 17, 'completion_tokens': 5, 'total_tokens': 22},
        })

    monkeypatch.setattr(client._client, 'post', fake_post)
    monkeypatch.setattr(client, 'get_settings', lambda: SimpleNamespace(
        deepseek_api_key=SecretStr('test'), deepseek_model='deepseek-chat',
        deepseek_base_url='https://example.test'))
    with collect_usage() as usage:
        assert client.chat('system', 'private question') == 'ok'

    assert usage.to_dict() == {'api_requests': 1, 'reported_requests': 1,
                               'prompt_tokens': 17, 'completion_tokens': 5,
                               'total_tokens': 22}
