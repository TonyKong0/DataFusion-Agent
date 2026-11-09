import json
from copy import deepcopy
from contextlib import contextmanager

import pytest
import pymysql
import sqlglot

from app.core.errors import AppError
from app.schema.schema_graph import SchemaGraph
from app.services import multitable_service
from app.sql.join_path_planner import plan_join_path
from app.sql.multitable_validator import validate_multitable_sql
from app.sql import multitable_executor
from tests.test_sql_phase26 import SCHEMA


PLAN = plan_join_path(['customer', 'invoice'], SchemaGraph(SCHEMA))
COLUMNS = ['customer.CustomerId', 'customer.FirstName', 'invoice.Total']
VALID = ('SELECT c.CustomerId, SUM(i.Total) AS spent FROM customer c '
         'JOIN invoice i ON c.CustomerId=i.CustomerId GROUP BY c.CustomerId LIMIT 10')
VALID_DSL = {
    'table': 'customer',
    'select': [
        {'kind': 'column', 'field': {'table': 'customer', 'column': 'CustomerId'}},
        {'kind': 'aggregate', 'function': 'SUM',
         'field': {'table': 'invoice', 'column': 'Total'}, 'alias': 'spent'},
    ],
    'group_by': [{'table': 'customer', 'column': 'CustomerId'}],
    'order_by': [{'field': 'spent', 'direction': 'DESC'}],
    'limit': 10,
}


def test_valid_sql_and_limit_bound():
    assert 'JOIN invoice' in validate_multitable_sql(VALID, PLAN, SCHEMA, COLUMNS)
    assert validate_multitable_sql(VALID.replace('LIMIT 10', 'LIMIT 9999'), PLAN, SCHEMA, COLUMNS).endswith('LIMIT 100')


@pytest.mark.parametrize('predicate', [
    "c.Country='USA' AND c.CustomerId > 0",
    "c.Country='USA' OR c.Country='Canada'",
    "(c.Country='USA' AND c.CustomerId > 0) OR c.Country='Canada'",
])
def test_boolean_predicates_are_safe_for_selected_columns(predicate):
    sql = VALID.replace(' GROUP BY', f' WHERE {predicate} GROUP BY')
    selected = [*COLUMNS, 'customer.Country']

    validated = validate_multitable_sql(sql, PLAN, SCHEMA, selected)

    validated_where = sqlglot.parse_one(validated, read='mysql').args['where'].this
    expected_where = sqlglot.parse_one(sql, read='mysql').args['where'].this
    assert validated_where == expected_where


def test_year_function_is_safe_for_selected_date_column():
    sql = VALID.replace(' GROUP BY', ' WHERE YEAR(i.InvoiceDate)=2010 GROUP BY')
    selected = [*COLUMNS, 'invoice.InvoiceDate']

    validated = validate_multitable_sql(sql, PLAN, SCHEMA, selected)

    assert 'YEAR(i.InvoiceDate) = 2010' in validated


def test_date_range_and_operator_is_safe_for_selected_date_column():
    sql = VALID.replace(
        ' GROUP BY',
        " WHERE i.InvoiceDate >= '2010-01-01' AND i.InvoiceDate < '2011-01-01' GROUP BY",
    )
    selected = [*COLUMNS, 'invoice.InvoiceDate']

    validated = validate_multitable_sql(sql, PLAN, SCHEMA, selected)

    assert "i.InvoiceDate >= '2010-01-01'" in validated
    assert "i.InvoiceDate < '2011-01-01'" in validated


@pytest.mark.parametrize('sql', [
    VALID.replace('SUM(i.Total)', 'SUM(c.CustomerId)'),
    VALID.replace('SUM(i.Total)', 'COUNT(c.CustomerId)'),
    VALID.replace('SUM(i.Total)', 'SUM(i.Total + c.CustomerId)'),
])
def test_parent_aggregates_are_rejected_when_child_join_can_repeat_rows(sql):
    with pytest.raises(AppError, match='重复'):
        validate_multitable_sql(sql, PLAN, SCHEMA, COLUMNS)


def test_count_distinct_parent_primary_key_and_child_aggregate_are_safe():
    distinct_parent_count = VALID.replace('SUM(i.Total)', 'COUNT(DISTINCT c.CustomerId)')
    distinct_parent_value_count = VALID.replace('SUM(i.Total)', 'COUNT(DISTINCT c.FirstName)')
    child_total = VALID.replace('SUM(i.Total)', 'SUM(i.Total)')
    joined_invoice_count = VALID.replace('SUM(i.Total)', 'COUNT(*)')

    assert 'COUNT(DISTINCT c.CustomerId)' in validate_multitable_sql(
        distinct_parent_count, PLAN, SCHEMA, COLUMNS)
    assert 'COUNT(DISTINCT c.FirstName)' in validate_multitable_sql(
        distinct_parent_value_count, PLAN, SCHEMA, COLUMNS)
    assert 'SUM(i.Total)' in validate_multitable_sql(child_total, PLAN, SCHEMA, COLUMNS)
    assert 'COUNT(*)' in validate_multitable_sql(joined_invoice_count, PLAN, SCHEMA, COLUMNS)
    assert 'COUNT(*)' in validate_multitable_sql(joined_invoice_count, PLAN, SCHEMA, COLUMNS)


@pytest.mark.parametrize('sql', [
    VALID.replace('i.Total', 'i.NotAColumn'),
    VALID.replace('c.CustomerId=i.CustomerId', 'c.CustomerId=i.InvoiceId'),
    VALID.replace('SELECT c.CustomerId', 'SELECT c.BadName'),
    'DELETE FROM invoice',
    'UPDATE invoice SET Total=0',
    'DROP TABLE invoice',
    VALID.replace('JOIN invoice i ON', 'CROSS JOIN invoice i ON'),
    VALID + '; DELETE FROM invoice',
    VALID.replace('SUM(i.Total)', 'SLEEP(10)'),
])
def test_unsafe_sql_is_rejected(sql):
    with pytest.raises(AppError):
        validate_multitable_sql(sql, PLAN, SCHEMA, COLUMNS)


def test_unknown_or_ambiguous_column_is_rejected():
    with pytest.raises(AppError):
        validate_multitable_sql(VALID.replace('c.CustomerId,', 'UnknownColumn,'), PLAN, SCHEMA, COLUMNS)
    with pytest.raises(AppError):
        validate_multitable_sql(VALID.replace('c.CustomerId,', 'CustomerId,'), PLAN, SCHEMA, COLUMNS)


def test_one_repair_receives_diagnostic_and_is_revalidated(monkeypatch):
    monkeypatch.setattr(multitable_service, 'get_metadata', lambda: SCHEMA)
    calls = []

    def generate(system, user):
        calls.append((system, json.loads(user)))
        invalid = deepcopy(VALID_DSL)
        invalid['select'][1]['field']['column'] = 'Missing'
        return {'query': invalid if len(calls) == 1 else VALID_DSL}

    monkeypatch.setattr(multitable_service, 'chat_json', generate)
    monkeypatch.setattr(multitable_service, 'execute_multitable_sql', lambda sql, params=(): (['CustomerId', 'spent'], [[1, 42]]))
    monkeypatch.setattr(multitable_service, 'chat', lambda *_: '已回答')
    result = multitable_service.query('每个客户消费了多少钱')
    assert result['sql_validation']['repair_count'] == 1
    assert calls[1][1]['original_query']['select'][1]['field']['column'] == 'Missing'
    assert calls[1][1]['join_path'] == result['join_plan']['join_path']
    assert any(item['step'] == 'sql_repair_1' for item in result['trace'])


def test_repairs_stop_after_two_attempts(monkeypatch):
    monkeypatch.setattr(multitable_service, 'get_metadata', lambda: SCHEMA)
    calls = []

    def always_invalid(*_):
        calls.append(True)
        invalid = deepcopy(VALID_DSL)
        invalid['select'][1]['field']['column'] = 'Missing'
        return {'query': invalid}

    monkeypatch.setattr(multitable_service, 'chat_json', always_invalid)
    with pytest.raises(AppError) as error:
        multitable_service.query('每个客户消费了多少钱')
    assert error.value.code == 'QUERY_DSL_INVALID'
    assert len(calls) == 3  # initial generation + two repairs


def test_model_cannot_override_planned_join_root(monkeypatch):
    monkeypatch.setattr(multitable_service, 'get_metadata', lambda: SCHEMA)
    wrong_order = deepcopy(VALID_DSL)
    wrong_order['table'] = 'invoice'
    generated = []
    monkeypatch.setattr(multitable_service, 'chat_json', lambda *_: generated.append(wrong_order) or {'query': wrong_order})
    monkeypatch.setattr(multitable_service, 'execute_multitable_sql', lambda sql, params=(): (['CustomerId', 'spent'], [[1, 42]]))
    monkeypatch.setattr(multitable_service, 'chat', lambda *_: '已回答')
    result = multitable_service.query('每个客户消费了多少钱')
    assert result['sql_validation']['repair_count'] == 0
    assert len(generated) == 1
    assert result['join_plan']['join_tables'] == ['customer', 'invoice']
    assert result['sql'].startswith('SELECT `t0`.`CustomerId`')


@pytest.mark.parametrize('code,diagnostic', [(1054, 'Unknown column'),
    (1064, 'Syntax error'), (1052, 'Ambiguous column')])
def test_execution_feedback_is_bounded_and_sanitized(monkeypatch, code, diagnostic):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def execute(self, _):
            raise pymysql.MySQLError(code, 'database internal details')

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def fake_connection():
        yield Connection()

    monkeypatch.setattr(multitable_executor, 'connection', fake_connection)
    with pytest.raises(AppError) as error:
        multitable_executor.execute_multitable_sql(VALID)
    assert error.value.diagnostic == diagnostic
    assert 'database internal details' not in error.value.message
