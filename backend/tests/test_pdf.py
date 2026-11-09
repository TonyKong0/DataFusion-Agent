import pytest
import pymupdf
from fastapi.testclient import TestClient
from app.main import app
from app.services.pdf_parser import parse_pdf
from app.services.text_splitter import split_pages
from app.core.errors import AppError
from app.services import document_service as service


def pdf_bytes(text='Test PDF text'):
    with pymupdf.open() as doc:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
        return doc.tobytes()


def test_parser_and_page_metadata():
    pages = parse_pdf(pdf_bytes())
    assert pages[0]['page'] == 1 and 'Test PDF text' in pages[0]['text']


def test_overlap_and_no_cross_page():
    chunks = split_pages([{'page': 1, 'text': 'x'*1500}, {'page': 2, 'text': 'y'*100}], 'doc_test', 'test.pdf')
    assert [c['page'] for c in chunks] == [1, 1, 1, 2]
    assert len(chunks[0]['text']) == 800
    assert chunks[0]['text'][-120:] == chunks[1]['text'][:120]


@pytest.mark.parametrize('content', [b'not a PDF', pdf_bytes('')])
def test_reject_invalid_pdf(content):
    with pytest.raises(AppError):
        parse_pdf(content)


def test_multiple_documents_keep_independent_chunks_and_delete_selected_only(tmp_path, monkeypatch):
    monkeypatch.setattr(service, 'DOCUMENT_DIR', tmp_path)
    first = service.import_document(pdf_bytes('First document'), '../../demo.pdf')
    second = service.import_document(pdf_bytes('Second document'), 'second.pdf')
    assert first['filename'] == 'demo.pdf' and first['chunks'] == 1
    assert second['filename'] == 'second.pdf' and second['chunks'] == 1
    assert first['document_id'] != second['document_id']
    assert {item['document_id'] for item in service.list_documents()} == {first['document_id'], second['document_id']}
    assert 'First document' in service.load_document(first['document_id'])['content'][0]['text']
    assert 'Second document' in service.load_document(second['document_id'])['content'][0]['text']
    service.delete_document(first['document_id'])
    assert service.list_documents()[0]['document_id'] == second['document_id']
    assert 'Second document' in service.load_document(second['document_id'])['content'][0]['text']
    service.delete_document(second['document_id'])
    assert service.list_documents() == []


def test_each_document_has_independent_vector_index(tmp_path, monkeypatch):
    import numpy as np
    from app.services import vector_store
    monkeypatch.setattr(service, 'DOCUMENT_DIR', tmp_path / 'documents')
    monkeypatch.setattr(vector_store, 'VECTOR_DIR', tmp_path / 'vectors')
    monkeypatch.setattr(vector_store, 'embed', lambda texts: np.ones((len(texts), 3), dtype='float32'))
    first = service.import_document(pdf_bytes('First document'), 'first.pdf')
    second = service.import_document(pdf_bytes('Second document'), 'second.pdf')
    for item in (first, second):
        vector_store.build_index(service.load_document(item['document_id']))
        assert vector_store.ready(item['document_id'])
    service.delete_document(first['document_id'])
    assert not vector_store.index_path(first['document_id']).exists()
    assert vector_store.ready(second['document_id'])
    hit = vector_store.search(service.load_document(second['document_id']), 'Second', 1)[0]
    assert hit['document_id'] == second['document_id']


def test_api_upload_multiple_and_delete_only_one(tmp_path, monkeypatch):
    import numpy as np
    from app.services import vector_store
    monkeypatch.setattr(service, 'DOCUMENT_DIR', tmp_path / 'documents')
    monkeypatch.setattr(vector_store, 'VECTOR_DIR', tmp_path / 'vectors')
    monkeypatch.setattr(vector_store, 'embed', lambda texts: np.ones((len(texts), 3), dtype='float32'))
    client = TestClient(app)
    first = client.post('/api/documents/upload', files={'file': ('first.pdf', pdf_bytes('First document'), 'application/pdf')})
    second = client.post('/api/documents/upload', files={'file': ('second.pdf', pdf_bytes('Second document'), 'application/pdf')})
    assert first.status_code == second.status_code == 200
    first_id, second_id = first.json()['document_id'], second.json()['document_id']
    assert first_id != second_id
    assert len(client.get('/api/documents').json()['documents']) == 2
    assert client.delete(f'/api/documents/{first_id}').status_code == 200
    assert [item['document_id'] for item in client.get('/api/documents').json()['documents']] == [second_id]
    assert client.get(f'/api/documents/{second_id}/file').status_code == 200


def test_original_pdf_opens_inline_and_missing_id_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(service, 'DOCUMENT_DIR', tmp_path)
    original = pdf_bytes()
    doc = service.import_document(original, 'sample.pdf')
    client = TestClient(app)
    response = client.get(f"/api/documents/{doc['document_id']}/file")
    assert response.status_code == 200
    assert response.content == original
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['content-disposition'].startswith('inline;')
    preview = client.get(f"/api/documents/{doc['document_id']}/pages/1/preview")
    assert preview.status_code == 200
    assert preview.headers['content-type'] == 'image/png'
    assert preview.content.startswith(b'\x89PNG\r\n\x1a\n')
    assert client.get(f"/api/documents/{doc['document_id']}/pages/2/preview").status_code == 404
    missing = client.get('/api/documents/doc_' + '0'*32 + '/file')
    assert missing.status_code == 404
