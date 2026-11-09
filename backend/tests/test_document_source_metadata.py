import json

from app.services import document_service


def test_legacy_pdf_with_original_file_remains_previewable(tmp_path, monkeypatch):
    monkeypatch.setattr(document_service, 'DOCUMENT_DIR', tmp_path)
    document_id = 'doc_' + 'a' * 32
    (tmp_path / f'{document_id}.json').write_text(json.dumps({
        'document_id': document_id, 'filename': 'legacy.pdf', 'status': 'indexed',
        'pages': 2, 'chunks': 1, 'content': [],
    }), encoding='utf-8')
    (tmp_path / f'{document_id}.pdf').write_bytes(b'%PDF-1.4')

    loaded = document_service.load_document(document_id)
    listed = document_service.list_documents()[0]

    assert loaded['extension'] == listed['extension'] == '.pdf'
    assert loaded['preview_available'] is True
    assert listed['preview_available'] is True


def test_legacy_pdf_without_original_file_is_not_previewable(tmp_path, monkeypatch):
    monkeypatch.setattr(document_service, 'DOCUMENT_DIR', tmp_path)
    document_id = 'doc_' + 'b' * 32
    (tmp_path / f'{document_id}.json').write_text(json.dumps({
        'document_id': document_id, 'filename': 'missing.pdf', 'status': 'indexed',
        'pages': 1, 'chunks': 1, 'content': [],
    }), encoding='utf-8')

    assert document_service.load_document(document_id)['preview_available'] is False
