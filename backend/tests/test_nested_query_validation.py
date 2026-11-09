"""The only nested-query shape this project allows: one scalar aggregate comparison."""

import pytest

from app.core.errors import AppError
from app.schema.schema_graph import SchemaGraph
from app.services.sql_validator import validate_sql
from app.sql.join_path_planner import plan_join_path
from app.sql.multitable_validator import validate_multitable_sql
from app.sql.query_dsl import compile_query_dsl
from tests.test_sql_phase26 import SCHEMA

INVOICE_SCHEMA = [{'table': 'Invoice', 'columns': [
    {'name': 'InvoiceId'}, {'name': 'CustomerId'}, {'name': 'InvoiceDate'}, {'name': 'Total'},
]}]

ALLOWED_PREDICATE = 'Total > (SELECT AVG(Total) FROM Invoice)'


def test_single_table_scalar_subquery_is_accepted():
    sql, table = validate_sql(
        f'SELECT InvoiceId FROM Invoice WHERE {ALLOWED_PREDICATE}', 'Invoice', INVOICE_SCHEMA)

    assert table == 'Invoice'
    assert '(SELECT AVG(Total) FROM Invoice)' in sql.replace('`', '')
    assert sql.endswith('LIMIT 100')


@pytest.mark.parametrize('sql', [
    # 相关子查询：内部引用了外层字段
    'SELECT InvoiceId FROM Invoice i WHERE Total > (SELECT AVG(Total) FROM Invoice o '
    'WHERE o.CustomerId = i.CustomerId)',
    # 两个子查询
    'SELECT InvoiceId FROM Invoice WHERE Total > (SELECT AVG(Total) FROM Invoice) '
    'AND Total < (SELECT MAX(Total) FROM Invoice)',
    # 两层嵌套
    'SELECT InvoiceId FROM Invoice WHERE Total > (SELECT AVG(Total) FROM Invoice '
    'WHERE Total > (SELECT MIN(Total) FROM Invoice))',
    # FROM 侧子查询
    'SELECT InvoiceId FROM (SELECT InvoiceId FROM Invoice) x',
    # IN 列表子查询
    'SELECT InvoiceId FROM Invoice WHERE InvoiceId IN (SELECT InvoiceId FROM Invoice)',
    # SELECT 列表里的子查询
    'SELECT (SELECT AVG(Total) FROM Invoice) FROM Invoice',
    # 非聚合子查询
    'SELECT InvoiceId FROM Invoice WHERE Total > (SELECT Total FROM Invoice)',
    # 子查询内部 GROUP BY
    'SELECT InvoiceId FROM Invoice WHERE Total > (SELECT AVG(Total) FROM Invoice GROUP BY CustomerId)',
    # 子查询内部未知字段
    'SELECT InvoiceId FROM Invoice WHERE Total > (SELECT AVG(Unknown) FROM Invoice)',
    # CTE 仍然禁止
    'WITH x AS (SELECT InvoiceId FROM Invoice) SELECT * FROM x',
    'SELECT InvoiceId FROM Invoice UNION SELECT InvoiceId FROM Invoice',
])
def test_other_nested_shapes_stay_rejected(sql):
    with pytest.raises(AppError):
        validate_sql(sql, 'Invoice', INVOICE_SCHEMA)


def test_dsl_compiles_one_scalar_subquery_filter():
    payload = {
        'table': 'Invoice',
        'select': [{'kind': 'column', 'field': {'column': 'InvoiceId'}}],
        'filters': {'field': {'column': 'Total'}, 'operator': 'gt',
                    'subquery': {'aggregate': 'AVG', 'field': {'column': 'Total'}}},
        'limit': 50,
    }

    compiled = compile_query_dsl(payload, INVOICE_SCHEMA)
    validated, _ = validate_sql(compiled.sql, 'Invoice', INVOICE_SCHEMA)

    assert compiled.params == ()
    assert 'WHERE `Invoice`.`Total` > (SELECT AVG(`Total`) FROM `Invoice`)' in compiled.sql
    assert '(SELECT AVG(`Total`) FROM `Invoice`)' in validated


@pytest.mark.parametrize('filters', [
    # 子查询与字面量同时出现
    {'field': {'column': 'Total'}, 'operator': 'gt', 'values': [5],
     'subquery': {'aggregate': 'AVG', 'field': {'column': 'Total'}}},
    # 集合操作不能接子查询
    {'field': {'column': 'Total'}, 'operator': 'in',
     'subquery': {'aggregate': 'AVG', 'field': {'column': 'Total'}}},
    # 非 COUNT 聚合必须给字段
    {'field': {'column': 'Total'}, 'operator': 'gt', 'subquery': {'aggregate': 'AVG'}},
    # 两个子查询
    {'logic': 'AND', 'conditions': [
        {'field': {'column': 'Total'}, 'operator': 'gt',
         'subquery': {'aggregate': 'AVG', 'field': {'column': 'Total'}}},
        {'field': {'column': 'Total'}, 'operator': 'lt',
         'subquery': {'aggregate': 'MAX', 'field': {'column': 'Total'}}},
    ]},
])
def test_dsl_rejects_unsupported_subquery_shapes(filters):
    payload = {'table': 'Invoice',
               'select': [{'kind': 'column', 'field': {'column': 'InvoiceId'}}],
               'filters': filters}

    with pytest.raises(AppError):
        compile_query_dsl(payload, INVOICE_SCHEMA)


def test_multitable_scalar_subquery_passes_fk_validation():
    plan = plan_join_path(['invoice', 'customer'], SchemaGraph(SCHEMA))
    selected = ['invoice.InvoiceId', 'invoice.Total', 'customer.CustomerId']
    payload = {
        'table': 'invoice',
        'select': [{'kind': 'column', 'field': {'table': 'invoice', 'column': 'InvoiceId'}}],
        'filters': {'field': {'table': 'invoice', 'column': 'Total'}, 'operator': 'gt',
                    'subquery': {'aggregate': 'AVG',
                                 'field': {'table': 'invoice', 'column': 'Total'}}},
    }

    compiled = compile_query_dsl(payload, SCHEMA, join_plan=plan, selected_columns=selected)
    sql = validate_multitable_sql(compiled.sql, plan, SCHEMA, selected)

    assert 'JOIN `customer` AS `t1`' in sql
    assert '(SELECT AVG(Total) FROM invoice)' in sql.replace('`', '')


MULTI_SELECTED = ['invoice.InvoiceId', 'invoice.Total', 'customer.CustomerId',
                  'customer.FirstName', 'customer.LastName']


def _multi_plan():
    return plan_join_path(['invoice', 'customer'], SchemaGraph(SCHEMA))


def _compile_multi(filters, selected=None):
    payload = {
        'table': 'invoice',
        'select': [{'kind': 'column', 'field': {'table': 'invoice', 'column': 'InvoiceId'}}],
        'filters': filters,
        'limit': 20,
    }
    return compile_query_dsl(payload, SCHEMA, join_plan=_multi_plan(),
                             selected_columns=selected or MULTI_SELECTED)


LLM_SHAPED_PAYLOAD = {
    'select': [
        {'kind': 'column', 'field': {'table': 'customer', 'column': 'FirstName'}},
        {'kind': 'column', 'field': {'table': 'customer', 'column': 'LastName'}},
        {'kind': 'aggregate', 'function': 'SUM',
         'field': {'table': 'invoice', 'column': 'Total'}, 'alias': 'total_spent'},
    ],
    'from': {'table': 'customer'},
    'join': [{'type': 'inner'}],
    'filters': {'logic': 'AND', 'conditions': [
        {'field': {'table': 'invoice', 'column': 'Total'}, 'operator': 'gt',
         'subquery': {'aggregate': 'AVG',
                      'field': {'table': 'invoice', 'column': 'Total'}}},
    ]},
    'group_by': [{'table': 'customer', 'column': 'CustomerId'},
                 {'table': 'customer', 'column': 'FirstName'},
                 {'table': 'customer', 'column': 'LastName'}],
    'order_by': [{'field': {'table': 'customer', 'column': 'LastName'}, 'direction': 'ASC'}],
    'limit': 100,
}


def test_llm_shaped_single_condition_group_compiles_with_subquery():
    """Regression for a real DeepSeek output that the strict DSL used to reject."""
    payload = dict(LLM_SHAPED_PAYLOAD)
    compiled = compile_query_dsl(payload, SCHEMA, join_plan=_multi_plan(),
                                 selected_columns=MULTI_SELECTED)

    assert compiled.params == ()
    assert '(SELECT AVG(`Total`) FROM `invoice`)' in compiled.sql
    assert 'JOIN `customer` AS `t1`' in compiled.sql
    assert '(' not in compiled.sql.split('WHERE ', 1)[1].split('(SELECT', 1)[0]
    # The original payload must not be mutated by normalization.
    assert len(payload['filters']['conditions']) == 1
    assert payload['filters']['logic'] == 'AND'
    assert validate_multitable_sql(compiled.sql, _multi_plan(), SCHEMA, MULTI_SELECTED)


def test_single_child_group_without_subquery_is_also_normalized():
    payload = {'table': 'Invoice',
               'select': [{'kind': 'column', 'field': {'column': 'InvoiceId'}}],
               'filters': {'logic': 'OR', 'conditions': [
                   {'field': {'column': 'Total'}, 'operator': 'gt', 'values': [5]}]}}

    compiled = compile_query_dsl(payload, INVOICE_SCHEMA)

    assert 'WHERE `Invoice`.`Total` > ?' in compiled.sql
    assert compiled.params == (5,)


def test_multitable_dsl_count_subquery_is_accepted():
    compiled = _compile_multi({'field': {'table': 'invoice', 'column': 'InvoiceId'},
                               'operator': 'gt', 'subquery': {'aggregate': 'COUNT'}})

    assert '(SELECT COUNT(*) FROM `invoice`)' in compiled.sql
    assert validate_multitable_sql(compiled.sql, _multi_plan(), SCHEMA, MULTI_SELECTED)


def test_multitable_dsl_rejects_unselected_subquery_field():
    with pytest.raises(AppError) as error:
        _compile_multi({'field': {'table': 'invoice', 'column': 'Total'}, 'operator': 'gt',
                        'subquery': {'aggregate': 'AVG',
                                     'field': {'table': 'invoice', 'column': 'BillingCountry'}}})

    assert error.value.code == 'QUERY_DSL_INVALID'


def test_multitable_dsl_rejects_unplanned_subquery_table():
    with pytest.raises(AppError) as error:
        _compile_multi({'field': {'table': 'invoice', 'column': 'Total'}, 'operator': 'gt',
                        'subquery': {'aggregate': 'MAX',
                                     'field': {'table': 'album', 'column': 'Title'}}})

    assert error.value.code == 'QUERY_DSL_INVALID'


def test_multitable_dsl_rejects_two_subqueries():
    leaf = {'field': {'table': 'invoice', 'column': 'Total'}, 'operator': 'gt',
            'subquery': {'aggregate': 'AVG',
                         'field': {'table': 'invoice', 'column': 'Total'}}}
    with pytest.raises(AppError):
        _compile_multi({'logic': 'AND', 'conditions': [
            leaf, {**leaf, 'subquery': {'aggregate': 'MAX',
                                        'field': {'table': 'invoice', 'column': 'Total'}}}]})


JOIN_SQL = ('SELECT `t0`.`InvoiceId` FROM `invoice` AS `t0` '
            'JOIN `customer` AS `t1` ON `t0`.`CustomerId` = `t1`.`CustomerId` ')


@pytest.mark.parametrize('predicate', [
    # correlated subquery references the outer alias
    'WHERE `t0`.`Total` > (SELECT AVG(Total) FROM invoice i WHERE i.CustomerId = `t0`.`CustomerId`)',
    # table outside the approved join plan
    'WHERE `t0`.`Total` > (SELECT AVG(Total) FROM album)',
    # nested subqueries
    'WHERE `t0`.`Total` > (SELECT AVG(Total) FROM invoice WHERE Total > (SELECT MIN(Total) FROM invoice))',
    # join inside the subquery
    'WHERE `t0`.`Total` > (SELECT AVG(i.Total) FROM invoice i JOIN customer c ON i.CustomerId = c.CustomerId)',
    # IN-list subquery
    'WHERE `t0`.`InvoiceId` IN (SELECT InvoiceId FROM invoice)',
])
def test_multitable_sql_rejects_unsafe_subquery_shapes(predicate):
    with pytest.raises(AppError):
        validate_multitable_sql(JOIN_SQL + predicate + ' LIMIT 20',
                                _multi_plan(), SCHEMA, MULTI_SELECTED)


def test_multitable_sql_rejects_scalar_subquery_in_select_list():
    sql = ('SELECT `t0`.`InvoiceId`, (SELECT AVG(Total) FROM invoice) AS average '
           'FROM `invoice` AS `t0` '
           'JOIN `customer` AS `t1` ON `t0`.`CustomerId` = `t1`.`CustomerId` LIMIT 20')

    with pytest.raises(AppError):
        validate_multitable_sql(sql, _multi_plan(), SCHEMA, MULTI_SELECTED)
