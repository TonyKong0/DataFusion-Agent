import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.semantic.clarification_manager import create_clarification, resolve_clarification


def _validation(**changes):
    result = {'missing': [], 'ambiguities': [], 'unsupported': [], 'low_confidence': False,
              'conflicts': [], 'error': None}
    result.update(changes)
    return result


def test_single_choice_resumes_original_question():
    card = create_clarification('查 Alex', _validation(missing=['entity']))
    assert card['kind'] == 'single_choice'
    assert '客户' in card['options']
    assert resolve_clarification(card['session_id'], '客户')['question'] == '查 Alex 客户'


def test_free_text_resumes_original_question():
    card = create_clarification('客户增长率是多少', _validation(missing=['time_range']))
    assert card['kind'] == 'free_text'
    assert resolve_clarification(card['session_id'], '2020年')['question'] == '客户增长率是多少 2020年'


def test_missing_time_preserves_question_even_if_growth_is_unsupported():
    card = create_clarification('客户增长率是多少',
                                _validation(missing=['time_range'], unsupported=['metric:growth_rate']))
    assert resolve_clarification(card['session_id'], '2020年')['question'] == '客户增长率是多少 2020年'


def test_confirm_and_cancel():
    card = create_clarification('查询客户', _validation(low_confidence=True))
    assert card['kind'] == 'confirm'
    assert resolve_clarification(card['session_id'], '确认')['confirmed'] is True
    cancelled = create_clarification('查询客户', _validation(low_confidence=True))
    assert resolve_clarification(cancelled['session_id'], '取消')['cancelled'] is True


def test_invalid_choice_does_not_consume_session():
    card = create_clarification('查 Alex', _validation(missing=['entity']))
    with pytest.raises(Exception):
        resolve_clarification(card['session_id'], '不存在')
    assert resolve_clarification(card['session_id'], '客户')['question'] == '查 Alex 客户'


def test_ambiguous_entity_choice_removes_unselected_entity():
    card = create_clarification('客户和员工', _validation(ambiguities=['entity']))
    resolved = resolve_clarification(card['session_id'], '客户')
    assert resolved['question'] == '客户'
    assert resolved['original_question'] == '客户和员工'


def test_unsupported_question_can_be_rewritten():
    card = create_clarification('Rock 歌曲', _validation(unsupported=['filter:genre']))
    assert resolve_clarification(card['session_id'], '查询歌曲')['question'] == '查询歌曲'


def test_clarify_api_continues_query(monkeypatch):
    from app.api import semantic
    card = create_clarification('查 Alex', _validation(missing=['entity']))
    monkeypatch.setattr(semantic, 'query', lambda question, confirmed=False, clarification_completed=False, original_question=None:
                        {'success': True, 'question': question, 'confirmed': confirmed, 'sql': 'SELECT 1'})
    response = TestClient(app).post('/api/semantic/clarify', json={'session_id': card['session_id'], 'answer': '客户'})
    assert response.status_code == 200
    assert response.json()['question'] == '查 Alex 客户'


def test_clarify_api_cancel_does_not_query(monkeypatch):
    from app.api import semantic
    card = create_clarification('查询客户', _validation(low_confidence=True))
    monkeypatch.setattr(semantic, 'query', lambda *args, **kwargs: pytest.fail('query called'))
    response = TestClient(app).post('/api/semantic/clarify', json={'session_id': card['session_id'], 'answer': '取消'})
    assert response.status_code == 200
    assert response.json()['sql'] is None
