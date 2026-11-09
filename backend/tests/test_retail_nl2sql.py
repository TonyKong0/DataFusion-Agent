import pytest

from app.core.errors import AppError
from app.sql.query_dsl import render_pymysql_sql
from app.services import nl2sql_service


RETAIL_SCHEMA = [{'table': 'retail_transaction', 'columns': [
    {'name': 'InvoiceDate', 'type': 'datetime'},
    {'name': 'Quantity', 'type': 'int'},
    {'name': 'StockCode', 'type': 'varchar(20)'},
    {'name': 'UnitPrice', 'type': 'decimal(10,4)'},
]}]


RETAIL_CASES = [
    (
        '零售商品的平均单价是多少',
        ['AVG(', 'UnitPrice', 'average_price', 'LIMIT 100'], (),
        ['average_price'], [[4.19598]],
    ),
    (
        '退货记录中的商品数量总和是多少',
        ['SUM(', 'Quantity', 'returned_quantity', 'WHERE', '< %s', 'LIMIT 100'], (0,),
        ['returned_quantity'], [[-157.0]],
    ),
    (
        '2010年有多少笔零售交易记录',
        ['COUNT(*)', 'InvoiceDate', '>= %s', 'AND', '< %s', 'LIMIT 100'],
        ('2010-01-01', '2011-01-01'),
        ['total'], [[490]],
    ),
    (
        '零售交易中销量最高的10个商品编号是什么',
        ['StockCode', 'SUM(', 'items_sold', 'GROUP BY', 'ORDER BY', 'DESC', 'ASC', 'LIMIT 10'], (),
        ['StockCode', 'items_sold'], [
            ['84077', 336.0], ['20713', 304.0], ['79164', 240.0],
            ['22386', 212.0], ['17038', 200.0], ['21244', 192.0],
            ['23439', 192.0], ['16235', 180.0], ['21212', 150.0], ['22866', 144.0],
        ],
    ),
]


@pytest.mark.parametrize(
    ('question', 'expected_sql', 'expected_params', 'columns', 'rows'), RETAIL_CASES,
)
def test_supported_retail_questions_compile_to_verified_single_table_dsl(
    monkeypatch, question, expected_sql, expected_params, columns, rows,
):
    executed = []
    monkeypatch.setattr(nl2sql_service, 'load_schema', lambda: RETAIL_SCHEMA)

    def execute(sql, params=()):
        executed.append((sql, tuple(params)))
        return columns, rows

    def unexpected_llm_call(*_args, **_kwargs):
        raise AssertionError('recognized retail benchmark questions must not require an LLM')

    monkeypatch.setattr(nl2sql_service, 'execute_sql', execute)
    monkeypatch.setattr(nl2sql_service, 'extract_elements', unexpected_llm_call)
    monkeypatch.setattr(nl2sql_service, 'chat_json', unexpected_llm_call)
    monkeypatch.setattr(nl2sql_service, 'chat', unexpected_llm_call)

    result = nl2sql_service.query(question)

    assert result['success'] is True
    assert result['need_clarification'] is False
    assert result['table'] == 'retail_transaction'
    assert all(fragment in executed[0][0] for fragment in expected_sql)
    assert executed[0][1] == expected_params
    assert result['columns'] == columns
    assert result['rows'] == rows
    assert render_pymysql_sql(result['sql']) == executed[0][0]


def test_query_compilation_failure_keeps_stage_and_generated_dsl(monkeypatch):
    schema = [{'table': 'genre', 'columns': [{'name': 'GenreId'}, {'name': 'Name'}]}]
    generated_query = {
        'table': 'genre',
        'select': [{'kind': 'column', 'field': {'column': 'NotAColumn'}}],
    }
    monkeypatch.setattr(nl2sql_service, 'load_schema', lambda: schema)
    monkeypatch.setattr(nl2sql_service, 'chat_json', lambda *_: {
        'query': generated_query,
    })

    with pytest.raises(AppError) as raised:
        nl2sql_service.query('列出所有音乐类型')

    assert raised.value.code == 'QUERY_DSL_INVALID'
    assert raised.value.failed_step == 'query_compile'
    assert raised.value.generated_query == generated_query
    assert raised.value.generated_sql is None
    assert raised.value.trace[-1]['status'] == 'failed'
