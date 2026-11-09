"""Fail-closed rules for the only nested-query shape this project allows.

A query may contain at most one single-level, non-correlated scalar aggregate
subquery, and only as one side of a comparison inside WHERE/HAVING. Everything
else stays forbidden: CTEs, UNION, FROM/JOIN subqueries, correlated subqueries,
nested subqueries, IN/EXISTS list subqueries and writes.
"""

from sqlglot import exp

MAX_SUBQUERIES = 1
COMPARISONS = (exp.GT, exp.GTE, exp.LT, exp.LTE, exp.EQ, exp.NEQ)
AGGREGATES = (exp.Avg, exp.Sum, exp.Min, exp.Max, exp.Count)


class ScalarSubqueryViolation(Exception):
    """Raised with a user-facing reason when the subquery shape is not allowed."""


def _fail(message: str) -> None:
    raise ScalarSubqueryViolation(message)


def validate_scalar_subqueries(tree: exp.Expression, allowed_tables: set[str],
                               schema: dict[str, set[str]]) -> None:
    """Validate every subquery node against the controlled shape, or raise."""
    subqueries = list(tree.find_all(exp.Subquery))
    if not subqueries:
        return
    if len(subqueries) > MAX_SUBQUERIES:
        _fail('最多允许一个标量子查询')
    for subquery in subqueries:
        _validate_one(subquery, allowed_tables, schema)


def _validate_one(subquery: exp.Subquery, allowed_tables: set[str],
                  schema: dict[str, set[str]]) -> None:
    if not isinstance(subquery.parent, COMPARISONS):
        _fail('子查询只能作为 WHERE/HAVING 比较中的标量值')
    if subquery.find_ancestor(exp.Where) is None and subquery.find_ancestor(exp.Having) is None:
        _fail('子查询只能出现在 WHERE 或 HAVING 中')

    inner = subquery.this
    if not isinstance(inner, exp.Select):
        _fail('子查询必须是单条 SELECT')
    if inner.args.get('with_') or inner.find(exp.Subquery):
        _fail('禁止多层嵌套子查询')
    if inner.find(exp.Join) or inner.find(exp.Union):
        _fail('子查询禁止 JOIN 与 UNION')
    if any(inner.args.get(key) for key in ('group', 'having', 'limit', 'offset')):
        _fail('标量子查询不允许 GROUP BY、HAVING 或 LIMIT')

    tables = list(inner.find_all(exp.Table))
    if len(tables) != 1 or tables[0].db or tables[0].catalog:
        _fail('子查询必须是单表')
    table = tables[0]
    table_name = table.name.lower()
    if table_name not in allowed_tables:
        _fail('子查询使用了未规划的表')

    expressions = list(inner.expressions)
    if len(expressions) != 1:
        _fail('标量子查询必须只返回一个值')
    value = expressions[0].this if isinstance(expressions[0], exp.Alias) else expressions[0]
    if not isinstance(value, AGGREGATES):
        _fail('标量子查询必须只返回一个聚合值')

    known_columns = schema.get(table_name, set())
    inner_alias = table.alias_or_name.lower()
    for column in inner.find_all(exp.Column):
        if isinstance(column.this, exp.Star):
            _fail('子查询不允许 SELECT *')
        if column.table and column.table.lower() != inner_alias:
            _fail('禁止相关子查询：子查询不能引用外层字段')
        if column.name.lower() not in known_columns:
            _fail('子查询使用了不存在的字段')
