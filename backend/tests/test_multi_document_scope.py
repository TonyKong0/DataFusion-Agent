import pytest

from app.core.errors import AppError
from app.document.multi_doc import retriever


def _document(document_id):
    return {'document_id': document_id, 'filename': f'{document_id}.pdf', 'status': 'indexed'}


def test_multi_document_retrieval_accepts_ten_distinct_sources(monkeypatch):
    document_ids = [f'doc_{index:02}' for index in range(10)]
    monkeypatch.setattr(retriever, 'load_document', _document)
    monkeypatch.setattr(retriever, 'ready', lambda _: True)
    monkeypatch.setattr(retriever, 'retrieve_hits', lambda document, _question, _top_k: [{
        'chunk_id': document['document_id'], 'text': document['document_id'], 'score': 1.0,
    }])

    result = retriever.retrieve_many(document_ids, '综合查找', top_k=10)

    assert len(result) == 10
    assert {item['document_id'] for item in result} == set(document_ids)


def test_multi_document_retrieval_rejects_eleven_distinct_sources():
    document_ids = [f'doc_{index:02}' for index in range(11)]

    with pytest.raises(AppError) as error:
        retriever.retrieve_many(document_ids, '超出上限', top_k=10)

    assert error.value.code == 'DOCUMENT_SELECTION_REQUIRED'
    assert error.value.status_code == 422


def test_explicit_work_title_limits_author_evidence_to_matching_document(monkeypatch):
    filenames = {'doc_a': '醉翁亭记 (2).pdf', 'doc_b': '1岳阳楼记.pdf'}
    monkeypatch.setattr(retriever, 'load_document', lambda identifier: {
        'document_id': identifier, 'filename': filenames[identifier], 'status': 'indexed',
        'content': [{'chunk_id': identifier, 'page': 1, 'text': filenames[identifier]}]})
    monkeypatch.setattr(retriever, 'ready', lambda _: True)
    calls = []
    def hits(document, question, top_k):
        calls.append(document['document_id'])
        return [{**document['content'][0], 'score': .9}]
    monkeypatch.setattr(retriever, 'retrieve_hits', hits)
    monkeypatch.setattr(retriever, 'retrieve_original_hits', lambda *args: (_ for _ in ()).throw(
        AssertionError('author questions must use targeted retrieval')))

    result = retriever.retrieve_many(['doc_a', 'doc_b'], '岳阳楼记的作者是谁？', top_k=5)

    assert calls == ['doc_b']
    assert [item['document_id'] for item in result] == ['doc_b']


def test_cover_title_identifies_document_when_uploaded_filename_is_generic():
    target = {'filename': 'lesson-02.pdf', 'content': [
        {'page': 1, 'text': '岳阳楼记\n范仲淹'}]}
    other = {'filename': 'lesson-01.pdf', 'content': [
        {'page': 1, 'text': '醉翁亭记\n欧阳修'}]}

    assert retriever._title_matches_question(target, '岳阳楼记的作者是谁？')
    assert not retriever._title_matches_question(other, '岳阳楼记的作者是谁？')
