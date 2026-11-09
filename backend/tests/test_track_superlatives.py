from app.services import nl2sql_service


SCHEMA = [
    {'table': 'track', 'columns': [
        {'name': 'TrackId', 'type': 'int'}, {'name': 'Name', 'type': 'varchar(200)'},
        {'name': 'Milliseconds', 'type': 'int'}]},
    {'table': 'invoiceline', 'columns': [
        {'name': 'TrackId', 'type': 'int'}, {'name': 'Quantity', 'type': 'int'}]},
]


def test_longest_track_uses_duration_without_model_guess(monkeypatch):
    monkeypatch.setattr(nl2sql_service, 'load_schema', lambda: SCHEMA)
    monkeypatch.setattr(nl2sql_service, 'execute_sql', lambda sql:
                        (['TrackId', 'Name', 'Milliseconds'], [[9, 'Long Song', 5286953]]))
    monkeypatch.setattr(nl2sql_service, 'chat_json', lambda *_: (_ for _ in ()).throw(
        AssertionError('known duration must not call SQL model')))
    monkeypatch.setattr(nl2sql_service, 'chat', lambda *_: (_ for _ in ()).throw(
        AssertionError('known duration must not call answer model')))

    result = nl2sql_service.query('最长的歌曲')

    assert result['need_clarification'] is False
    assert 'Long Song' in result['answer']
    assert '5,286,953 毫秒' in result['answer']
    assert 'ORDER BY Milliseconds DESC' in result['sql']


def test_popular_music_uses_purchase_quantity_and_states_proxy(monkeypatch):
    monkeypatch.setattr(nl2sql_service, 'load_schema', lambda: SCHEMA)
    executed = []

    def execute(sql):
        executed.append(sql)
        if 'invoiceline' in sql.lower():
            return ['TrackId', 'sold'], [[7, 4]]
        return ['TrackId', 'Name'], [[7, 'Popular Song']]

    monkeypatch.setattr(nl2sql_service, 'execute_sql', execute)
    monkeypatch.setattr(nl2sql_service, 'chat_json', lambda *_: (_ for _ in ()).throw(
        AssertionError('known popularity proxy must not call SQL model')))

    result = nl2sql_service.query('最流行的音乐')

    assert result['need_clarification'] is False
    assert 'Popular Song' in result['answer']
    assert '售出 4 份' in result['answer']
    assert '没有播放量数据' in result['answer']
    assert len(executed) == 2
    assert all('LIMIT 1' in sql and 'JOIN' not in sql for sql in executed)
