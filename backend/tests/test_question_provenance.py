"""Regressions for raw input surviving context rewrites and clarification."""
import pytest

from app.conversation import service


@pytest.mark.parametrize('mode', ['database', 'rag', 'agent'])
def test_rewritten_question_keeps_original_in_response_and_saved_turn(monkeypatch, mode):
    raw = '列出所有的乐音类型'
    interpreted = '列出所有的音乐类型'
    conversation = {'id': 'a' * 32, 'mode': mode, 'document_id': None,
                    'summary': '之前查询过音乐类型', 'state': {}}
    saved, calls = [], []
    monkeypatch.setattr(service.store, 'get', lambda *args: conversation)
    monkeypatch.setattr(service.store, 'recent_turns', lambda *args: [])
    monkeypatch.setattr(service.store, 'recent_document_turns', lambda *args: [])
    monkeypatch.setattr(service.store, 'memory_turns', lambda *args: [])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: saved.append(args))
    monkeypatch.setattr(service, '_rewrite', lambda *args: (interpreted, None, None))

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        # Reproduce a downstream worker receiving only interpreted text.
        return {'success': True, 'answer': '结果', 'semantic': {
            'original_question': interpreted, 'normalized_question': interpreted,
            'changes': [], 'canonical_question': interpreted}}

    monkeypatch.setattr(service, '_run', run)
    result = service.ask('owner', conversation['id'], raw)
    assert calls[0][0][1] == interpreted
    assert calls[0][1]['original_question'] == raw
    assert result['original_question'] == result['semantic']['original_question'] == raw
    assert result['semantic']['interpreted_question'] == interpreted
    assert result['semantic']['normalized_question'] == interpreted
    assert result['semantic']['changes'][0] == {'type': 'context', 'from': raw, 'to': interpreted}
    assert saved[0][2:4] == (raw, interpreted)
    assert saved[0][4]['semantic']['original_question'] == raw


def test_database_worker_receives_raw_input_without_changing_sql_input(monkeypatch):
    from app.services import nl2sql_service
    seen = {}

    def query(question, **kwargs):
        seen.update(question=question, **kwargs)
        return {'success': True}

    monkeypatch.setattr(nl2sql_service, 'query', query)
    service._run('database', '列出音乐类型', None, original_question='列出乐音类型')
    assert seen == {'question': '列出音乐类型', 'original_question': '列出乐音类型'}


def test_agent_database_tool_keeps_raw_input_and_tool_instruction(monkeypatch):
    from app.agent.tools import database_tool
    monkeypatch.setattr(database_tool, 'query', lambda question, **kwargs: {
        'success': True, 'semantic': {'original_question': kwargs['original_question'],
                                    'normalized_question': question, 'changes': []}})
    result = database_tool.database_query('统计歌曲数', {'original_question': '按刚才条件统计它们'})
    assert result.data['semantic']['original_question'] == '按刚才条件统计它们'
    assert result.data['semantic']['interpreted_question'] == '统计歌曲数'


def test_clarification_keeps_initial_question_in_persisted_response(monkeypatch):
    from app.semantic import clarification_manager
    from app.services import nl2sql_service
    raw = '看看可乎的情况'
    interpreted = '列出客户'
    conversation = {'id': 'a' * 32, 'mode': 'database', 'document_id': None,
                    'summary': '', 'state': {'pending_clarification_id': 'session'}}
    saved = []
    monkeypatch.setattr(service.store, 'get', lambda *args: conversation)
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: saved.append(args))
    monkeypatch.setattr(clarification_manager, 'resolve_clarification', lambda *args: {
        'question': interpreted, 'original_question': raw, 'confirmed': True, 'cancelled': False})
    monkeypatch.setattr(nl2sql_service, 'query', lambda *args, **kwargs: {
        'success': True, 'semantic': {'original_question': kwargs['original_question'],
                                    'normalized_question': interpreted, 'changes': []}})
    result = service.clarify('owner', conversation['id'], '客户')
    assert result['original_question'] == result['semantic']['original_question'] == raw
    assert saved[0][2] == '客户'
    assert saved[0][4]['original_question'] == raw
