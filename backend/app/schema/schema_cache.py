"""Process-local, atomic cache for one database schema snapshot."""

from threading import RLock

from app.schema.models import SchemaMetadata


_lock = RLock()
_snapshot: SchemaMetadata | None = None


def get_cached_metadata() -> SchemaMetadata | None:
    with _lock:
        return _snapshot.model_copy(deep=True) if _snapshot is not None else None


def replace_cached_metadata(snapshot: SchemaMetadata) -> None:
    global _snapshot
    with _lock:
        _snapshot = snapshot.model_copy(deep=True)

