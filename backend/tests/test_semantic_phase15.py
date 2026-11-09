import json

from app.semantic import element_extractor as extractor


def test_simple_question_skips_llm(monkeypatch):
    monkeypatch.setattr(extractor, 'chat', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('LLM called')))
    result = extractor.extract_elements('前10个客户')
    assert result['fallback_used'] is False
    assert result['error'] is None


def test_vague_question_uses_structured_fallback(monkeypatch):
    calls = []
    def fake_chat(*args, **kwargs):
        calls.append(kwargs)
        return json.dumps({'elements': [
            {'type': 'metric', 'raw_value': '卖得比较猛', 'canonical_value': 'sales'},
            {'type': 'sort', 'raw_value': '卖得比较猛', 'canonical_value': 'DESC'},
        ]})
    monkeypatch.setattr(extractor, 'chat', fake_chat)
    result = extractor.extract_elements('找点卖得比较猛的歌')
    assert result['fallback_used'] is True
    assert result['error'] is None
    assert {item.type for item in result['elements']} >= {'entity', 'metric', 'sort'}
    assert calls == [{'json_mode': True}]


def test_invalid_json_retries_once_then_fails_closed(monkeypatch):
    calls = []
    def fake_chat(*args, **kwargs):
        calls.append(1)
        return 'not json'
    monkeypatch.setattr(extractor, 'chat', fake_chat)
    result = extractor.extract_elements('找点卖得比较猛的歌')
    assert result['error'] == 'ELEMENT_EXTRACTION_FAILED'
    assert len(calls) == 2


def test_unsupported_llm_entity_rejected(monkeypatch):
    monkeypatch.setattr(extractor, 'chat', lambda *args, **kwargs: json.dumps({'elements': [
        {'type': 'entity', 'raw_value': '未知', 'canonical_value': 'Unknown'}]}))
    assert extractor.extract_elements('未知')['error'] == 'ELEMENT_EXTRACTION_FAILED'
