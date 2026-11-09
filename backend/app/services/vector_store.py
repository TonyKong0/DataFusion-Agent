import json
import threading
import uuid
from pathlib import Path

import faiss
import numpy as np

from app.core.config import BACKEND_DIR, get_settings
from app.core.errors import AppError
from app.services.document_service import document_path
from app.services.embedding_service import embed

VECTOR_DIR = BACKEND_DIR / 'data/vector_store'
_INDEX_LOCK = threading.RLock()


def _legacy_index_path(document_id: str):
    document_path(document_id)
    return VECTOR_DIR / f'{document_id}.faiss'


def _manifest_path(document_id: str):
    document_path(document_id)
    return VECTOR_DIR / f'{document_id}.index.json'


def _read_manifest(document_id: str) -> dict | None:
    manifest_path = _manifest_path(document_id)
    if not manifest_path.is_file():
        return None
    data = json.loads(manifest_path.read_text(encoding='utf-8'))
    index_file = data.get('index_file')
    if not isinstance(index_file, str) or Path(index_file).name != index_file:
        raise ValueError('invalid index manifest')
    return data


def index_path(document_id: str):
    """Return the published index path, with compatibility for legacy indexes."""
    with _INDEX_LOCK:
        try:
            manifest = _read_manifest(document_id)
        except (OSError, ValueError, json.JSONDecodeError):
            manifest = None
        if manifest:
            return VECTOR_DIR / manifest['index_file']
        return _legacy_index_path(document_id)


def _read_index_metadata(document_id: str) -> tuple[dict, object]:
    manifest = _read_manifest(document_id)
    if manifest:
        path = VECTOR_DIR / manifest['index_file']
        return manifest, path
    target = _legacy_index_path(document_id)
    metadata_path = target.with_suffix('.model.json')
    if not metadata_path.is_file():
        raise FileNotFoundError('index metadata missing')
    return json.loads(metadata_path.read_text(encoding='utf-8')), target


def build_index(document: dict, progress=None) -> None:
    """Build a candidate index and atomically publish it with a manifest."""
    texts = [chunk['text'] for chunk in document['content']]
    vectors = embed(texts) if progress is None else embed(texts, progress=progress)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    VECTOR_DIR.mkdir(parents=True, exist_ok=True)
    document_id = document['document_id']
    _legacy_index_path(document_id)  # Validate the ID before constructing paths.
    generation = uuid.uuid4().hex
    candidate = VECTOR_DIR / f'{document_id}.{generation}.faiss'
    temporary_index = candidate.with_suffix('.faiss.tmp')
    temporary_manifest = _manifest_path(document_id).with_suffix('.index.json.tmp')
    manifest = {'model': get_settings().embedding_model, 'chunks': len(document['content']),
                'index_file': candidate.name}
    published = False
    try:
        temporary_index.write_bytes(faiss.serialize_index(index).tobytes())
        temporary_index.replace(candidate)
        temporary_manifest.write_text(json.dumps(manifest), encoding='utf-8')
        with _INDEX_LOCK:
            temporary_manifest.replace(_manifest_path(document_id))
            published = True
            # Readers load the published bytes while holding this same lock, so old
            # generations are safe to remove after the manifest swap.
            for path in VECTOR_DIR.glob(f'{document_id}*.faiss'):
                if path != candidate:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        pass
            try:
                _legacy_index_path(document_id).with_suffix('.model.json').unlink(missing_ok=True)
            except OSError:
                pass
    except Exception:
        temporary_index.unlink(missing_ok=True)
        if not published:
            candidate.unlink(missing_ok=True)
        temporary_manifest.unlink(missing_ok=True)
        raise


def ready(document_id: str) -> bool:
    with _INDEX_LOCK:
        try:
            metadata, target = _read_index_metadata(document_id)
            return (target.is_file()
                    and metadata.get('model') == get_settings().embedding_model
                    and isinstance(metadata.get('chunks'), int))
        except (OSError, ValueError, json.JSONDecodeError, AppError):
            return False


def search(document: dict, question: str, top_k: int,
           *, extra_chunk_ids: set[str] | None = None) -> list[dict]:
    try:
        with _INDEX_LOCK:
            metadata, target = _read_index_metadata(document['document_id'])
            if (metadata.get('model') != get_settings().embedding_model or not target.is_file()
                    or metadata.get('chunks') != len(document['content'])):
                raise ValueError('index metadata mismatch')
            serialized = np.frombuffer(target.read_bytes(), dtype='uint8').copy()
            index = faiss.deserialize_index(serialized)
        if index.ntotal != len(document['content']):
            raise ValueError('index row count mismatch')
        vector = embed([question])
        scores, positions = index.search(vector, min(top_k, index.ntotal))
        candidates = {int(position): float(score)
                      for score, position in zip(scores[0], positions[0]) if position >= 0}
        if extra_chunk_ids:
            for position, chunk in enumerate(document['content']):
                if chunk['chunk_id'] in extra_chunk_ids and position not in candidates:
                    candidates[position] = float(np.dot(index.reconstruct(position), vector[0]))
        return [{**document['content'][position], 'score': round(score, 4)}
                for position, score in sorted(candidates.items(), key=lambda item: -item[1])]
    except AppError:
        raise
    except Exception:
        raise AppError('VECTOR_SEARCH_FAILED', '向量检索失败，请重新建立索引', 503) from None


def remove_index(document_id: str) -> None:
    target = _legacy_index_path(document_id)
    with _INDEX_LOCK:
        for path in VECTOR_DIR.glob(f'{document_id}*'):
            if path.is_file():
                path.unlink(missing_ok=True)
        target.with_suffix('.model.json').unlink(missing_ok=True)
