import json
from concurrent.futures import Future
from types import SimpleNamespace

import numpy as np
from fastapi.testclient import TestClient

from app.api import documents as document_api
from app.core.errors import AppError
from app.main import app
from app.services import document_service, vector_store


class DeferredExecutor:
    def __init__(self):
        self.jobs = []

    def submit(self, function, *args):
        future = Future()
        self.jobs.append((future, function, args))
        return future

    def run_all(self):
        for future, function, args in self.jobs:
            if not future.done():
                future.set_result(function(*args))


def _write_document(directory, document_id, text, status='parsed'):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{document_id}.json'
    path.write_text(json.dumps({
        'document_id': document_id, 'filename': f'{document_id}.pdf',
        'pages': 1, 'chunks': 1, 'status': status,
        'processing': {'fixture': True},
        'content': [{'chunk_id': document_id, 'page': 1, 'text': text}], 'trace': [],
    }), encoding='utf-8')


def test_index_jobs_isolate_a_failed_document_and_keep_retry_state(tmp_path, monkeypatch):
    documents_dir = tmp_path / 'documents'
    monkeypatch.setattr(document_service, 'DOCUMENT_DIR', documents_dir)
    monkeypatch.setattr(vector_store, 'VECTOR_DIR', tmp_path / 'vectors')
    executor = DeferredExecutor()
    monkeypatch.setattr(document_service, 'INDEX_EXECUTOR', executor)
    failed_id, successful_id = 'doc_' + 'a' * 32, 'doc_' + 'b' * 32
    _write_document(documents_dir, failed_id, 'fail this document', status='indexed')
    _write_document(documents_dir, successful_id, 'index this document')

    monkeypatch.setattr(vector_store, 'embed', lambda texts: np.asarray([[1, 0]], dtype='float32'))
    vector_store.build_index({'document_id': failed_id, 'content': [
        {'chunk_id': 'old', 'page': 1, 'text': 'old index'}]})
    fail_embedding = {'enabled': True}

    def embed(texts, progress=None):
        if fail_embedding['enabled'] and texts[0] == 'fail this document':
            raise AppError('EMBEDDING_FAILED', 'model unavailable', 503)
        return np.asarray([[1, 0]], dtype='float32')

    monkeypatch.setattr(vector_store, 'embed', embed)
    first = document_service.start_index_job(failed_id)
    second = document_service.start_index_job(successful_id)
    assert first['index_status']['status'] == 'uploaded'
    assert second['index_status']['status'] == 'uploaded'

    executor.run_all()

    failed = document_service.get_index_status(failed_id)
    successful = document_service.get_index_status(successful_id)
    assert failed['status'] == 'indexed'
    assert failed['index_status']['status'] == 'failed'
    assert failed['index_status']['retryable'] is True
    assert failed['index_status']['error'] == 'model unavailable'
    assert vector_store.ready(failed_id)
    assert vector_store.search({'document_id': failed_id, 'content': [
        {'chunk_id': 'old', 'page': 1, 'text': 'old index'}]}, 'query', 1)[0]['chunk_id'] == 'old'
    assert successful['status'] == 'indexed'
    assert successful['index_status']['percent'] == 100
    assert vector_store.ready(successful_id)

    fail_embedding['enabled'] = False
    document_service.start_index_job(failed_id)
    executor.run_all()
    retried = document_service.get_index_status(failed_id)
    assert retried['status'] == 'indexed'
    assert retried['index_status']['status'] == 'indexed'


def test_background_upload_defers_pdf_parsing_and_reports_each_phase(tmp_path, monkeypatch):
    monkeypatch.setattr(document_service, 'DOCUMENT_DIR', tmp_path / 'documents')
    monkeypatch.setattr(vector_store, 'VECTOR_DIR', tmp_path / 'vectors')
    executor = DeferredExecutor()
    monkeypatch.setattr(document_service, 'INDEX_EXECUTOR', executor)
    page = SimpleNamespace(page=1, text='Parsed document text.', headings=[], metadata={})
    processing = {'pages': [page], 'complexity': {'recommended_strategy': 'standard'},
        'metadata': {}, 'quality': {}, 'formulas': [],
        'tree': SimpleNamespace(to_dict=lambda: {'root': 'doc'}), 'trace': []}
    calls = []
    monkeypatch.setattr(document_service, 'process_document', lambda *_: calls.append('parsing') or processing)
    monkeypatch.setattr(document_service, 'split_pages', lambda *_: calls.append('chunking') or [
        {'chunk_id': 'parsed', 'page': 1, 'text': 'Parsed document text.'}])
    monkeypatch.setattr(document_service, 'extract_from_pages', lambda *_: [])
    def embed(texts, progress=None):
        calls.append('embedding')
        if progress:
            progress(len(texts), len(texts))
        return np.asarray([[1, 0]], dtype='float32')

    monkeypatch.setattr(vector_store, 'embed', embed)
    failures = []
    progress_updates = []
    update_status = document_service._update_index_status

    def record_status(document_id, job_id, status, **changes):
        if status == 'failed':
            failures.append(changes)
        if status == 'embedding':
            progress_updates.append((changes.get('completed_chunks'), changes.get('total_chunks'),
                                     changes.get('percent')))
        return update_status(document_id, job_id, status, **changes)

    monkeypatch.setattr(document_service, '_update_index_status', record_status)

    uploaded = document_service.start_document_import(b'%PDF-placeholder', 'report.pdf')

    assert uploaded['status'] == 'uploaded'
    assert calls == []
    executor.run_all()

    indexed = document_service.get_index_status(uploaded['document_id'])
    document = document_service.load_document(uploaded['document_id'])
    assert indexed['status'] == 'indexed', failures
    assert [item['step'] for item in document['trace'] if item['step'] in {'pdf_parse', 'chunk', 'embedding'}] == [
        'pdf_parse', 'chunk', 'embedding']
    assert calls == ['parsing', 'chunking', 'embedding']
    assert progress_updates[-1] == (1, 1, 99)


def test_orphaned_index_job_becomes_retryable_in_document_list(tmp_path, monkeypatch):
    documents_dir = tmp_path / 'documents'
    monkeypatch.setattr(document_service, 'DOCUMENT_DIR', documents_dir)
    monkeypatch.setattr(vector_store, 'VECTOR_DIR', tmp_path / 'vectors')
    monkeypatch.setattr(document_service, 'ACTIVE_INDEX_JOBS', {})
    document_id = 'doc_' + 'd' * 32
    _write_document(documents_dir, document_id, 'interrupted document', status='embedding')
    path = documents_dir / f'{document_id}.json'
    document = json.loads(path.read_text(encoding='utf-8'))
    document['index_status'] = {'job_id': 'job_stale', 'status': 'embedding', 'phase': 'embedding',
        'completed_chunks': 0, 'total_chunks': 1, 'percent': 0, 'retryable': False, 'error': None}
    path.write_text(json.dumps(document), encoding='utf-8')

    status = document_service.get_index_status(document_id)
    listed = document_service.list_documents()[0]

    assert status['status'] == 'failed'
    assert status['index_status']['retryable'] is True
    assert listed['status'] == 'failed'
    assert listed['index_status']['status'] == 'failed'
    assert listed['index_status']['retryable'] is True
    assert listed['index_status']['error'] == '索引任务已中断，请重试'


def test_legacy_upload_stays_synchronous_and_background_is_opt_in(monkeypatch):
    document = {'document_id': 'doc_' + 'c' * 32}
    calls = []
    monkeypatch.setattr(document_api, 'import_document', lambda *_: document)
    monkeypatch.setattr(document_api, 'index_document', lambda _id: calls.append('sync') or {
        'document_id': _id, 'status': 'indexed'})
    monkeypatch.setattr(document_api, 'start_document_import', lambda *_: calls.append('background') or {
        'document_id': document['document_id'], 'status': 'uploaded', 'index_status': {'status': 'uploaded'}})
    client = TestClient(app)

    legacy = client.post('/api/documents/upload', files={'file': ('legacy.pdf', b'%PDF-legacy', 'application/pdf')})
    background = client.post('/api/documents/upload?background=true',
        files={'file': ('background.pdf', b'%PDF-background', 'application/pdf')})

    assert legacy.status_code == 200 and legacy.json()['status'] == 'indexed'
    assert background.status_code == 200 and background.json()['status'] == 'uploaded'
    assert calls == ['sync', 'background']
