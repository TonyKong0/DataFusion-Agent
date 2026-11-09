import re

from app.services import nl2sql_service


def test_artist_count_and_roster_uses_two_bounded_single_table_queries(monkeypatch):
    schema = [{'table': 'artist', 'columns': [
        {'name': 'ArtistId', 'type': 'int', 'primary_key': True, 'nullable': False},
        {'name': 'Name', 'type': 'varchar(120)', 'primary_key': False, 'nullable': True}],
        'foreign_keys': []}]
    executed = []
    monkeypatch.setattr(nl2sql_service, 'load_schema', lambda: schema)
    monkeypatch.setattr(nl2sql_service, 'chat_json', lambda *_: (_ for _ in ()).throw(
        AssertionError('known artist query should not need SQL generation')))

    def execute(sql):
        executed.append(sql)
        if 'COUNT(' in sql:
            return ['total'], [[3]]
        return ['ArtistId', 'Name'], [[1, 'AC/DC'], [2, 'Queen'], [3, 'Jazz Artist']]

    monkeypatch.setattr(nl2sql_service, 'execute_sql', execute)
    result = nl2sql_service.query('一共有多少音乐家，他们分别是谁')

    assert result['need_clarification'] is False
    assert result['total_count'] == 3
    assert all(name in result['answer'] for name in ('AC/DC', 'Queen', 'Jazz Artist'))
    assert len(executed) == 2
    assert all('LIMIT 100' in sql and 'JOIN' not in sql for sql in executed)


def test_artist_roster_reports_when_the_100_row_limit_truncates_names(monkeypatch):
    schema = [{'table': 'artist', 'columns': [
        {'name': 'ArtistId', 'type': 'int'}, {'name': 'Name', 'type': 'varchar(120)'}]}]
    monkeypatch.setattr(nl2sql_service, 'load_schema', lambda: schema)
    monkeypatch.setattr(nl2sql_service, 'execute_sql', lambda sql:
                        (['total'], [[275]]) if 'COUNT(' in sql else
                        (['ArtistId', 'Name'], [[index, f'Artist {index}'] for index in range(1, 101)]))

    result = nl2sql_service.query('一共有多少音乐家，他们分别是谁')

    assert result['total_count'] == 275
    assert result['row_count'] == 100
    assert '还有 175 位未列出' in result['answer']


def test_explicit_all_artists_fetches_every_page_without_exceeding_page_limit(monkeypatch):
    schema = [{'table': 'artist', 'columns': [
        {'name': 'ArtistId', 'type': 'int'}, {'name': 'Name', 'type': 'varchar(120)'}]}]
    executed = []
    monkeypatch.setattr(nl2sql_service, 'load_schema', lambda: schema)
    monkeypatch.setattr(nl2sql_service, 'chat_json', lambda *_: (_ for _ in ()).throw(
        AssertionError('explicit artist roster should not call SQL model')))

    def execute(sql):
        executed.append(sql)
        if 'COUNT(' in sql:
            return ['total'], [[205]]
        last_id = int(re.search(r'ArtistId > (\d+)', sql).group(1))
        ids = range(last_id + 1, min(last_id + 101, 206))
        return ['ArtistId', 'Name'], [[identifier, f'Artist {identifier}'] for identifier in ids]

    monkeypatch.setattr(nl2sql_service, 'execute_sql', execute)
    result = nl2sql_service.query('把全部音乐家列出来')

    assert result['need_clarification'] is False
    assert result['total_count'] == result['row_count'] == 205
    assert len(result['page_sqls']) == 3
    assert all('LIMIT 100' in sql and 'JOIN' not in sql for sql in executed)
    assert 'Artist 205' in result['answer']
    assert '未列出' not in result['answer']
