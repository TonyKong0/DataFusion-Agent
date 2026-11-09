"""Cooperative cancellation for in-flight conversation turns."""

from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock
from time import monotonic

from app.core.errors import AppError


_current: ContextVar[tuple[str, str, str] | None] = ContextVar('conversation_operation', default=None)
_cancelled: dict[tuple[str, str, str], float] = {}
_lock = Lock()
_RETENTION_SECONDS = 300


def _prune(now: float) -> None:
    for key, timestamp in list(_cancelled.items()):
        if now - timestamp > _RETENTION_SECONDS:
            _cancelled.pop(key, None)


def cancel(owner_id: str, conversation_id: str, operation_id: str) -> None:
    with _lock:
        now = monotonic()
        _prune(now)
        _cancelled[(owner_id, conversation_id, operation_id)] = now


def check() -> None:
    key = _current.get()
    if key is None:
        return
    with _lock:
        stopped = key in _cancelled
    if stopped:
        raise AppError('REQUEST_CANCELLED', '本次问答已中断', 409)


@contextmanager
def operation(owner_id: str, conversation_id: str, operation_id: str | None):
    if not operation_id:
        yield
        return
    key = (owner_id, conversation_id, operation_id)
    token = _current.set(key)
    try:
        check()
        yield
    finally:
        _current.reset(token)
        with _lock:
            _cancelled.pop(key, None)
