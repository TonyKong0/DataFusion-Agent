"""Single entry point for reading and explicitly refreshing cached metadata."""

from threading import Lock

from app.schema.metadata_loader import load_metadata
from app.schema.schema_cache import get_cached_metadata, replace_cached_metadata
from app.schema.models import SchemaMetadata


_load_lock = Lock()


def get_metadata() -> SchemaMetadata:
    cached = get_cached_metadata()
    if cached is not None:
        return cached
    with _load_lock:
        cached = get_cached_metadata()
        if cached is None:
            cached = load_metadata()
            replace_cached_metadata(cached)
        return cached


def refresh_metadata() -> SchemaMetadata:
    with _load_lock:
        snapshot = load_metadata()
        replace_cached_metadata(snapshot)
        return snapshot

