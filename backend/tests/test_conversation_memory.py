import json

import numpy as np
from types import SimpleNamespace

from app.conversation import memory


def test_episodic_memory_recalls_relevant_older_turns_and_keeps_material_scope(monkeypatch):
    turns = [
        {'id': 1, 'question': '旧文档问题', 'resolved_question': '解释销售表',
         'answer': '旧材料答案', 'result': {'document_ids': ['doc-old']}},
        {'id': 2, 'question': '匹配的问题', 'resolved_question': '说明客户数量',
         'answer': '旧轮中的客户数量结果', 'result': {'document_ids': ['doc-current']}},
        {'id': 3, 'question': '最近一轮', 'resolved_question': '最近一轮',
         'answer': 'recent', 'result': {'document_ids': ['doc-current']}},
    ]

    def fake_embed(texts):
        return np.asarray([[1.0, 0.0] if text == '现在多少客户' or '匹配的问题' in text
                           else [0.0, 1.0] for text in texts], dtype=np.float32)

    monkeypatch.setattr(memory, 'embed', fake_embed)

    recalled = memory.retrieve_episodic(
        turns, '现在多少客户', mode='rag', document_ids=['doc-current'],
        recent_turn_ids={3}, limit=3)

    assert [turn['turn_id'] for turn in recalled] == [2]
    assert recalled[0]['answer'] == '旧轮中的客户数量结果'


def test_episodic_memory_for_agent_excludes_other_material_scope(monkeypatch):
    turns = [
        {'id': 1, 'question': '数据库问句', 'resolved_question': '客户数', 'answer': '59',
         'result': {'route': {'route': 'DATABASE_ONLY'}}},
        {'id': 2, 'question': '旧材料问句', 'resolved_question': '旧材料事实', 'answer': '旧内容',
         'result': {'document_ids': ['doc-old'], 'route': {'route': 'DOCUMENT_ONLY'}}},
    ]
    monkeypatch.setattr(memory, 'embed', lambda texts: np.asarray(
        [[1.0, 0.0] if index == 0 else [0.8, 0.2] for index, _ in enumerate(texts)],
        dtype=np.float32))

    recalled = memory.retrieve_episodic(
        turns, '数据库客户数', mode='agent', document_ids=['doc-current'],
        recent_turn_ids=set(), limit=3)

    assert [turn['turn_id'] for turn in recalled] == [1]


def test_context_compaction_trims_old_memory_before_current_question(monkeypatch):
    payload = {
        'current_question': '保留当前问题',
        'summary': '旧摘要' * 100,
        'recent': [{'question': '旧追问' * 100, 'answer': '旧答案' * 100}],
        'episodic_memory': [{'question': '更旧的问题' * 100, 'answer': '更旧答案' * 100}],
    }
    system = '固定系统指令'

    reduced = memory.fit_rewrite_context(payload, system, max_tokens=60)

    assert reduced['current_question'] == '保留当前问题'
    sent_prompt_tokens = memory.estimate_tokens(system + json.dumps(reduced, ensure_ascii=False))
    assert sent_prompt_tokens <= 60


def test_conversation_query_rewrites_with_recalled_older_episode(monkeypatch):
    from app.conversation import service

    older = {'id': 1, 'question': '之前的音乐类型筛选', 'resolved_question': '音乐类型名称以 R 开头',
             'answer': '四种', 'result': {}}
    recent = {'id': 2, 'question': '列出音乐类型', 'resolved_question': '列出音乐类型',
              'answer': '25 种', 'result': {}}
    conversation = {'id': 'a' * 32, 'mode': 'database', 'document_id': None,
                    'summary': '', 'state': {}}
    prompts = []
    saved = []
    monkeypatch.setattr(service, 'get_settings', lambda: SimpleNamespace(
        max_context_tokens=12000, conversation_summary_chars=800,
        conversation_recent_turns=3, max_llm_calls=8, llm_timeout=45))
    monkeypatch.setattr(service.store, 'get', lambda *_: conversation)
    monkeypatch.setattr(service.store, 'recent_turns', lambda *_: [recent])
    monkeypatch.setattr(service.store, 'memory_turns', lambda *_: [older, recent])
    monkeypatch.setattr(memory, 'retrieve_episodic', lambda *_args, **_kwargs: [{
        'turn_id': 1, 'question': older['question'], 'resolved_question': older['resolved_question'],
        'answer': older['answer'], 'source_route': None, 'document_ids': [],
    }])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: saved.append(args))
    monkeypatch.setattr(service, 'chat_json', lambda _system, user: (
        prompts.append(user) or {'action': 'query', 'standalone_question': '再次筛选 R 开头音乐类型'}))
    monkeypatch.setattr(service, '_run', lambda *_args, **_kwargs: {'success': True, 'answer': '核验结果'})

    result = service.ask('owner', 'a' * 32, '只看刚才那些')

    assert '之前的音乐类型筛选' in prompts[0]
    assert result['resolved_question'] == '再次筛选 R 开头音乐类型'
    assert saved[0][-1].get('memory_summary') is None


def test_context_pressure_consolidates_once_and_persists_scoped_summary(monkeypatch):
    from app.conversation import service

    turns = [{'id': index, 'question': f'问题{index}', 'resolved_question': f'独立问题{index}',
              'answer': '音乐类型的历史解释' * 120, 'result': {}}
             for index in range(1, 5)]
    conversation = {'id': 'b' * 32, 'mode': 'database', 'document_id': None,
                    'summary': '', 'state': {}}
    calls = []
    saved = []
    settings = SimpleNamespace(max_context_tokens=1000, conversation_summary_chars=800,
        conversation_recent_turns=3, max_llm_calls=8, llm_timeout=45)
    monkeypatch.setattr(service, 'get_settings', lambda: settings)
    monkeypatch.setattr(service.store, 'get', lambda *_: conversation)
    monkeypatch.setattr(service.store, 'recent_turns', lambda *_: turns[-3:])
    monkeypatch.setattr(service.store, 'memory_turns', lambda *_: turns)
    monkeypatch.setattr(memory, 'retrieve_episodic', lambda *_args, **_kwargs: [{
        'turn_id': 1, 'question': turns[0]['question'], 'resolved_question': turns[0]['resolved_question'],
        'answer': turns[0]['answer'], 'source_route': None, 'document_ids': [],
    }])
    monkeypatch.setattr(service.store, 'append_turn', lambda *args: saved.append(args))

    def fake_chat(system, user):
        calls.append(system)
        if system == service.MEMORY_SUMMARY_SYSTEM:
            return {'summary': '保留用户正在追问音乐类型筛选。'}
        return {'action': 'query', 'standalone_question': '查询当前音乐类型筛选'}

    monkeypatch.setattr(service, 'chat_json', fake_chat)
    monkeypatch.setattr(service, '_run', lambda *_args, **_kwargs: {'success': True, 'answer': '结果'})

    service.ask('owner', 'b' * 32, '这个筛选结果呢？', context_limit_tokens=1000)

    assert calls.count(service.MEMORY_SUMMARY_SYSTEM) == 1
    assert saved[0][-1]['memory_summaries']['database:[]'] == '保留用户正在追问音乐类型筛选。'
    assert saved[0][-1]['memory_summary_through']['database:[]'] == 1


def test_cross_source_working_memory_excludes_turns_from_other_materials(monkeypatch):
    import json
    from app.conversation import service

    wrong_scope = {'id': 1, 'question': '旧材料的问题', 'resolved_question': '旧材料的内容',
                   'answer': '不能带入的旧材料事实',
                   'result': {'document_ids': ['doc-old']}}
    current_scope = {'id': 2, 'question': '当前材料的问题', 'resolved_question': '当前材料的内容',
                     'answer': '当前范围相关的追问背景',
                     'result': {'document_ids': ['doc-current']}}
    conversation = {'id': 'c' * 32, 'mode': 'agent', 'document_id': 'doc-current',
                    'summary': '', 'state': {'agent_document_ids': ['doc-current'],
                        'pending_context_question': '旧材料的待澄清问题',
                        'pending_context_document_ids': ['doc-old']}}
    prompts = []
    monkeypatch.setattr(service, 'get_settings', lambda: SimpleNamespace(
        max_context_tokens=12000, conversation_summary_chars=800,
        conversation_recent_turns=3, max_llm_calls=8, llm_timeout=45))
    monkeypatch.setattr(service.store, 'get', lambda *_: conversation)
    monkeypatch.setattr(service.store, 'recent_turns', lambda *_: [wrong_scope, current_scope])
    monkeypatch.setattr(service.store, 'memory_turns', lambda *_: [wrong_scope, current_scope])
    monkeypatch.setattr(memory, 'retrieve_episodic', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(service.store, 'append_turn', lambda *_args: None)
    monkeypatch.setattr(service, 'chat_json', lambda _system, user: (
        prompts.append(json.loads(user)) or
        {'action': 'query', 'standalone_question': '核对当前材料内容'}))
    monkeypatch.setattr(service, '_run', lambda *_args, **_kwargs: {'success': True, 'answer': '已核对'})

    service.ask('owner', 'c' * 32, '继续刚才的问题')

    assert '不能带入的旧材料事实' not in json.dumps(prompts[0], ensure_ascii=False)
    assert '旧材料的待澄清问题' not in json.dumps(prompts[0], ensure_ascii=False)
    assert '当前范围相关的追问背景' in json.dumps(prompts[0], ensure_ascii=False)

