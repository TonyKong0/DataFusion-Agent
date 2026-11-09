from contextlib import contextmanager

import pytest

from app.core.errors import AppError
from app.schema.schema_graph import SchemaGraph
from app.services import sql_executor
from app.sql.join_path_planner import plan_join_path
from app.sql import multitable_executor
from app.sql.multitable_validator import validate_multitable_sql
from app.sql.query_dsl import compile_query_dsl, normalize_ranking_query, render_pymysql_sql
from tests.test_sql_phase26 import SCHEMA


def test_single_table_query_compiles_bound_filter_values_and_bounds_limit():
    query = {
        'table': 'genre',
        'select': [{'kind': 'column', 'field': {'column': 'Name'}}],
        'filters': {'field': {'column': 'Name'}, 'operator': 'eq', 'values': ['Rock']},
        'group_by': [],
        'order_by': [{'field': 'Name', 'direction': 'ASC'}],
        'limit': 500,
    }
    schema = [{'table': 'genre', 'columns': [{'name': 'GenreId'}, {'name': 'Name'}]}]

    compiled = compile_query_dsl(query, schema, max_rows=100)

    assert compiled.table == 'genre'
    assert compiled.params == ('Rock',)
    assert "'Rock'" not in compiled.sql
    assert 'WHERE `genre`.`Name` = ?' in compiled.sql
    assert compiled.sql.endswith('LIMIT 100')
    assert render_pymysql_sql(compiled.sql).endswith('LIMIT 100')
    assert 'WHERE `genre`.`Name` = %s' in render_pymysql_sql(compiled.sql)


def test_multi_table_query_uses_planned_join_and_nested_boolean_filters():
    plan = plan_join_path(['customer', 'invoice'], SchemaGraph(SCHEMA))
    query = {
        'table': 'customer',
        'select': [
            {'kind': 'column', 'field': {'table': 'customer', 'column': 'CustomerId'}},
            {'kind': 'aggregate', 'function': 'SUM',
             'field': {'table': 'invoice', 'column': 'Total'}, 'alias': 'spent'},
        ],
        'filters': {
            'logic': 'AND',
            'conditions': [
                {'logic': 'OR', 'conditions': [
                    {'field': {'table': 'customer', 'column': 'Country'},
                     'operator': 'eq', 'values': ['USA']},
                    {'field': {'table': 'customer', 'column': 'Country'},
                     'operator': 'eq', 'values': ["Côte d'Ivoire"]},
                ]},
                {'field': {'table': 'invoice', 'column': 'InvoiceDate'},
                 'operator': 'between', 'values': ['2010-01-01', '2010-12-31']},
            ],
        },
        'group_by': [{'table': 'customer', 'column': 'CustomerId'}],
        'order_by': [
            {'field': 'spent', 'direction': 'DESC'},
            {'field': 'customer.CustomerId', 'direction': 'ASC'},
        ],
        'limit': 10,
    }
    selected = [
        'customer.CustomerId', 'customer.Country', 'invoice.Total', 'invoice.InvoiceDate',
    ]

    compiled = compile_query_dsl(
        query, SCHEMA, join_plan=plan, selected_columns=selected, max_rows=100,
    )
    validated = validate_multitable_sql(compiled.sql, plan, SCHEMA, selected)
    normalized_sql = validated.replace('`', '')

    assert compiled.params == ('USA', "Côte d'Ivoire", '2010-01-01', '2010-12-31')
    assert 'JOIN invoice AS t1 ON t0.CustomerId = t1.CustomerId' in normalized_sql
    assert 'WHERE ((t0.Country = ? OR t0.Country = ?) AND t1.InvoiceDate BETWEEN ? AND ?)' in normalized_sql
    assert 'ORDER BY spent DESC, t0.CustomerId ASC' in normalized_sql
    assert 'LIMIT 10' in normalized_sql
    assert "Côte d'Ivoire" not in normalized_sql
    assert render_pymysql_sql(validated).count('%s') == 4


def test_generated_from_and_join_shapes_cannot_override_trusted_join_plan():
    plan = plan_join_path(['customer', 'invoice'], SchemaGraph(SCHEMA))
    query = {
        'from': {'table': 'invoice'},
        'join': [{'type': 'LEFT', 'table': 'untrusted'}],
        'select': [
            {'kind': 'column', 'field': {'table': 'customer', 'column': 'CustomerId'}},
            {'kind': 'aggregate', 'function': 'COUNT',
             'field': {'table': 'invoice', 'column': 'InvoiceId'}, 'alias': 'orders'},
        ],
        'filters': [
            {'field': {'table': 'customer', 'column': 'Country'},
             'operator': 'eq', 'values': ['USA']},
            {'field': {'table': 'invoice', 'column': 'InvoiceDate'},
             'operator': 'gte', 'values': ['2010-01-01']},
        ],
        'group_by': [{'table': 'customer', 'column': 'CustomerId'}],
        'order_by': [{'field': {'table': 'customer', 'column': 'CustomerId'},
                      'direction': 'ASC'}],
    }
    selected = ['customer.CustomerId', 'customer.Country', 'invoice.InvoiceId', 'invoice.InvoiceDate']

    compiled = compile_query_dsl(
        query, SCHEMA, join_plan=plan, selected_columns=selected,
    )
    sql = validate_multitable_sql(compiled.sql, plan, SCHEMA, selected)

    assert '`customer` AS `t0`' in sql
    assert '`invoice` AS `t1` ON `t0`.`CustomerId` = `t1`.`CustomerId`' in sql
    assert 'untrusted' not in sql
    assert 'LEFT JOIN' not in sql
    assert "`t0`.`Country` = ? AND `t1`.`InvoiceDate` >= ?" in sql
    assert compiled.params == ('USA', '2010-01-01')
    assert 'ORDER BY `t0`.`CustomerId` ASC' in sql


def test_sorting_by_an_aggregate_source_uses_its_selected_output_alias():
    plan = plan_join_path(['customer', 'invoice'], SchemaGraph(SCHEMA))
    query = {
        'from': {'table': 'customer'},
        'select': [{'kind': 'aggregate', 'function': 'COUNT',
                    'field': {'table': 'invoice', 'column': 'InvoiceId'},
                    'alias': 'order_count'}],
        'group_by': [{'table': 'customer', 'column': 'CustomerId'}],
        'order_by': [
            {'field': {'table': 'invoice', 'column': 'InvoiceId'}, 'direction': 'DESC'},
            {'field': {'table': 'customer', 'column': 'CustomerId'}, 'direction': 'ASC'},
        ],
    }
    selected = ['customer.CustomerId', 'invoice.InvoiceId']

    compiled = compile_query_dsl(
        query, SCHEMA, join_plan=plan, selected_columns=selected,
    )
    sql = validate_multitable_sql(compiled.sql, plan, SCHEMA, selected)

    assert 'ORDER BY `order_count` DESC, `t0`.`CustomerId` ASC' in sql


@pytest.mark.parametrize(('question', 'expected_limit'), [
    ('哪个音乐类型销量最高', 1),
    ('美国客户中消费最高的前 3 位是谁', 3),
    ('Canada top 5 customers by orders', 5),
])
def test_ranking_intent_sets_metric_order_and_respects_requested_top_limit(question, expected_limit):
    payload = {
        'select': [
            {'kind': 'column', 'field': {'table': 'genre', 'column': 'Name'}},
            {'kind': 'aggregate', 'function': 'SUM', 'field': {'table': 'invoice', 'column': 'Total'},
             'alias': 'total'},
        ],
        'order_by': [{'field': {'table': 'genre', 'column': 'Name'}, 'direction': 'ASC'}],
        'limit': 100,
    }

    normalized = normalize_ranking_query(payload, question)

    assert normalized['limit'] == expected_limit
    assert normalized['order_by'][0] == {'field': 'total', 'direction': 'DESC'}
    assert payload['limit'] == 100


def test_lowest_ranking_orders_ascending():
    payload = {
        'select': [{'kind': 'aggregate', 'function': 'MIN',
                    'field': {'table': 'invoice', 'column': 'Total'}, 'alias': 'minimum'}],
        'limit': 100,
    }

    assert normalize_ranking_query(payload, '订单金额最低的是多少')[
        'order_by'] == [{'field': 'minimum', 'direction': 'ASC'}]


def test_query_dsl_rejects_excessive_nesting_before_recursive_validation():
    schema = [{'table': 'genre', 'columns': [{'name': 'Name'}]}]
    nested_filter = {'field': {'column': 'Name'}, 'operator': 'eq', 'values': ['Rock']}
    for _ in range(20):
        nested_filter = {'logic': 'AND', 'conditions': [nested_filter, {
            'field': {'column': 'Name'}, 'operator': 'eq', 'values': ['Jazz'],
        }]}
    query = {
        'table': 'genre',
        'select': [{'kind': 'column', 'field': {'column': 'Name'}}],
        'filters': nested_filter,
    }

    with pytest.raises(AppError) as caught:
        compile_query_dsl(query, schema)

    assert caught.value.code == 'QUERY_DSL_INVALID'


def test_grouped_listing_uses_display_dimensions_as_stable_sort_keys():
    payload = {
        'select': [
            {'kind': 'column', 'field': {'table': 'artist', 'column': 'Name'}},
            {'kind': 'aggregate', 'function': 'COUNT',
             'field': {'table': 'track', 'column': 'TrackId'}, 'alias': 'track_count'},
        ],
        'order_by': [{'field': 'track_count', 'direction': 'DESC'}],
        'limit': 100,
    }

    normalized = normalize_ranking_query(payload, '每位艺术家的歌曲数量是多少？')

    assert normalized['order_by'] == [
        {'field': {'table': 'artist', 'column': 'Name'}, 'direction': 'ASC'},
    ]


def test_compiler_completes_grouping_and_normalizes_where_and_sort_alias_extras():
    plan = plan_join_path(['customer', 'invoice'], SchemaGraph(SCHEMA))
    query = {
        'from': {'table': 'customer'},
        'select': [
            {'kind': 'column', 'field': {'table': 'customer', 'column': 'FirstName'}},
            {'kind': 'aggregate', 'function': 'COUNT',
             'field': {'table': 'invoice', 'column': 'InvoiceId'}, 'alias': 'orders'},
        ],
        'where': {'field': {'table': 'customer', 'column': 'Country'},
                  'operator': 'eq', 'values': ['Canada']},
        'group_by': [{'table': 'customer', 'column': 'CustomerId'}],
        'order_by': [{'field': {'table': 'invoice', 'column': 'InvoiceId'},
                      'direction': 'DESC', 'alias': 'orders'}],
    }
    selected = ['customer.CustomerId', 'customer.FirstName', 'customer.Country', 'invoice.InvoiceId']

    compiled = compile_query_dsl(
        query, SCHEMA, join_plan=plan, selected_columns=selected,
    )
    sql = validate_multitable_sql(compiled.sql, plan, SCHEMA, selected)

    assert 'WHERE `t0`.`Country` = ?' in sql
    assert 'GROUP BY `t0`.`CustomerId`, `t0`.`FirstName`' in sql
    assert 'ORDER BY `orders` DESC' in sql
    assert compiled.params == ('Canada',)


@pytest.mark.parametrize('query', [
    {
        'table': 'genre',
        'select': [{'kind': 'column', 'field': {'column': 'Unknown'}}],
    },
    {
        'table': 'genre',
        'select': [{'kind': 'column', 'field': {'column': 'Name'}}],
        'filters': {'field': {'column': 'Name'}, 'operator': 'raw_sql', 'values': ['x']},
    },
])
def test_query_dsl_rejects_unknown_fields_and_unapproved_operators(query):
    schema = [{'table': 'genre', 'columns': [{'name': 'GenreId'}, {'name': 'Name'}]}]

    with pytest.raises(AppError) as caught:
        compile_query_dsl(query, schema)

    assert caught.value.code == 'QUERY_DSL_INVALID'


def test_multi_table_query_rejects_fields_outside_the_linked_column_allowlist():
    plan = plan_join_path(['customer', 'invoice'], SchemaGraph(SCHEMA))
    query = {
        'table': 'customer',
        'select': [{'kind': 'column', 'field': {'table': 'customer', 'column': 'Email'}}],
    }

    with pytest.raises(AppError) as caught:
        compile_query_dsl(
            query, SCHEMA, join_plan=plan,
            selected_columns=['customer.CustomerId', 'invoice.Total'],
        )

    assert caught.value.code == 'QUERY_DSL_INVALID'


def test_aggregate_query_compiler_groups_selected_nonaggregate_fields():
    schema = [{'table': 'genre', 'columns': [{'name': 'GenreId'}, {'name': 'Name'}]}]
    query = {
        'table': 'genre',
        'select': [
            {'kind': 'column', 'field': {'column': 'Name'}},
            {'kind': 'aggregate', 'function': 'COUNT', 'alias': 'total'},
        ],
    }

    compiled = compile_query_dsl(query, schema)

    assert 'GROUP BY `genre`.`Name`' in compiled.sql


@pytest.mark.parametrize('executor_module,execute', [
    (sql_executor, sql_executor.execute_sql),
    (multitable_executor, multitable_executor.execute_multitable_sql),
])
def test_mysql_executors_pass_compiled_parameters_separately(monkeypatch, executor_module, execute):
    statements = []

    class Cursor:
        description = [('Name',)]

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def execute(self, statement, params=None):
            statements.append((statement, params))

        def fetchmany(self, _):
            return [('Rock',)]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def cursor(self):
            return Cursor()

    @contextmanager
    def fake_connection():
        yield Connection()

    monkeypatch.setattr(executor_module, 'connection', fake_connection)

    columns, rows = execute('SELECT `genre`.`Name` FROM `genre` WHERE `genre`.`Name` = %s', ('Rock',))

    assert columns == ['Name']
    assert rows == [['Rock']]
    assert statements[-1] == (
        'SELECT `genre`.`Name` FROM `genre` WHERE `genre`.`Name` = %s', ('Rock',),
    )


def test_placeholder_adapter_only_rewrites_unquoted_question_marks():
    sql = "SELECT `column?` FROM `table` WHERE `name` = ? AND `note` = '?'"

    assert render_pymysql_sql(sql) == "SELECT `column?` FROM `table` WHERE `name` = %s AND `note` = '?'"


def test_contains_filter_escapes_like_wildcards_in_bound_value():
    schema = [{'table': 'genre', 'columns': [{'name': 'Name'}]}]
    query = {
        'table': 'genre',
        'select': [{'kind': 'column', 'field': {'column': 'Name'}}],
        'filters': {'field': {'column': 'Name'}, 'operator': 'contains', 'values': ['50%_off']},
    }

    compiled = compile_query_dsl(query, schema)

    assert compiled.params == ('%50\\%\\_off%',)
    assert 'LIKE ? ESCAPE' in compiled.sql
