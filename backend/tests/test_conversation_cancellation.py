from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest

from app.conversation import cancellation, store
from app.core.errors import AppError


def test_cancelled_operation_cannot_save_turn(monkeypatch):
    owner, conversation, operation_id = 'owner', 'conversation', str(uuid4())
    started, proceed = Event(), Event()
    monkeypatch.setattr(store, 'connection', lambda: (_ for _ in ()).throw(
        AssertionError('cancelled answer must never open a write transaction')))

    def worker():
        with cancellation.operation(owner, conversation, operation_id):
            started.set()
            assert proceed.wait(5)
            store.append_turn(owner, conversation, '问题', '问题', {'answer': '迟到的回答'}, {})

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(worker)
        assert started.wait(5)
        cancellation.cancel(owner, conversation, operation_id)
        proceed.set()
        with pytest.raises(AppError) as error:
            future.result(timeout=5)
    assert error.value.code == 'REQUEST_CANCELLED'


def test_cancel_before_worker_starts_is_honored():
    owner, conversation, operation_id = 'owner', 'conversation', str(uuid4())
    cancellation.cancel(owner, conversation, operation_id)
    with pytest.raises(AppError) as error:
        with cancellation.operation(owner, conversation, operation_id):
            pass
    assert error.value.code == 'REQUEST_CANCELLED'
