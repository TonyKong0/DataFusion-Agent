import threading
import os
import numpy as np
from app.core.config import get_settings
from app.core.config import BACKEND_DIR
from app.core.errors import AppError

_model = None
_lock = threading.RLock()
INDEX_PROGRESS_BATCH_SIZE = 8
INDEX_EMBED_BATCH_SIZE = 4


def embed(texts: list[str], progress=None) -> np.ndarray:
    """Lazy load the configured local model; normalize dense embeddings."""
    global _model
    settings = get_settings()
    try:
        with _lock:
            if _model is None:
                os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
                import torch
                from sentence_transformers import SentenceTransformer
                device = 'cuda' if torch.cuda.is_available() else 'cpu'
                local = BACKEND_DIR / 'data/models/bge-m3'
                model_name = str(local) if settings.embedding_model == 'BAAI/bge-m3' and (local / 'pytorch_model.bin').exists() else settings.embedding_model
                _model = SentenceTransformer(model_name, cache_folder=settings.embedding_cache_dir,
                    device=device, model_kwargs={'use_safetensors': False, 'torch_dtype': torch.float16 if device=='cuda' else torch.float32})
                _model.max_seq_length = 1024
            if progress is None or len(texts) <= INDEX_PROGRESS_BATCH_SIZE:
                result = _model.encode(texts, batch_size=INDEX_EMBED_BATCH_SIZE, normalize_embeddings=True,
                                       show_progress_bar=False)
                if progress is not None:
                    progress(len(texts), len(texts))
                return np.asarray(result, dtype='float32')
            vectors = []
            for start in range(0, len(texts), INDEX_PROGRESS_BATCH_SIZE):
                batch = texts[start:start + INDEX_PROGRESS_BATCH_SIZE]
                vectors.extend(_model.encode(batch, batch_size=INDEX_EMBED_BATCH_SIZE, normalize_embeddings=True,
                                             show_progress_bar=False))
                progress(start + len(batch), len(texts))
            return np.asarray(vectors, dtype='float32')
    except Exception:
        raise AppError('EMBEDDING_FAILED', 'Embedding 加载或计算失败，请先下载模型并检查运行环境', 503) from None
