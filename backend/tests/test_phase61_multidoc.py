import json

import pytest

from app.conversation import service as conversation_service
from app.document.multi_doc import retriever
from app.services import rag_service


@pytest.fixture(autouse=True)
def default_document_loader(monkeypatch):
    monkeypatch.setattr(retriever, 'load_document', lambda identifier: {
        'document_id': identifier, 'filename': f'{identifier}.pdf',
        'status': 'indexed', 'content': []})


def test_three_document_ranking_dedup_and_provenance(monkeypatch):
    docs = {key: {'document_id': key, 'filename': f'report_{key}.pdf', 'status': 'indexed'}
            for key in ('doc_a', 'doc_b', 'doc_c')}
    monkeypatch.setattr(retriever, 'load_document', lambda key: docs[key])
    monkeypatch.setattr(retriever, 'ready', lambda key: True)
    monkeypatch.setattr(retriever, 'retrieve_hits', lambda doc, question, limit: [
        {'chunk_id': doc['document_id'] + '_1', 'page': 1, 'text': 'shared' if doc['document_id'] != 'doc_c' else 'unique',
         'score': {'doc_a': .7, 'doc_b': .9, 'doc_c': .8}[doc['document_id']]}])
    hits = retriever.retrieve_many(['doc_a', 'doc_b', 'doc_c'], '架构', 5)
    assert len(hits) == 3
    assert hits[0]['document_id'] == 'doc_b'
    assert {item['document_id'] for item in hits} == set(docs)
    assert all(not item['duplicate_document_ids'] for item in hits)
    assert [item['cross_document_rank'] for item in hits] == [1, 2, 3]


def test_multi_document_answer_accepts_only_retrieved_citations(monkeypatch):
    hits = [{'document_id': 'doc_a', 'chunk_id': 'a1', 'filename': 'a.pdf', 'page': 2,
             'text': '系统使用 Router。', 'score': .9, 'heading_path': ['架构']}]
    monkeypatch.setattr(retriever, 'retrieve_many', lambda ids, question, top_k: hits)
    monkeypatch.setattr(retriever, 'chat_json', lambda system, prompt: {
        'answer': '系统使用 Router。', 'used_chunk_ids': ['doc_a:a1']})
    result = retriever.query(['doc_a', 'doc_b'], '系统架构？')
    assert result['sources'][0]['document_id'] == 'doc_a'
    assert result['sources'][0]['page'] == 2


def test_multi_document_answer_resolves_unique_short_chunk_id(monkeypatch):
    hits = [{'document_id': 'doc_a', 'chunk_id': 'doc_a_chunk_1',
             'filename': 'a.pdf', 'page': 2, 'text': '材料中的结论。', 'score': .9}]
    monkeypatch.setattr(retriever, 'retrieve_many', lambda *_: hits)
    monkeypatch.setattr(retriever, 'chat_json', lambda *_: {
        'answer': '材料中的结论。', 'used_chunk_ids': ['doc_a_chunk_1']})

    result = retriever.query(['doc_a', 'doc_b'], '材料中的结论是什么？')

    assert result['answer'] == '材料中的结论。'
    assert result['sources'][0]['chunk_id'] == 'doc_a_chunk_1'


def test_overview_draws_opening_evidence_from_each_selected_document(monkeypatch):
    docs = {key: {'document_id': key, 'filename': f'{key}.pdf', 'status': 'indexed'}
            for key in ('doc_a', 'doc_b')}
    monkeypatch.setattr(retriever, 'load_document', lambda key: docs[key])
    monkeypatch.setattr(retriever, 'ready', lambda key: True)
    monkeypatch.setattr(retriever, 'retrieve_hits', lambda doc, question, limit: [
        {'chunk_id': f"{doc['document_id']}_{index}", 'page': index,
         'text': f"{doc['document_id']} opening {index}", 'score': .9 if doc['document_id'] == 'doc_a' else .2}
        for index in (1, 2, 3)])

    hits = retriever.retrieve_many(['doc_a', 'doc_b'], '这两篇讲的啥？', 4)

    assert [(hit['document_id'], hit['page']) for hit in hits] == [
        ('doc_a', 1), ('doc_b', 1), ('doc_a', 2), ('doc_b', 2)]


def test_three_selected_documents_each_contribute_to_overview(monkeypatch):
    docs = {key: {'document_id': key, 'filename': f'{key}.pdf', 'status': 'indexed'}
            for key in ('doc_a', 'doc_b', 'doc_c')}
    monkeypatch.setattr(retriever, 'load_document', lambda key: docs[key])
    monkeypatch.setattr(retriever, 'ready', lambda key: True)
    monkeypatch.setattr(retriever, 'retrieve_hits', lambda doc, question, limit: [{
        'chunk_id': doc['document_id'] + '_opening', 'page': 1,
        'text': doc['document_id'] + ' opening', 'score': .5}])

    hits = retriever.retrieve_many(list(docs), '这三篇分别讲什么？', 5)

    assert {hit['document_id'] for hit in hits} == set(docs)


def test_comparison_keeps_evidence_from_both_selected_documents(monkeypatch):
    docs = {key: {'document_id': key, 'filename': f'{key}.pdf', 'status': 'indexed'}
            for key in ('doc_a', 'doc_b')}
    monkeypatch.setattr(retriever, 'load_document', lambda key: docs[key])
    monkeypatch.setattr(retriever, 'ready', lambda _: True)
    monkeypatch.setattr(retriever, 'retrieve_hits', lambda doc, question, limit: [{
        'chunk_id': doc['document_id'] + '_theme', 'page': 4,
        'text': doc['document_id'] + ' 的主题与观点。',
        'score': .95 if doc['document_id'] == 'doc_a' else .25}])

    hits = retriever.retrieve_many(list(docs), '两份文档的主题有什么不同？', 2)

    assert {hit['document_id'] for hit in hits} == set(docs)


def test_comparison_rechecks_partial_citation_before_answering(monkeypatch):
    hits = [{'document_id': identifier, 'chunk_id': identifier + '_theme',
             'filename': identifier + '.pdf', 'page': 4,
             'text': identifier + ' 的观点。', 'score': .8}
            for identifier in ('doc_a', 'doc_b')]
    monkeypatch.setattr(retriever, 'retrieve_many', lambda *_: hits)
    calls = []

    def model(system, payload):
        calls.append(system)
        if len(calls) == 1:
            return {'answer': '只讲了甲。', 'used_chunk_ids': ['doc_a:doc_a_theme']}
        return {'answer': '甲和乙的观点不同。',
                'used_chunk_ids': ['doc_a:doc_a_theme', 'doc_b:doc_b_theme']}

    monkeypatch.setattr(retriever, 'chat_json', model)
    result = retriever.query(['doc_a', 'doc_b'], '比较两份文档的观点', 2)

    assert result['answer'] == '甲和乙的观点不同。'
    assert {source['document_id'] for source in result['sources']} == {'doc_a', 'doc_b'}
    assert len(calls) == 2


def test_comparison_refuses_partial_citation_after_retry(monkeypatch):
    hits = [{'document_id': identifier, 'chunk_id': identifier + '_theme',
             'filename': identifier + '.pdf', 'page': 4,
             'text': identifier + ' 的观点。', 'score': .8}
            for identifier in ('doc_a', 'doc_b')]
    monkeypatch.setattr(retriever, 'retrieve_many', lambda *_: hits)
    monkeypatch.setattr(retriever, 'chat_json', lambda *_: {
        'answer': '只有甲。', 'used_chunk_ids': ['doc_a:doc_a_theme']})

    result = retriever.query(['doc_a', 'doc_b'], '比较两份文档的观点', 2)

    assert result['partial'] is True
    assert '尚未覆盖全部指定材料' in result['answer']
    assert [source['document_id'] for source in result['sources']] == ['doc_a']


def test_original_question_with_title_searches_only_matching_document(monkeypatch):
    docs = {
        'doc_a': {'document_id': 'doc_a', 'filename': '甲篇.pdf', 'status': 'indexed'},
        'doc_b': {'document_id': 'doc_b', 'filename': '乙篇.pdf', 'status': 'indexed'},
    }
    monkeypatch.setattr(retriever, 'load_document', lambda key: docs[key])
    monkeypatch.setattr(retriever, 'ready', lambda _: True)
    calls = []

    def original(document, question, limit):
        calls.append(document['document_id'])
        return [{'chunk_id': document['document_id'] + '_original', 'page': 3,
                 'text': '这里是可见的原文正文。', 'score': .8}]

    monkeypatch.setattr(retriever, 'retrieve_original_hits', original)

    hits = retriever.retrieve_many(list(docs), '乙篇的原文是什么？', 5)

    assert calls == ['doc_b']
    assert [hit['document_id'] for hit in hits] == ['doc_b']


def test_overview_keeps_matching_opening_evidence_for_each_selected_material(monkeypatch):
    ids = ['doc_a', 'doc_b']
    docs = {key: {'document_id': key, 'filename': f'{key}.pdf', 'status': 'indexed'} for key in ids}
    monkeypatch.setattr(retriever, 'load_document', lambda key: docs[key])
    monkeypatch.setattr(retriever, 'ready', lambda _: True)
    monkeypatch.setattr(retriever, 'retrieve_hits', lambda document, *_: [{
        'chunk_id': document['document_id'] + '_opening', 'page': 1,
        'text': 'This shared opening paragraph appears in both materials.', 'score': 0.0,
    }])

    hits = retriever.retrieve_many(ids, '这两份材料讲什么？', top_k=2)

    assert {hit['document_id'] for hit in hits} == set(ids)


@pytest.mark.parametrize('opening_text', [
    '{id} introduces the subject, explains its background and purpose, and summarizes the main idea for readers who need a clear overview.',
    '材料 {id} 介绍主要内容。',
])
def test_generic_document_overview_returns_evidence_from_each_selected_material(monkeypatch, opening_text):
    ids = ['doc_a', 'doc_b']
    opening_hits = {
        key: [{'chunk_id': f'{key}_opening', 'page': 1,
               'text': opening_text.format(id=key),
               'score': .8}]
        for key in ids
    }
    docs = {key: {'document_id': key, 'filename': f'{key}.pdf', 'status': 'indexed',
                  'extension': 'pdf', 'content': opening_hits[key]} for key in ids}
    conversation = {'id': 'c' * 32, 'mode': 'rag', 'document_id': ids[0], 'state': {},
                    'scope_summary': ''}
    monkeypatch.setattr(conversation_service.store, 'get', lambda *_: conversation)
    monkeypatch.setattr(conversation_service.store, 'recent_document_turns', lambda *_: [])
    monkeypatch.setattr(conversation_service.store, 'append_turn', lambda *_: None)
    monkeypatch.setattr(rag_service, 'load_document', lambda key: docs[key])
    monkeypatch.setattr(rag_service, 'ready', lambda _: True)
    monkeypatch.setattr(retriever, 'load_document', lambda key: docs[key])
    monkeypatch.setattr(retriever, 'ready', lambda _: True)
    monkeypatch.setattr(rag_service, 'search', lambda *_: [])
    monkeypatch.setattr(retriever, 'retrieve_hits', lambda document, *_: document['content'])

    def answer_from_available_context(_system, prompt):
        context = json.loads(prompt)['context']
        if not context:
            return {'answer': '根据所选文档无法确定。', 'used_chunk_ids': []}
        return {'answer': '两份材料分别介绍各自的主要主题。',
                'used_chunk_ids': [item['chunk_id'] for item in context]}

    monkeypatch.setattr(retriever, 'chat_json', answer_from_available_context)

    result = conversation_service.ask('owner', conversation['id'], '这个文档讲什么？', document_ids=ids)

    assert result['answer'] == '两份材料分别介绍各自的主要主题。'
    assert {item['provenance']['document_id'] for item in result['evidence']} == set(ids)
