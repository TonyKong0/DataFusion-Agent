from app.services import nl2sql_service


def test_single_table_llm_query_is_compiled_and_executes_bound_values(monkeypatch):
    schema = [{'table': 'genre', 'columns': [{'name': 'GenreId'}, {'name': 'Name'}]}]
    generated_query = {
        'table': 'genre',
        'select': [{'kind': 'column', 'field': {'column': 'Name'}}],
        'filters': {
            'field': {'column': 'Name'},
            'operator': 'eq',
            'values': ["Rock' OR 1=1 --"],
        },
    }
    executions = []
    monkeypatch.setattr(nl2sql_service, 'load_schema', lambda: schema)
    monkeypatch.setattr(nl2sql_service, 'extract_elements', lambda *_: {
        'elements': [], 'fallback_used': False,
    })
    monkeypatch.setattr(nl2sql_service, 'validate_semantics', lambda *_args, **_kwargs: {
        'valid': True, 'need_clarification': False, 'missing': [], 'ambiguities': [],
        'unsupported': [], 'low_confidence': False, 'conflicts': [], 'error': None,
    })
    monkeypatch.setattr(nl2sql_service, 'chat_json', lambda *_: {'query': generated_query})

    def execute(sql, params=()):
        executions.append((sql, params))
        return ['Name'], [['Rock']]

    monkeypatch.setattr(nl2sql_service, 'execute_sql', execute)

    result = nl2sql_service.query('按名称查询音乐类型')

    assert executions == [
        ('SELECT `genre`.`Name` FROM genre WHERE `genre`.`Name` = %s LIMIT 100',
         ("Rock' OR 1=1 --",)),
    ]
    assert "Rock' OR 1=1 --" not in result['sql']
    assert "`genre`.`Name` = ?" in result['sql']
    assert result['table'] == 'genre'
    assert result['rows'] == [['Rock']]
    assert any(step['step'] == 'query_compile' and step['status'] == 'success'
               for step in result['trace'])
