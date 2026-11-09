import numpy as np
import pytest
from pathlib import Path
from app.core.errors import AppError
from app.services import vector_store as store


def test_faiss_persistence_and_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'VECTOR_DIR', tmp_path)
    monkeypatch.setattr(store, 'embed', lambda texts: np.asarray([[1, 0], [0, 1]] if len(texts)==2 else [[1, 0]], dtype='float32'))
    document = {'document_id': 'doc_'+'a'*32, 'content': [
        {'chunk_id': 'a', 'page': 1, 'text': 'first'}, {'chunk_id': 'b', 'page': 2, 'text': 'second'}]}
    store.build_index(document)
    assert store.ready(document['document_id'])
    hits = store.search(document, 'query', 1)
    assert hits[0]['page'] == 1 and hits[0]['score'] == 1
    store.remove_index(document['document_id'])
    assert not store.ready(document['document_id'])


def test_failed_rebuild_keeps_the_previous_index_searchable(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'VECTOR_DIR', tmp_path)
    def embeddings(texts):
        if texts == ['query']:
            return np.asarray([[1, 0]], dtype='float32')
        vectors = [[1, 0], [0, 1]] if texts[0].startswith('old') else [[0, 1], [1, 0]]
        return np.asarray(vectors, dtype='float32')

    monkeypatch.setattr(store, 'embed', embeddings)
    document_id = 'doc_'+'b'*32
    old_document = {'document_id': document_id, 'content': [
        {'chunk_id': 'old_first', 'page': 1, 'text': 'old first'},
        {'chunk_id': 'old_second', 'page': 2, 'text': 'old second'}]}
    store.build_index(old_document)
    replacement = {'document_id': document_id, 'content': [
        {'chunk_id': 'new_first', 'page': 1, 'text': 'new first'},
        {'chunk_id': 'new_second', 'page': 2, 'text': 'new second'}]}
    write_text = Path.write_text

    def fail_manifest(path, *args, **kwargs):
        if path.name.endswith('.index.json.tmp'):
            raise OSError('manifest publication failed')
        return write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'write_text', fail_manifest)
    with pytest.raises(OSError, match='manifest publication failed'):
        store.build_index(replacement)

    assert store.ready(document_id)
    assert store.search(old_document, 'query', 1)[0]['chunk_id'] == 'old_first'
