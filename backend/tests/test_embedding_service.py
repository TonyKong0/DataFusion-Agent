import numpy as np

from app.services import embedding_service


class FakeEmbeddingModel:
    def __init__(self):
        self.calls = []

    def encode(self, texts, **kwargs):
        self.calls.append((list(texts), kwargs))
        return np.asarray([[len(text), index] for index, text in enumerate(texts)], dtype='float32')


def test_index_embeddings_report_chunk_progress_with_bounded_model_batches(monkeypatch):
    model = FakeEmbeddingModel()
    monkeypatch.setattr(embedding_service, '_model', model)
    progress = []

    vectors = embedding_service.embed([f'chunk-{index}' for index in range(10)],
                                      progress=lambda completed, total: progress.append((completed, total)))

    assert vectors.shape == (10, 2)
    assert [len(texts) for texts, _ in model.calls] == [8, 2]
    assert all(call['batch_size'] == embedding_service.INDEX_EMBED_BATCH_SIZE for _, call in model.calls)
    assert progress == [(8, 10), (10, 10)]

    model.calls.clear()
    query_vectors = embedding_service.embed(['query'])
    assert query_vectors.shape == (1, 2)
    assert len(model.calls) == 1
    assert len(model.calls[0][0]) == 1
    assert model.calls[0][1]['batch_size'] == embedding_service.INDEX_EMBED_BATCH_SIZE
