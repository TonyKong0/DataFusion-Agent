from app.services import rag_service
from app.services.document_question import model_correction, normalize


def _document(identifier: str, filename: str, text: str) -> dict:
    return {'document_id': identifier, 'filename': filename, 'status': 'indexed',
            'content': [{'chunk_id': f'{identifier}_cover', 'page': 1, 'text': text}]}


def test_local_correction_handles_typo_and_selected_title_without_changing_other_intent():
    document = _document('a', '岳阳楼记.pdf', '岳阳楼记\n范仲淹')

    assert normalize('作者时谁', [document]) == '作者是谁'
    assert normalize('岳阳楼计的作者时谁', [document]) == '岳阳楼记的作者是谁'
    assert normalize('读者是谁', [document]) == '读者是谁'


def test_single_selected_document_answers_corrected_author_question(monkeypatch):
    document = _document('a', '岳阳楼记.pdf', '岳阳楼记\n范仲淹')
    monkeypatch.setattr(rag_service, 'load_document', lambda _: document)
    monkeypatch.setattr(rag_service, 'ready', lambda _: True)

    result = rag_service.query_documents(['a'], '作者时谁', 5)

    assert result['question'] == '作者时谁'
    assert result['interpreted_question'] == '作者是谁'
    assert result['answer'] == '《岳阳楼记》的作者是范仲淹。'
    assert result['sources'][0]['chunk_id'] == 'a_cover'


def test_multiple_selected_documents_keep_explicit_fuzzy_title_scope(monkeypatch):
    documents = {
        'a': _document('a', '醉翁亭记.pdf', '醉翁亭记\n欧阳修'),
        'b': _document('b', '岳阳楼记.pdf', '岳阳楼记\n范仲淹'),
    }
    monkeypatch.setattr(rag_service, 'load_document', lambda key: documents[key])
    monkeypatch.setattr(rag_service, 'ready', lambda _: True)

    result = rag_service.query_documents(['a', 'b'], '岳阳楼计的作者时谁', 5)

    assert result['answer'] == '《岳阳楼记》的作者是范仲淹。'
    assert [source['document_id'] for source in result['sources']] == ['b']


def test_model_correction_rejects_new_unselected_title_and_changed_number():
    documents = [_document('a', '岳阳楼记.pdf', '')]
    assert model_correction('第 3 页说什么', documents,
                            lambda *_: {'corrected_question': '第 4 页说什么'}) is None
    assert model_correction('《岳阳楼记》说什么', documents,
                            lambda *_: {'corrected_question': '《醉翁亭记》说什么'}) is None


def test_unanswered_typo_retries_retrieval_and_requires_cited_source(monkeypatch):
    document = _document('a', '人物介绍.pdf', '欧阳修是江西吉水人。')
    monkeypatch.setattr(rag_service, 'load_document', lambda _: document)
    monkeypatch.setattr(rag_service, 'ready', lambda _: True)
    hit = {**document['content'][0], 'score': .8}
    monkeypatch.setattr(rag_service, 'search', lambda _doc, question, _limit: [hit]
                        if '欧阳修' in question else [])
    monkeypatch.setattr(rag_service, 'generate_answer', lambda question, context, _chat: {
        'answer': '欧阳修是江西吉水人。' if context else rag_service.UNKNOWN,
        'used_chunk_ids': [hit['chunk_id']] if context else [],
    })
    monkeypatch.setattr(rag_service, 'chat_json', lambda *_: {
        'corrected_question': '欧阳修哪里人'})

    result = rag_service.query_documents(['a'], '欧阳秀哪里人', 5)

    assert result['answer'] == '欧阳修是江西吉水人。'
    assert result['interpreted_question'] == '欧阳修哪里人'
    assert [source['chunk_id'] for source in result['sources']] == ['a_cover']
