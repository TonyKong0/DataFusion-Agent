from app.services import nl2sql_service


GENRE_SCHEMA = [{'table': 'genre', 'columns': [
    {'name': 'GenreId', 'type': 'int'}, {'name': 'Name', 'type': 'varchar(120)'}]}]


def test_count_and_name_list_skip_answer_model(monkeypatch):
    monkeypatch.setattr(nl2sql_service, 'load_schema', lambda: GENRE_SCHEMA)
    monkeypatch.setattr(nl2sql_service, 'chat', lambda *_: (_ for _ in ()).throw(
        AssertionError('simple SQL results must not call the answer model')))
    generated = iter([
        {'query': {'table': 'genre', 'select': [
            {'kind': 'aggregate', 'function': 'COUNT', 'alias': 'total'}]}},
        {'query': {'table': 'genre', 'select': [
            {'kind': 'column', 'field': {'column': 'Name'}}],
            'order_by': [{'field': 'Name', 'direction': 'ASC'}]}},
    ])
    monkeypatch.setattr(nl2sql_service, 'chat_json', lambda *_: next(generated))
    monkeypatch.setattr(nl2sql_service, 'execute_sql', lambda sql:
                        (['total'], [[25]]) if 'COUNT(' in sql else
                        (['Name'], [['Rock'], ['Jazz']]))

    count = nl2sql_service.query('一共有多少音乐类型')
    names = nl2sql_service.query('列出所有音乐类型')

    assert count['answer'] == '音乐类型共有 25 种。'
    assert names['answer'] == '当前查询返回 2 种音乐类型：Rock、Jazz。'
    assert count['trace'][-1]['name'] == 'answer_generate'
    assert names['trace'][-1]['duration_ms'] < 100


def test_complex_result_keeps_model_answer(monkeypatch):
    monkeypatch.setattr(nl2sql_service, 'load_schema', lambda: GENRE_SCHEMA)
    monkeypatch.setattr(nl2sql_service, 'chat_json', lambda *_: {
        'query': {'table': 'genre', 'select': [
            {'kind': 'column', 'field': {'column': 'GenreId'}},
            {'kind': 'column', 'field': {'column': 'Name'}}],
            'order_by': [{'field': 'GenreId', 'direction': 'ASC'}]}})
    monkeypatch.setattr(nl2sql_service, 'execute_sql', lambda sql:
                        (['GenreId', 'Name'], [[1, 'Rock']]))
    calls = []
    monkeypatch.setattr(nl2sql_service, 'chat', lambda system, user:
                        calls.append(user) or '第一种音乐类型是 Rock。')

    result = nl2sql_service.query('查看音乐类型编号和名称')

    assert result['answer'] == '第一种音乐类型是 Rock。'
    assert len(calls) == 1


def test_select_star_with_id_and_name_skips_answer_model(monkeypatch):
    monkeypatch.setattr(nl2sql_service, 'load_schema', lambda: GENRE_SCHEMA)
    monkeypatch.setattr(nl2sql_service, 'chat_json', lambda *_: {
        'query': {'table': 'genre', 'select': [
            {'kind': 'column', 'field': {'column': 'GenreId'}},
            {'kind': 'column', 'field': {'column': 'Name'}}]}})
    monkeypatch.setattr(nl2sql_service, 'execute_sql', lambda sql:
                        (['GenreId', 'Name'], [[1, 'Rock'], [2, 'Jazz']]))
    monkeypatch.setattr(nl2sql_service, 'chat', lambda *_: (_ for _ in ()).throw(
        AssertionError('name roster must not call the answer model')))

    result = nl2sql_service.query('列出所有音乐类型')

    assert result['answer'] == '当前查询返回 2 种音乐类型：Rock、Jazz。'
