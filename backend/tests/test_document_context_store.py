"""Document context must survive intervening turns about other PDFs."""

import json
from contextlib import contextmanager
from datetime import datetime

from app.conversation import store


def test_recent_document_turns_reaches_past_other_document_turns(monkeypatch):
    first, second = 'doc-a', 'doc-b'
    rows = []
    for identifier in range(1, 61):
        scope = [first] if identifier in {1, 5, 7} else [second]
        rows.append({'id': identifier, 'question': f'问题 {identifier}',
                     'resolved_question': f'问题 {identifier}', 'answer': f'回答 {identifier}',
                     'result_json': json.dumps({'document_ids': scope}),
                     'created_at': datetime(2026, 1, 1)})

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def execute(self, _sql, params):
            before = params[1] if len(params) > 1 else 61
            self.batch = [row.copy() for row in reversed(rows) if row['id'] < before][:50]

        def fetchall(self):
            return self.batch

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def fake_connection():
        yield Connection()

    monkeypatch.setattr(store, 'connection', fake_connection)

    turns = store.recent_document_turns('conversation', [first], 3)

    assert [turn['id'] for turn in turns] == [1, 5, 7]
    assert all(turn['result']['document_ids'] == [first] for turn in turns)
