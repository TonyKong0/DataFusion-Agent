"""Focused regressions for bounded context without real model calls."""
import json
import pytest

from app.conversation import service
from app.core.errors import AppError


@pytest.fixture(autouse=True)
def _mock_scoped_history_for_existing_service_tests(monkeypatch):
    """Existing tests supply persisted turns through the recent_turns stub."""
    monkeypatch.setattr(service.store, 'recent_document_turns',
        lambda identifier, document_ids, limit, legacy_document_id=None:
            service.store.recent_turns(identifier, limit))


def _conversation(mode='database', document_id=None):
    return {'id': 'a' * 32, 'mode': mode, 'document_id': document_id,
            'summary': '较早的对话摘要', 'state': {}}


@pytest.mark.parametrize('question', ['最流行的音乐', '最火的应音乐是哪个'])
def test_ambiguous_popularity_starts_persisted_clarification_without_model(monkeypatch, question):
    conversation = _conversation()
    saved = []
    monkeypatch.setattr(service.store, 'get', lambda *args: conversation)
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: saved.append(args))
    monkeypatch.setattr(service, 'chat_json', lambda *args: (_ for _ in ()).throw(AssertionError('no model')))
    monkeypatch.setattr(service, '_run', lambda *args: (_ for _ in ()).throw(AssertionError('no SQL')))

    result = service.ask('owner', conversation['id'], question)

    assert result['need_clarification'] is True
    assert result['clarification']['options'] == ['按销量查歌曲', '按销量查音乐类型', '取消']
    assert '歌曲' in result['answer'] and '音乐类型' in result['answer']
    assert saved[0][-1]['pending_popularity_intent']['original_question'] == question


def test_popularity_choice_resolves_saved_intent_without_rewrite(monkeypatch):
    conversation = _conversation()
    saved = []
    queries = []
    monkeypatch.setattr(service.store, 'get', lambda *args: conversation)
    monkeypatch.setattr(service.store, 'recent_turns', lambda *args: [])
    monkeypatch.setattr(service.store, 'memory_turns', lambda *args: [])
    def save(*args):
        saved.append(args)
        conversation['state'] = args[-1]
    monkeypatch.setattr(service.store, 'append_turn', save)
    monkeypatch.setattr(service, 'chat_json', lambda *args: (_ for _ in ()).throw(AssertionError('no rewrite')))
    def run(mode, question, document_id, formula_id=None, original_question=None):
        queries.append(question)
        return {'success': True, 'answer': '查到结果', 'sources': [], 'trace': []}
    monkeypatch.setattr(service, '_run', run)

    service.ask('owner', conversation['id'], '最流行的音乐')
    result = service.ask('owner', conversation['id'], '按销量查歌曲')

    assert not result.get('need_clarification')
    assert queries == ['最流行的歌曲按销量衡量是哪首？']
    assert saved[-1][2] == '按销量查歌曲'
    assert saved[-1][3] == queries[0]
    assert 'pending_popularity_intent' not in conversation['state']


def test_unavailable_rewrite_does_not_block_independent_question(monkeypatch):
    conversation = _conversation()
    monkeypatch.setattr(service.store, 'get', lambda *args: conversation)
    monkeypatch.setattr(service.store, 'recent_turns', lambda *args: [
        {'question': '列出音乐类型', 'resolved_question': '列出音乐类型', 'answer': '25 种'}])
    monkeypatch.setattr(service.store, 'memory_turns', lambda *args: [])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: None)
    monkeypatch.setattr(service, 'chat_json', lambda *args: (_ for _ in ()).throw(AppError('LLM_ERROR', 'unavailable', 503)))
    monkeypatch.setattr(service, '_run', lambda mode, question, document_id, formula_id=None, original_question=None:
                        {'success': True, 'answer': question, 'sources': [], 'trace': []})

    result = service.ask('owner', conversation['id'], '列出所有音乐类型')

    assert result['answer'] == '列出所有音乐类型'
    assert not result.get('need_clarification')


@pytest.mark.parametrize(('message', 'expected'), [
    ('欧阳修', '所选文档中如何介绍欧阳修？'),
    ('醉翁亭记', '所选文档中如何介绍醉翁亭记？'),
    ('machine learning', '所选文档中如何介绍machine learning？'),
    ('欧阳修哪里人', '欧阳修哪里人'),
    ('这篇文档讲什么？', '这篇文档讲什么？'),
])
def test_material_topic_fragments_expand_without_changing_explicit_questions(message, expected):
    assert service._material_question(message) == expected


def test_new_question_uses_existing_query_without_context_llm(monkeypatch):
    saved = []
    conversation = _conversation()
    conversation['summary'] = ''
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: conversation)
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: saved.append(args))
    monkeypatch.setattr(service, 'chat_json', lambda *args: (_ for _ in ()).throw(AssertionError('unexpected rewrite')))
    monkeypatch.setattr(service, '_run', lambda mode, question, document_id, formula_id=None, original_question=None: {'success': True, 'answer': '答案'})
    result = service.ask('owner', 'a' * 32, '有多少客户？')
    assert result['resolved_question'] == '有多少客户？'
    assert saved[0][2:4] == ('有多少客户？', '有多少客户？')


def test_previous_question_uses_history_route_from_persisted_turn(monkeypatch):
    saved = []
    conversation = _conversation()
    conversation['state'] = {'pending_context_question': '旧问题', 'pending_clarification_id': 'stale'}
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: conversation)
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [
        {'question': '列出所有音乐类型', 'resolved_question': '列出所有音乐类型', 'answer': '25 种'}])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: saved.append(args))
    monkeypatch.setattr(service.store, 'history_turns', lambda *args: [
        {'question': '列出所有音乐类型', 'answer': '25 种'}])
    monkeypatch.setattr(service, '_answer_from_history', lambda question, turns, scope, limit:
                        f'你刚才问了：{turns[-1]["question"]}。')
    monkeypatch.setattr(service, '_run', lambda *args: (_ for _ in ()).throw(AssertionError('must not query SQL')))
    def answer_from_history(system, user):
        assert '列出所有音乐类型' in user
        return {'action': 'history', 'history_scope': 'last'}
    monkeypatch.setattr(service, 'chat_json', answer_from_history)

    result = service.ask('owner', 'a' * 32, '我刚才问了什么问题')

    assert '列出所有音乐类型' in result['answer']
    assert saved[0][2:4] == ('我刚才问了什么问题', '我刚才问了什么问题')
    assert 'pending_context_question' not in saved[0][-1]
    assert 'pending_clarification_id' not in saved[0][-1]


def test_schema_table_count_uses_live_metadata_and_is_saved(monkeypatch):
    from app.db import mysql
    saved = []
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: _conversation())
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: saved.append(args))
    monkeypatch.setattr(mysql, 'database_status', lambda: {'database': 'chinook', 'tables': 11})
    monkeypatch.setattr(service, '_run', lambda *args: (_ for _ in ()).throw(AssertionError('must not query SQL')))

    result = service.ask('owner', 'a' * 32, '我有几张表')

    assert result['answer'] == '当前数据库 chinook 共有 11 张表。'
    assert saved[0][2] == '我有几张表'


def test_new_topic_still_sends_persisted_history_to_model(monkeypatch):
    calls = {}
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: _conversation())
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [
        {'question': '列出所有音乐类型', 'resolved_question': '列出所有音乐类型', 'answer': '25 种'}])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: None)

    def interpret(system, user):
        calls['prompt'] = user
        return {'action': 'query', 'standalone_question': '列出所有员工'}

    monkeypatch.setattr(service, 'chat_json', interpret)
    def run(mode, question, document_id, formula_id=None, original_question=None):
        calls['query'] = question
        return {'success': True, 'answer': '员工列表'}
    monkeypatch.setattr(service, '_run', run)

    service.ask('owner', 'a' * 32, '列出所有员工')

    assert '列出所有音乐类型' in calls['prompt']
    assert '较早的对话摘要' in calls['prompt']
    assert calls['query'] == '列出所有员工'


def test_agent_followup_preserves_bound_pdf_and_cross_source_intent(monkeypatch):
    document_id = 'doc_' + 'f' * 32
    conversation = _conversation('agent', document_id)
    conversation['document_name'] = '研究报告.pdf'
    calls = {}
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: conversation)
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [{
        'question': '数据库里有多少客户？', 'resolved_question': '数据库里有多少客户？',
        'answer': '数据库中有 59 位客户。', 'result': {'route': {'route': 'DATABASE_ONLY'}}}])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: calls.setdefault('saved', args))

    def rewrite(system, user):
        context = json.loads(user)
        assert context['bound_document'] == {'document_id': document_id,
                                              'document_name': '研究报告.pdf'}
        assert context['recent'][0]['source_route'] == 'DATABASE_ONLY'
        assert '59 位客户' in context['recent'][0]['answer']
        return {'action': 'query', 'standalone_question': '核对数据库客户数量，并与当前文档中的客户数量比较'}

    monkeypatch.setattr(service, 'chat_json', rewrite)
    def run(mode, question, selected_document_id, formula_id=None, document_ids=None, original_question=None):
        calls['run'] = (mode, question, selected_document_id)
        calls['document_ids'] = document_ids
        return {'success': True, 'answer': '核验后的比较结果', 'sources': []}
    monkeypatch.setattr(service, '_run', run)

    result = service.ask('owner', 'a' * 32, '这个数和文档里的一样吗？')

    assert calls['run'] == ('agent', '核对数据库客户数量，并与当前文档中的客户数量比较', document_id)
    assert result['resolved_question'] == calls['run'][1]
    assert calls['saved'][2] == '这个数和文档里的一样吗？'


def test_unlisted_memory_phrase_uses_history_route(monkeypatch):
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: _conversation())
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [
        {'question': '列出所有音乐类型', 'resolved_question': '列出所有音乐类型', 'answer': '25 种'}])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: None)
    monkeypatch.setattr(service.store, 'history_turns', lambda *args: [
        {'question': '列出所有音乐类型', 'answer': '25 种'}])
    monkeypatch.setattr(service, '_answer_from_history', lambda question, turns, scope, limit:
                        f'你之前让我{turns[-1]["question"]}。')
    monkeypatch.setattr(service, 'chat_json', lambda system, user: {
        'action': 'history', 'history_scope': 'substantive'})
    monkeypatch.setattr(service, '_run', lambda *args: (_ for _ in ()).throw(AssertionError('no SQL')))

    result = service.ask('owner', 'a' * 32, '你还记得我之前让你做了什么吗？')

    assert result['answer'] == '你之前让我列出所有音乐类型。'


def test_typo_in_history_request_uses_full_persisted_answer(monkeypatch):
    first_answer = '共列出 25 种音乐类型：' + 'Rock、Jazz、' * 80
    history = [
        {'id': 1, 'question': '列出所有音乐类型', 'answer': first_answer},
        {'id': 2, 'question': '我过程提问了什么', 'answer': '旧的回忆回答'},
        {'id': 3, 'question': '我刚刚问了什么', 'answer': '旧的回忆回答'},
    ]
    calls = []
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: _conversation())
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [
        {'question': item['question'], 'resolved_question': item['question'],
         'answer': item['answer']} for item in history[-2:]])
    monkeypatch.setattr(service.store, 'history_turns', lambda identifier: history)
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: None)
    monkeypatch.setattr(service, '_run', lambda *args: (_ for _ in ()).throw(AssertionError('no SQL')))

    def model(system, user):
        calls.append(user)
        if len(calls) == 1:
            assert '我过程提问了什么' in user
            return {'action': 'history'}
        assert first_answer in user
        return {'answer': '你之前实际查询的是所有音乐类型。'}

    monkeypatch.setattr(service, 'chat_json', model)
    result = service.ask('owner', 'a' * 32, '我过程提问了什么')

    assert result['answer'] == '你之前实际查询的是所有音乐类型。'
    assert len(calls) == 2


def test_broad_history_question_excludes_memory_chatter(monkeypatch):
    turns = [
        {'id': 1, 'question': '列出所有音乐类型', 'answer': '25 种', 'conversation_history': False},
        {'id': 2, 'question': '我过程提问了什么', 'answer': '你问了音乐类型', 'conversation_history': True},
        {'id': 3, 'question': '我刚刚问了什么', 'answer': '你问了什么', 'conversation_history': False},
    ]

    def model(system, user):
        assert '列出所有音乐类型' in user
        assert '我过程提问了什么' not in user
        assert '我刚刚问了什么' not in user
        return {'answer': '你实际查询过所有音乐类型。'}

    monkeypatch.setattr(service, 'chat_json', model)
    answer = service._answer_from_history('我一共问了你哪些问题', turns, 'substantive')
    assert answer == '你实际查询过所有音乐类型。'


def test_history_answer_fits_the_selected_context_budget(monkeypatch):
    from app.agent.budget import estimate_tokens
    turns = [{'id': index, 'question': f'问题 {index}', 'answer': '历史答案内容' * 500}
             for index in range(1, 9)]

    def model(system, user):
        assert estimate_tokens(system + user) <= 1000
        assert '当前问题' in user
        return {'answer': '按预算裁剪历史后完成回答。'}

    monkeypatch.setattr(service, 'chat_json', model)
    answer = service._answer_from_history('当前问题', turns, 'substantive', 1000)

    assert answer == '按预算裁剪历史后完成回答。'


def test_history_scope_corrects_overly_literal_model_choice():
    assert service._history_scope('我一共问了你哪些问题', 'all') == 'substantive'
    assert service._history_scope('我过程提问了什么', 'all') == 'substantive'
    assert service._history_scope('我刚刚问了什么', 'substantive') == 'last'
    assert service._history_scope('把我问过的所有问题逐字列出来', 'substantive') == 'all'


@pytest.mark.parametrize(('question', 'scope'), [
    ('我刚刚问了哪些问题', 'recent'),
    ('我刚才问了什么问题', None),
    ('我在这个对话一起问了哪些问题', 'substantive'),
    ('我在这段对话一共问过什么', 'substantive'),
    ('本次会话里我问过什么问题', 'substantive'),
    ('把我问过的所有问题逐字列出来', 'all'),
    ('岳阳楼记里问了哪些问题', None),
    ('我问的岳阳楼记作者是谁', None),
])
def test_question_history_intent_is_distinct_from_material_question(question, scope):
    assert service._question_history_scope(question) == scope


@pytest.mark.parametrize('mode', ['database', 'rag', 'agent'])
def test_whole_conversation_question_list_uses_persisted_originals_without_tools(monkeypatch, mode):
    selected = 'doc_' + 'a' * 32
    conversation = _conversation(mode, selected if mode != 'database' else None)
    history = [
        {'id': 1, 'question': '岳阳楼记作者时谁', 'answer': '范仲淹', 'conversation_history': False},
        {'id': 2, 'question': '我刚刚问了哪些问题', 'answer': '旧历史回答', 'conversation_history': False},
        {'id': 3, 'question': '醉翁亭记讲了啥', 'answer': '文章概要', 'conversation_history': False},
    ]
    monkeypatch.setattr(service.store, 'get', lambda *_: conversation)
    monkeypatch.setattr(service.store, 'recent_turns', lambda *_: [])
    monkeypatch.setattr(service.store, 'recent_document_turns', lambda *_: [])
    monkeypatch.setattr(service.store, 'history_turns', lambda *_: history)
    monkeypatch.setattr(service.store, 'memory_turns', lambda *_: [])
    monkeypatch.setattr(service.store, 'append_turn', lambda *_: None)
    monkeypatch.setattr(service, 'chat_json', lambda *_: (_ for _ in ()).throw(AssertionError('no model')))
    monkeypatch.setattr(service, '_run', lambda *_args, **_kwargs:
                        (_ for _ in ()).throw(AssertionError('no retrieval or SQL')))

    kwargs = {'document_ids': [selected]} if mode != 'database' else {}
    result = service.ask('owner', conversation['id'], '我在这个对话一起问了哪些问题', **kwargs)

    assert result['conversation_history'] is True
    assert '岳阳楼记作者时谁' in result['answer']
    assert '醉翁亭记讲了啥' in result['answer']
    assert '我刚刚问了哪些问题' not in result['answer']
    assert '共 2 个' in result['answer']


def test_recent_plural_history_lists_questions_instead_of_only_last(monkeypatch):
    history = [
        {'question': '第一篇作者是谁', 'answer': '甲'},
        {'question': '第二篇讲了什么', 'answer': '乙'},
    ]
    answer = service._question_history_answer(history, 'recent')
    assert '第一篇作者是谁' in answer and '第二篇讲了什么' in answer


def test_agent_accepts_null_clarification_from_successful_result(monkeypatch):
    saved = []
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: _conversation('agent'))
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: saved.append(args))
    monkeypatch.setattr(service, '_run', lambda mode, question, document_id, formula_id=None, document_ids=None, original_question=None: {
        'success': True, 'answer': '共有 59 位客户。', 'clarification': None,
        'sources': [], 'trace': []})
    result = service.ask('owner', 'a' * 32, '数据库里有多少客户？')
    assert result['answer'] == '共有 59 位客户。'
    assert saved[0][-1].get('pending_clarification_id') is None


def test_agent_session_persists_the_exact_per_turn_material_scope(monkeypatch):
    conversation = _conversation('agent', 'doc_' + 'a' * 32)
    saved = []
    calls = []
    selected = ['doc_' + 'b' * 32, 'doc_' + 'c' * 32]
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: conversation)
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: saved.append(args))
    monkeypatch.setattr(service, '_rewrite', lambda question, *_: (question, None, None))
    monkeypatch.setattr(service, '_run', lambda mode, question, document_id, formula_id=None, document_ids=None, original_question=None:
                        calls.append((mode, document_ids)) or {
                            'success': True, 'answer': '多份材料答案', 'document_ids': document_ids,
                            'sources': [], 'trace': []})

    result = service.ask('owner', 'a' * 32, '两份材料共同说明什么？', document_ids=selected)

    assert calls == [('agent', selected)]
    assert result['document_ids'] == selected
    assert saved[0][4]['document_ids'] == selected


def test_agent_session_rejects_more_than_ten_materials(monkeypatch):
    conversation = _conversation('agent')
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: conversation)
    selected = ['doc_' + f'{index:032x}' for index in range(11)]

    with pytest.raises(AppError) as error:
        service.ask('owner', 'a' * 32, '检索资料', document_ids=selected)

    assert error.value.code == 'DOCUMENT_SELECTION_LIMIT'


def test_agent_clarification_reuses_the_pending_turn_material_scope(monkeypatch):
    selected = ['doc_' + 'b' * 32, 'doc_' + 'c' * 32]
    conversation = _conversation('agent', 'doc_' + 'a' * 32)
    conversation['state'] = {'pending_clarification_id': 'clarify-id',
                             'agent_document_ids': selected}
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: conversation)
    from app.semantic import clarification_manager
    monkeypatch.setattr(clarification_manager, 'resolve_clarification', lambda *_: {
        'cancelled': False, 'question': '用材料阈值筛选发票？',
        'confirmed': True, 'original_question': '刚才那两份材料里的阈值呢？'})
    calls = []
    monkeypatch.setattr('app.agent.service.query', lambda question, document_id=None,
                        formula_id=None, document_ids=None, original_question=None: calls.append(document_ids) or {
                            'success': True, 'answer': '已按两份材料继续查询。'})
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: None)

    result = service.clarify('owner', 'a' * 32, '按新版本')

    assert calls == [selected]
    assert result['document_ids'] == selected


def test_followup_rewrites_with_bounded_history_and_keeps_document(monkeypatch):
    calls = {}
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: _conversation('rag', 'doc_' + 'b' * 32))
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [{
        'question': '这篇文章是谁写的？', 'resolved_question': '这篇文章是谁写的？',
        'answer': '根据第 1 页，作者是范仲淹。'}])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: None)
    def rewrite(system, user):
        calls['prompt'] = user
        return {'standalone_question': '范仲淹为什么写这篇文章？', 'need_clarification': False}
    monkeypatch.setattr(service, 'chat_json', rewrite)
    def run(mode, question, document_id, formula_id=None, document_ids=None, original_question=None):
        calls['run'] = (mode, question, document_id)
        calls['document_ids'] = document_ids
        return {'success': True, 'answer': '有引用的答案', 'sources': [{'chunk_id': 'c1', 'page': 2}]}
    monkeypatch.setattr(service, '_run', run)
    result = service.ask('owner', 'a' * 32, '他为什么写这篇文章？')
    assert calls['run'] == ('rag', '范仲淹为什么写这篇文章？', 'doc_' + 'b' * 32)
    assert calls['document_ids'] == ['doc_' + 'b' * 32]
    assert '这篇文章是谁写的？' in calls['prompt']
    assert result['original_question'] == '他为什么写这篇文章？'


def test_document_followup_uses_persisted_turns_for_selected_scope(monkeypatch):
    first, second = ['doc_' + character * 32 for character in 'ab']
    calls = {}
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: _conversation('rag', first))
    def scoped_turns(identifier, document_ids, limit, legacy_document_id=None):
        calls['scope'] = document_ids
        return [{
                'question': '这篇文章是谁写的？', 'resolved_question': '这篇文章是谁写的？',
                'answer': '作者是范仲淹。'}]

    monkeypatch.setattr(service.store, 'recent_document_turns', scoped_turns)
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: None)

    def rewrite(system, user):
        calls['rewrite'] = user
        return {'action': 'query', 'standalone_question': '范仲淹在这篇文章中表达了什么观点？'}

    monkeypatch.setattr(service, 'chat_json', rewrite)
    monkeypatch.setattr(service, '_run', lambda mode, question, document_id,
                        formula_id=None, document_ids=None, original_question=None:
                        calls.update(question=question, documents=document_ids) or
                        {'success': True, 'answer': '有引用的回答', 'sources': []})

    service.ask('owner', 'a' * 32, '这篇文章中他的观点呢？', document_ids=[second])

    assert calls['scope'] == [second]
    assert '作者是范仲淹' in calls['rewrite']
    assert calls['question'] == '范仲淹在这篇文章中表达了什么观点？'
    assert calls['documents'] == [second]


def test_document_history_question_uses_full_persisted_chat(monkeypatch):
    selected = 'doc_' + 'a' * 32
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: _conversation('rag', selected))
    monkeypatch.setattr(service.store, 'recent_document_turns', lambda *args: [])
    monkeypatch.setattr(service.store, 'history_turns', lambda identifier: [
        {'id': 1, 'question': '第一篇的作者是谁？', 'answer': '范仲淹。'},
        {'id': 2, 'question': '第二篇的作者是谁？', 'answer': '欧阳修。'},
    ])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: None)
    monkeypatch.setattr(service, 'chat_json', lambda system, user: {'answer': '刚才问的是第二篇的作者。'})
    monkeypatch.setattr(service, '_run', lambda *args, **kwargs:
                        (_ for _ in ()).throw(AssertionError('must not search documents')))

    result = service.ask('owner', 'a' * 32, '我刚才问了什么问题？', document_ids=[selected])

    assert result['answer'] == '刚才问的是第二篇的作者。'
    assert result['conversation_history'] is True


def test_document_summary_persists_per_selected_scope(monkeypatch):
    first, second = ['doc_' + character * 32 for character in 'ab']
    first_key = json.dumps([first], ensure_ascii=False)
    second_key = json.dumps([second], ensure_ascii=False)
    conversation = _conversation('rag', first)
    conversation['state'] = {'document_summaries': {
        first_key: '第一篇的旧摘要', second_key: '第二篇的旧摘要'}}
    turns = [{'question': f'第一篇问题 {index}', 'resolved_question': f'问题 {index}',
              'answer': f'第一篇回答 {index}'} for index in range(3)]
    saved = []
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: conversation)
    monkeypatch.setattr(service.store, 'recent_document_turns', lambda *args: turns)
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: saved.append(args))

    def rewrite(system, user):
        assert '第一篇的旧摘要' in user
        assert '第二篇的旧摘要' not in user
        return {'action': 'query', 'standalone_question': '第一篇后续问题'}

    monkeypatch.setattr(service, 'chat_json', rewrite)
    monkeypatch.setattr(service, '_run', lambda *args, **kwargs:
                        {'success': True, 'answer': '新回答', 'sources': []})

    service.ask('owner', 'a' * 32, '还有呢？', document_ids=[first])

    summaries = saved[0][-1]['document_summaries']
    assert '第一篇问题 0' in summaries[first_key]
    assert summaries[second_key] == '第二篇的旧摘要'


def test_ambiguous_followup_asks_before_running_tools(monkeypatch):
    saved = []
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: _conversation())
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [{
        'question': '客户和员工', 'resolved_question': '客户和员工', 'answer': '包含两类对象。'}])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: saved.append(args))
    monkeypatch.setattr(service, 'chat_json', lambda *args: {
        'need_clarification': True, 'clarification_question': '你指客户还是员工？'})
    monkeypatch.setattr(service, '_run', lambda *args: (_ for _ in ()).throw(AssertionError('must clarify')))
    result = service.ask('owner', 'a' * 32, '他们有多少？')
    assert result['context_clarification'] is True
    assert saved[0][-1]['pending_context_question'] == '他们有多少？'


def test_selected_document_resolves_explicit_document_reference(monkeypatch):
    selected = 'doc_' + 'b' * 32
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: _conversation('rag', 'doc_' + 'a' * 32))
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [{
        'question': '比较两份课件', 'resolved_question': '比较两份课件',
        'answer': '涉及醉翁亭记和岳阳楼记。'}])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: None)
    monkeypatch.setattr(service, 'chat_json', lambda *args: (_ for _ in ()).throw(AssertionError('selection resolves reference')))
    calls = []
    monkeypatch.setattr(service, '_run', lambda mode, question, document_id, formula_id=None, document_ids=None, original_question=None:
                        calls.append((question, document_ids)) or {'success': True, 'answer': '文档概要',
                            'document_ids': document_ids, 'sources': []})

    result = service.ask('owner', 'a' * 32, '这个文档讲了啥？', document_ids=[selected])

    assert not result.get('need_clarification')
    assert calls == [('这个文档讲了啥？', [selected])]


def test_reasking_after_document_selection_does_not_duplicate_pending_question(monkeypatch):
    selected = 'doc_' + 'b' * 32
    conversation = _conversation('rag', 'doc_' + 'a' * 32)
    conversation['state'] = {'pending_context_question': '这个文档讲了啥？'}
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: conversation)
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: None)
    calls = []
    monkeypatch.setattr(service, '_run', lambda mode, question, document_id, formula_id=None, document_ids=None, original_question=None:
                        calls.append((question, document_ids)) or {'success': True, 'answer': '文档概要',
                            'document_ids': document_ids, 'sources': []})

    service.ask('owner', 'a' * 32, '这个文档讲了啥？', document_ids=[selected])

    assert calls == [('这个文档讲了啥？', [selected])]


def test_switching_pdf_does_not_rewrite_question_to_previous_pdf(monkeypatch):
    previous = 'doc_' + 'a' * 32
    selected = 'doc_' + 'b' * 32
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: _conversation('rag', previous))
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [{
        'question': '这篇讲的啥？', 'resolved_question': '醉翁亭记讲的啥？',
        'answer': '醉翁亭记的内容', 'result': {'document_ids': [previous]}}])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: None)
    monkeypatch.setattr(service, 'chat_json', lambda *args: (_ for _ in ()).throw(AssertionError('old PDF must not rewrite')))
    calls = []
    monkeypatch.setattr(service, '_run', lambda mode, question, document_id, formula_id=None, document_ids=None, original_question=None:
                        calls.append((question, document_ids)) or {'success': True, 'answer': '岳阳楼记的内容',
                            'document_ids': document_ids, 'sources': []})

    service.ask('owner', 'a' * 32, '这篇讲的是啥？', document_ids=[selected])

    assert calls == [('这篇讲的是啥？', [selected])]


def test_selected_two_pdfs_resolve_this_two_reference(monkeypatch):
    selected = ['doc_' + 'a' * 32, 'doc_' + 'b' * 32]
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: _conversation('rag', selected[0]))
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [{
        'question': '这两篇讲的啥', 'resolved_question': '这两篇讲的啥',
        'answer': '根据所选文档无法确定。', 'result': {'document_ids': selected}}])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: None)
    monkeypatch.setattr(service, 'chat_json', lambda *args: (_ for _ in ()).throw(AssertionError('scope resolves both PDFs')))
    calls = []
    monkeypatch.setattr(service, '_run', lambda mode, question, document_id, formula_id=None, document_ids=None, original_question=None:
                        calls.append((question, document_ids)) or {'success': True, 'answer': '两篇概要',
                            'document_ids': document_ids, 'sources': []})

    service.ask('owner', 'a' * 32, '这两篇讲的啥', document_ids=selected)

    assert calls == [('这两篇讲的啥', selected)]


def test_selected_three_pdfs_define_the_scope_for_this_three(monkeypatch):
    selected = ['doc_' + character * 32 for character in 'abc']
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: _conversation('rag', selected[0]))
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [{
        'question': '第一篇讲什么', 'resolved_question': '第一篇讲什么',
        'answer': '旧回答', 'result': {'document_ids': [selected[0]]}}])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: None)
    monkeypatch.setattr(service, 'chat_json', lambda *args: (_ for _ in ()).throw(AssertionError('scope is explicit')))
    calls = []
    monkeypatch.setattr(service, '_run', lambda mode, question, document_id, formula_id=None, document_ids=None, original_question=None:
                        calls.append((question, document_ids)) or {'success': True, 'answer': '三篇概要',
                            'document_ids': document_ids, 'sources': []})

    result = service.ask('owner', 'a' * 32, '这三篇分别讲什么？', document_ids=selected)

    assert calls == [('这三篇分别讲什么？', selected)]
    assert result['document_ids'] == selected


@pytest.mark.parametrize('question', ['这几篇讲的是什么？', '请总结这些材料'])
def test_agent_selected_material_reference_uses_current_scope_without_clarifying(monkeypatch, question):
    selected = ['doc_' + character * 32 for character in 'abc']
    conversation = _conversation('agent', selected[0])
    monkeypatch.setattr(service.store, 'get', lambda *_: conversation)
    monkeypatch.setattr(service.store, 'recent_turns', lambda *_: [{
        'question': '之前的问题', 'resolved_question': '之前的问题', 'answer': '旧回答',
        'result': {'document_ids': selected}}])
    monkeypatch.setattr(service.store, 'memory_turns', lambda *_: [])
    monkeypatch.setattr(service.store, 'append_turn', lambda *_: None)
    monkeypatch.setattr(service, 'chat_json', lambda *_: (_ for _ in ()).throw(
        AssertionError('当前选择已经消除了材料范围歧义')))
    calls = []
    monkeypatch.setattr(service, '_run', lambda mode, resolved, document_id,
                        formula_id=None, document_ids=None, original_question=None: calls.append(
                            (mode, resolved, document_ids)) or {
                                'success': True, 'answer': '分别介绍各篇内容',
                                'document_ids': document_ids, 'sources': []})

    result = service.ask('owner', conversation['id'], question, document_ids=selected)

    assert calls == [('agent', question, selected)]
    assert result['answer'] == '分别介绍各篇内容'


def test_rag_clarification_retains_selected_scope(monkeypatch):
    selected = ['doc_' + character * 32 for character in 'ab']
    saved = []
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: _conversation('rag', selected[0]))
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [{
        'question': '比较作者', 'resolved_question': '比较作者', 'answer': '两位作者',
        'result': {'document_ids': selected}}])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: saved.append(args))
    monkeypatch.setattr(service, 'chat_json', lambda *args: {
        'need_clarification': True, 'clarification_question': '你指哪位作者？'})
    monkeypatch.setattr(service, '_run', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('must clarify')))

    result = service.ask('owner', 'a' * 32, '他为什么写？', document_ids=selected)

    assert result['document_ids'] == selected
    assert saved[0][-1]['pending_context_document_ids'] == selected


def test_switching_scope_discards_pending_question_from_old_pdf(monkeypatch):
    first, second = ['doc_' + character * 32 for character in 'ab']
    conversation = _conversation('rag', first)
    conversation['state'] = {'pending_context_question': '旧文档讲什么？',
                             'pending_context_document_ids': [first]}
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: conversation)
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: None)
    calls = []
    monkeypatch.setattr(service, '_run', lambda mode, question, document_id, formula_id=None, document_ids=None, original_question=None:
                        calls.append((question, document_ids)) or {'success': True, 'answer': '新文档作者',
                            'document_ids': document_ids, 'sources': []})

    service.ask('owner', 'a' * 32, '作者是谁？', document_ids=[second])

    assert calls == [('作者是谁？', [second])]


def test_rag_turn_scope_overrides_legacy_session_document_and_is_stored(monkeypatch):
    saved = []
    conversation = _conversation('rag', 'doc_' + 'a' * 32)
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: conversation)
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: saved.append(args))
    calls = {}

    def run(mode, question, document_id, formula_id=None, document_ids=None, original_question=None):
        calls['scope'] = document_ids
        return {'success': True, 'answer': '回答', 'document_ids': document_ids,
                'document_names': [{'document_id': item, 'filename': f'{item}.pdf'}
                                   for item in document_ids],
                'sources': [{'document_id': document_ids[1], 'filename': f'{document_ids[1]}.pdf',
                             'chunk_id': 'source-c', 'page': 2, 'text': '引用原文'}]}

    monkeypatch.setattr(service, '_run', run)
    requested = ['doc_' + 'b' * 32, 'doc_' + 'c' * 32]

    result = service.ask('owner', 'a' * 32, '总结两份资料', document_ids=requested)

    assert calls['scope'] == requested
    assert result['document_ids'] == requested
    assert saved[0][4]['sources'][0]['document_id'] == requested[1]
    assert saved[0][4]['document_names'][1]['filename'] == f'{requested[1]}.pdf'


def test_rag_omitted_scope_uses_legacy_document_and_empty_scope_stays_empty(monkeypatch):
    conversation = _conversation('rag', 'doc_' + 'd' * 32)
    monkeypatch.setattr(service.store, 'get', lambda owner, identifier: conversation)
    monkeypatch.setattr(service.store, 'recent_turns', lambda identifier, limit: [])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: None)
    scopes = []
    monkeypatch.setattr(service, '_run', lambda mode, question, document_id, formula_id=None, document_ids=None, original_question=None:
                        scopes.append(document_ids) or {'success': True, 'answer': 'ok',
                            'document_ids': document_ids, 'sources': []})

    service.ask('owner', 'a' * 32, '旧客户端请求')
    service.ask('owner', 'a' * 32, '显式不选择文档', document_ids=[])

    assert scopes == [['doc_' + 'd' * 32], []]
