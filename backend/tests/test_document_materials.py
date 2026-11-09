import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.document.table.qa import query_table
from app.api import documents as document_api
from app.main import app
from app.services import document_service, vector_store
from app.core.errors import AppError
from app.services.document_parser import parse_document


def test_csv_material_is_persisted_indexed_and_table_evidence_is_queryable(tmp_path, monkeypatch):
    monkeypatch.setattr(document_service, 'DOCUMENT_DIR', tmp_path / 'documents')
    monkeypatch.setattr(vector_store, 'VECTOR_DIR', tmp_path / 'vectors')
    monkeypatch.setattr(vector_store, 'embed', lambda texts, **kwargs:
                        np.tile(np.asarray([[1.0, 0.0]], dtype='float32'), (len(texts), 1)))
    content = '年份,收入\n2024,100\n2025,120\n'.encode()

    uploaded = document_service.import_document(content, 'revenue.csv')
    indexed = document_service.index_document(uploaded['document_id'])
    answer = query_table(uploaded['document_id'], '表格中2025年收入是多少？')
    stored_path, _ = document_service.original_file_path(uploaded['document_id'])

    assert indexed['status'] == 'indexed'
    assert stored_path.suffix == '.csv'
    assert answer['value'] == '120'
    assert answer['sources'][0]['page'] == 1
    assert answer['sources'][0]['source'] == 'spreadsheet'


def test_upload_api_accepts_multiple_material_formats(monkeypatch):
    calls = []

    def start(content, filename):
        calls.append((content, filename))
        return {'document_id': f'doc_{len(calls)}', 'filename': filename, 'status': 'uploaded'}

    monkeypatch.setattr(document_api, 'start_document_import', start)
    response = TestClient(app).post('/api/documents/upload?background=true', files=[
        ('files', ('notes.txt', b'material text', 'text/plain')),
        ('files', ('table.csv', b'year,value\n2025,10', 'text/csv')),
    ])

    assert response.status_code == 200
    assert [item['filename'] for item in response.json()['documents']] == ['notes.txt', 'table.csv']
    assert len(calls) == 2


def test_upload_api_rejects_over_ten_files_before_import(monkeypatch):
    monkeypatch.setattr(document_api, 'start_document_import',
                        lambda *_: (_ for _ in ()).throw(AssertionError('must reject batch first')))
    files = [('files', (f'{index}.txt', b'x', 'text/plain')) for index in range(11)]

    response = TestClient(app).post('/api/documents/upload?background=true', files=files)

    assert response.status_code == 413
    assert response.json()['error']['code'] == 'DOCUMENT_COUNT_LIMIT'


def test_text_parse_rejects_unreadable_or_empty_content():
    with pytest.raises(AppError) as error:
        parse_document(b'\xff\xfe\xff', 'notes.txt')

    assert error.value.code == 'DOCUMENT_DECODE_FAILED'
