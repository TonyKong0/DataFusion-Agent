import pytest
from app.core.errors import AppError
from app.services import rag_service as service

DOCUMENT = {'status': 'indexed'}
HIT = {'chunk_id': 'chunk_1', 'document_id': 'doc_a', 'filename': 'demo.pdf', 'page': 3,
       'text': '单表 SELECT 最多 100 行。', 'score': .82}


@pytest.fixture(autouse=True)
def fixtures(monkeypatch):
    monkeypatch.setattr(service, 'load_document', lambda _: DOCUMENT)
    monkeypatch.setattr(service, 'ready', lambda _: True)
    monkeypatch.setattr(service, 'search', lambda *args: [HIT])


def test_rag_source_is_retrieved(monkeypatch):
    monkeypatch.setattr(service, 'chat_json', lambda *args: {'answer': '最多 100 行。', 'used_chunk_ids': ['chunk_1']})
    result = service.query('doc_a', '最多几行？', 5)
    assert result['sources'][0]['page'] == 3 and result['sources'][0]['score'] == .82
    assert [step['step'] for step in result['trace']] == [
        'document_load', 'vector_search', 'context_build', 'llm_generate', 'citation_validate']


def test_unknown_answer_has_no_source(monkeypatch):
    monkeypatch.setattr(service, 'chat_json', lambda *args: {'answer': '随便回答', 'used_chunk_ids': []})
    result = service.query('doc_a', '电话号码是多少？', 5)
    assert result['answer'] == service.UNKNOWN and result['sources'] == []


def test_rag_rechecks_evidence_once_before_declaring_unknown(monkeypatch):
    outputs = iter([
        {'answer': '根据当前文档无法确定。', 'used_chunk_ids': []},
        {'answer': '资料明确说最多 100 行。', 'used_chunk_ids': ['chunk_1']},
    ])
    prompts = []
    def model(system, payload):
        prompts.append(system)
        return next(outputs)
    monkeypatch.setattr(service, 'chat_json', model)

    result = service.query('doc_a', '最多几行？', 5)

    assert result['answer'] == '资料明确说最多 100 行。'
    assert [source['chunk_id'] for source in result['sources']] == ['chunk_1']
    assert len(prompts) == 2


def test_rag_quotes_matching_source_for_explicit_excerpt_request(monkeypatch):
    source = {**HIT, 'text': '欧阳修是北宋文学家，江西吉水人。'}
    monkeypatch.setattr(service, 'search', lambda *args: [source])
    monkeypatch.setattr(service, 'chat_json', lambda *args: {
        'answer': '根据当前文档无法确定。', 'used_chunk_ids': []})

    result = service.query('doc_a', '请摘录有关欧阳修的原文', 5)

    assert '江西吉水人' in result['answer']
    assert [item['chunk_id'] for item in result['sources']] == ['chunk_1']


def test_related_name_is_not_evidence_for_missing_requested_fact(monkeypatch):
    source = {**HIT, 'text': '文档提到滕子京重修岳阳楼，但没有联系方式。'}
    monkeypatch.setattr(service, 'search', lambda *args: [source])
    monkeypatch.setattr(service, 'chat_json', lambda *args: {
        'answer': '根据当前文档无法确定。', 'used_chunk_ids': []})

    result = service.query('doc_a', '滕子京的手机号是多少？', 5)

    assert result['answer'] == service.UNKNOWN
    assert result['sources'] == []


def test_excerpt_request_requires_whole_requested_topic(monkeypatch):
    source = {**HIT, 'text': '文档介绍了滕子京重修岳阳楼，没有电话号码。'}
    monkeypatch.setattr(service, 'search', lambda *args: [source])
    monkeypatch.setattr(service, 'chat_json', lambda *args: {
        'answer': '根据当前文档无法确定。', 'used_chunk_ids': []})

    result = service.query('doc_a', '请摘录有关滕子京手机号的原文', 5)

    assert result['answer'] == service.UNKNOWN
    assert result['sources'] == []


def test_forged_source_rejected(monkeypatch):
    monkeypatch.setattr(service, 'chat_json', lambda *args: {'answer': '伪造', 'used_chunk_ids': ['bad']})
    with pytest.raises(AppError) as error:
        service.query('doc_a', '问题', 5)
    assert error.value.code == 'INVALID_SOURCE'


@pytest.mark.parametrize('question', ['这份文档主要讲什么？', '这个文档讲了啥？',
                                      '这篇讲的啥？', '这篇讲的是啥？',
                                      '这篇文章主要表达什么思想？'])
def test_overview_includes_opening_content(monkeypatch, question):
    chunks = [{'chunk_id': f'chunk_{page}', 'page': page,
               'text': f'第{page}页正文' * 20, 'score': .4}
              for page in (1, 4, 32)]
    heading = {'chunk_id': 'chunk_41', 'page': 41, 'text': '总结提升', 'score': .9}
    document = {'content': chunks + [heading]}
    monkeypatch.setattr(service, 'search', lambda *_: [heading, chunks[2], chunks[1], chunks[0]])
    hits = service.retrieve_hits(document, question, 3)
    assert {hit['page'] for hit in hits} == {1, 4, 32}
    assert hits[0]['page'] != 41


def test_overview_prefers_substantive_body_to_cover_slide(monkeypatch):
    cover = {'chunk_id': 'cover', 'page': 1,
             'text': '教学课件 第一PPT模板网 WWW.EXAMPLE.COM ' * 5, 'score': .8}
    body = {'chunk_id': 'body', 'page': 22,
            'text': '文章主题是关心社会现实，并通过人物经历揭示制度带来的伤害。' * 3,
            'score': .65}
    document = {'content': [cover, body]}
    monkeypatch.setattr(service, 'search', lambda *args: [cover, body])

    hits = service.retrieve_hits(document, '这篇文章讲什么？', 2)

    assert hits[0]['chunk_id'] == 'body'


def test_original_request_prefers_source_prose_to_translation_and_lesson(monkeypatch):
    original = {'chunk_id': 'original', 'page': 7,
                'text': '庆历四年春，滕子京谪守巴陵郡。越明年，政通人和，百废具兴。' * 3,
                'score': .54}
    translation = {'chunk_id': 'translation', 'page': 8,
                   'text': '译文：庆历四年的春天，滕子京被贬官到岳州做知州。' * 3,
                   'score': .67}
    lesson = {'chunk_id': 'lesson', 'page': 18,
              'text': '这篇文章的主要内容是什么？作者在文中如何表现思想？' * 3,
              'score': .66}
    monkeypatch.setattr(service, 'search', lambda *_: [translation, lesson, original])

    hits = service.retrieve_original_hits({'content': [original, translation, lesson]},
                                           '岳阳楼记的原文是什么', 2)

    assert hits[0]['chunk_id'] == 'original'


def test_original_request_with_typo_cites_selected_document_excerpt(monkeypatch):
    from app.document.multi_doc import retriever

    original = {'chunk_id': 'original', 'page': 7,
                'text': '庆历四年春，滕子京谪守巴陵郡。\n越明年，政通人和，百废具兴。\n'
                        '乃重修岳阳楼，增其旧制，刻唐贤今人诗赋于其上。\n同“俱”，全、皆。',
                'score': .7}
    docs = {
        'a': {'document_id': 'a', 'filename': '甲篇.pdf', 'status': 'indexed', 'content': []},
        'b': {'document_id': 'b', 'filename': '岳阳楼记.pdf', 'status': 'indexed',
              'content': [original]},
    }
    monkeypatch.setattr(service, 'load_document', lambda identifier: docs[identifier])
    monkeypatch.setattr(service, 'ready', lambda _: True)
    monkeypatch.setattr(service, 'search', lambda doc, *_: [original] if doc['document_id'] == 'b' else [])
    monkeypatch.setattr(retriever, 'query', lambda *_: (_ for _ in ()).throw(
        AssertionError('clear visible original should be answered before model search')))

    assert service.normalize_document_question('岳阳楼鸡的原文是什么', list(docs.values())) == '岳阳楼记的原文是什么'
    assert service.original_excerpt_answer([docs['b']], '岳阳楼记的原文是什么')

    result = service.query_documents(['a', 'b'], '岳阳楼鸡的原文是什么', 5)

    assert '庆历四年春' in result['answer']
    assert '节选' in result['answer']
    assert '同“俱”' not in result['answer']
    assert [item['document_id'] for item in result['sources']] == ['b']


def test_original_request_rejects_intro_and_verifies_mixed_page_quote(monkeypatch):
    intro = {'chunk_id': 'intro', 'page': 4,
             'text': '醉翁亭坐落于滁州，与其他名亭齐名。欧阳修写的《醉翁亭记》讲的就是此亭。' * 2,
             'score': .8}
    mixed = {'chunk_id': 'mixed', 'page': 13,
             'text': '课文大意\n环绕滁州城的都是山。\n'
                     '环滁皆山也。其西南诸峰，林壑尤美，望之蔚然而深秀者，琅玡也。\n'
                     '语气词表判断。', 'score': .6}
    document = {'document_id': 'z', 'filename': '醉翁亭记.pdf', 'content': [intro, mixed]}
    monkeypatch.setattr(service, 'search', lambda *_: [intro, mixed])
    monkeypatch.setattr(service, 'chat_json', lambda *_: {
        'chunk_id': 'mixed',
        'excerpt': '环滁皆山也。其西南诸峰，林壑尤美，望之蔚然而深秀者，琅玡也。'})

    result = service.original_excerpt_answer([document], '醉翁亭记的原文是什么')

    assert '环滁皆山也' in result['answer']
    assert '醉翁亭坐落' not in result['answer']
    assert result['sources'][0]['page'] == 13


def test_original_request_rejects_model_passage_not_in_source(monkeypatch):
    intro = {'chunk_id': 'intro', 'page': 4,
             'text': '醉翁亭坐落于滁州，与其他名亭齐名。欧阳修写的《醉翁亭记》讲的就是此亭。' * 2,
             'score': .8}
    document = {'document_id': 'z', 'filename': '醉翁亭记.pdf', 'content': [intro]}
    monkeypatch.setattr(service, 'search', lambda *_: [intro])
    monkeypatch.setattr(service, 'chat_json', lambda *_: {
        'chunk_id': 'intro', 'excerpt': '环滁皆山也。其西南诸峰，林壑尤美，望之蔚然而深秀者，琅玡也。'})

    assert service.original_excerpt_answer([document], '醉翁亭记的原文是什么') is None


def test_original_request_keeps_short_verse_without_following_lesson(monkeypatch):
    intro = {'chunk_id': 'intro', 'page': 2, 'text': '反复朗读诗歌，体会诗歌的情感。'}
    translation = {'chunk_id': 'translation', 'page': 6,
                   'text': '行路难\n明大意\n拔剑环顾四周，心里一片茫然。'
                           '这段译文说明诗人失意的心情。', 'score': .9}
    lesson = {'chunk_id': 'poem', 'page': 8,
              'text': '行路难\n停杯投箸不能食，拔剑四顾心茫然。'
                      '停、投、拔、顾四个连动，形象地把诗人的苦闷表现出来。',
              'score': .7}
    document = {'document_id': 'poem', 'filename': '行路难课件.pdf',
                'content': [intro, translation, lesson]}
    monkeypatch.setattr(service, 'search', lambda *_: [translation, lesson])
    monkeypatch.setattr(service, 'chat_json', lambda *_: (_ for _ in ()).throw(
        AssertionError('a quoted complete couplet should not require model selection')))

    result = service.original_excerpt_answer([document], '行路难的原文是什么')

    assert '停杯投箸不能食' in result['answer']
    assert '形象地' not in result['answer']


def test_prose_document_does_not_treat_seven_character_intro_as_poetry():
    intro = {'chunk_id': 'intro', 'page': 4,
             'text': '又屡次复建，终不为人所忘。醉翁亭是当地古迹。'}
    document = {'filename': '醉翁亭记.pdf', 'content': [intro]}

    assert service._poetry_excerpt(document, [intro]) == (None, '')


@pytest.mark.parametrize('question', ['这个文章是谁写的？', '作者是谁？'])
def test_author_question_includes_opening_evidence(monkeypatch, question):
    chunks = [{'chunk_id': f'chunk_{page}', 'page': page,
               'text': text, 'score': .4}
              for page, text in [(1, '竖排标题'), (3, '作者生平' * 30),
                                 (4, '受朋友邀请写下这篇文章' * 20),
                                 (32, '文章表达了作者的思想' * 20)]]
    document = {'content': chunks}
    ranked = [chunks[3], chunks[1], chunks[2], chunks[0]]
    monkeypatch.setattr(service, 'search', lambda *_: ranked)
    hits = service.retrieve_hits(document, question, 3)
    assert [hit['page'] for hit in hits] == [3, 4, 32]


def test_author_question_keeps_short_cover_with_title_and_author(monkeypatch):
    cover = {'chunk_id': 'cover', 'page': 1, 'text': '岳阳楼记\n范仲淹'}
    body = {'chunk_id': 'body', 'page': 3, 'text': '作者生平' * 30}
    document = {'content': [cover, body]}
    monkeypatch.setattr(service, 'search', lambda *args: [{**body, 'score': .8},
                                                         {**cover, 'score': .5}])

    hits = service.retrieve_hits(document, '岳阳楼记的作者是谁？', 2)

    assert [hit['chunk_id'] for hit in hits] == ['cover', 'body']


def test_multi_document_author_question_uses_each_selected_document_before_vector_search(monkeypatch):
    docs = {identifier: {'document_id': identifier, 'filename': filename, 'status': 'indexed',
                         'content': [{'chunk_id': identifier + '_cover', 'page': 1,
                                      'text': f'{title}\n{author}'}]}
            for identifier, filename, title, author in [
                ('a', '甲篇.pdf', '甲篇', '张三'),
                ('b', '乙篇.pdf', '乙篇', '李四'),
                ('c', '丙篇.pdf', '丙篇', '王五'),
                ('d', '丁篇.pdf', '丁篇', '赵六')]}
    monkeypatch.setattr(service, 'load_document', lambda identifier: docs[identifier])
    monkeypatch.setattr(service, 'ready', lambda *_: True)
    monkeypatch.setattr(service, 'search', lambda *_: (_ for _ in ()).throw(
        AssertionError('clear author evidence must be checked per document')))

    result = service.query_documents(list(docs), '这四篇文章的作者是谁？', 5)

    assert [source['document_id'] for source in result['sources']] == list(docs)
    assert all(name in result['answer'] for name in ('张三', '李四', '王五', '赵六'))


def test_unrelated_fact_keeps_vector_ranking(monkeypatch):
    ranked = [{'chunk_id': 'a', 'page': 20, 'text': '电话号码', 'score': .9}]
    monkeypatch.setattr(service, 'search', lambda *args: ranked[:args[2]])
    assert service.retrieve_hits({'content': []}, '电话号码是多少？', 1) == ranked


def test_explicit_empty_document_scope_never_falls_back_to_the_session_document():
    with pytest.raises(AppError) as error:
        service.query_documents([], '总结文档', 5)

    assert error.value.code == 'DOCUMENT_SELECTION_REQUIRED'
    assert error.value.status_code == 422


def test_document_scope_deduplicates_ids_and_records_the_exact_single_source(monkeypatch):
    monkeypatch.setattr(service, 'load_document', lambda identifier: {
        'document_id': identifier, 'filename': 'policy.pdf', 'status': 'indexed'})
    monkeypatch.setattr(service, 'chat_json', lambda *_: {
        'answer': '只读查询最多返回 100 行。', 'used_chunk_ids': ['chunk_1']})

    result = service.query_documents(['doc_a', 'doc_a'], '查询限制是什么？', 5)

    assert result['document_ids'] == ['doc_a']
    assert result['document_names'] == [{'document_id': 'doc_a', 'filename': 'policy.pdf'}]
    assert result['sources'][0]['document_id'] == 'doc_a'


def test_multiple_document_scope_uses_existing_retriever_and_records_names(monkeypatch):
    from app.document.multi_doc import retriever
    calls = []
    documents = {
        'doc_a': {'document_id': 'doc_a', 'filename': 'policy_v1.pdf', 'status': 'indexed'},
        'doc_b': {'document_id': 'doc_b', 'filename': 'policy_v2.pdf', 'status': 'indexed'},
    }
    monkeypatch.setattr(service, 'load_document', lambda identifier: documents[identifier])
    monkeypatch.setattr(retriever, 'query', lambda ids, question, top_k: calls.append(
        (ids, question, top_k)) or {'success': True, 'answer': '两份资料已比较。', 'sources': [
            {'document_id': 'doc_b', 'filename': 'policy_v2.pdf', 'chunk_id': 'new', 'page': 2}],
            'documents': ids})

    result = service.query_documents(['doc_a', 'doc_b', 'doc_a'], '规则改了什么？', 5)

    assert calls == [(['doc_a', 'doc_b'], '规则改了什么？', 5)]
    assert result['document_ids'] == ['doc_a', 'doc_b']
    assert result['document_names'] == [
        {'document_id': 'doc_a', 'filename': 'policy_v1.pdf'},
        {'document_id': 'doc_b', 'filename': 'policy_v2.pdf'},
    ]
    assert result['sources'][0]['document_id'] == 'doc_b'


def test_document_being_reindexed_is_not_accepted_for_a_new_turn(monkeypatch):
    monkeypatch.setattr(service, 'load_document', lambda identifier: {
        'document_id': identifier, 'filename': 'report.pdf', 'status': 'indexed',
        'index_status': {'status': 'embedding'}})

    with pytest.raises(AppError) as error:
        service.query_documents(['doc_a'], '总结', 5)

    assert error.value.code == 'INDEX_NOT_READY'
    assert error.value.status_code == 409


def test_document_scope_accepts_ten_and_rejects_eleven(monkeypatch):
    from app.document.multi_doc import retriever

    ids = [f'doc_{index:02}' for index in range(10)]
    monkeypatch.setattr(service, 'load_document', lambda identifier: {
        'document_id': identifier, 'filename': f'{identifier}.pdf', 'status': 'indexed'})
    monkeypatch.setattr(service, 'ready', lambda _: True)
    monkeypatch.setattr(retriever, 'query', lambda selected, question, top_k: {
        'success': True, 'answer': '已检索十份资料。', 'sources': [], 'documents': selected})

    result = service.query_documents(ids, '联合检索', 5)

    assert result['document_ids'] == ids
    assert result['document_names'][-1]['document_id'] == ids[-1]
    with pytest.raises(AppError) as error:
        service.query_documents(ids + ['doc_10'], '超出上限', 5)
    assert error.value.code == 'DOCUMENT_SELECTION_LIMIT'
    assert error.value.status_code == 422
