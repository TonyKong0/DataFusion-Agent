"""Fail-closed validation for SELECT queries over an approved FK join plan."""

import re

import sqlglot
from sqlglot import exp

from app.core.config import get_settings
from app.core.errors import AppError
from app.schema.models import SchemaMetadata
from app.services.sql_validator import find_unsafe_function
from app.sql.scalar_subquery import ScalarSubqueryViolation, validate_scalar_subqueries


def _reject(message: str = '多表 SQL 未通过安全校验') -> None:
    raise AppError('UNSAFE_MULTI_SQL', message, 422)


def _reject_parent_fanout_aggregates(tree: exp.Select, tables: list[exp.Table],
                                    metadata: SchemaMetadata, aliases: dict[str, str]) -> None:
    """Reject aggregates over parent rows that a joined one-to-many child can repeat."""
    if len(tables) < 2:
        return
    joined_tables = {table.name.lower() for table in tables}
    schema_tables = {table.table_name.lower(): table for table in metadata.tables}
    child_parent_pairs = {
        (table.table_name.lower(), key.references_table.lower())
        for table in metadata.tables for key in table.foreign_keys
    }

    for aggregate in tree.find_all(exp.AggFunc):
        if aggregate.find_ancestor(exp.Subquery):
            continue
        name = aggregate.sql_name().upper()
        if name not in {'SUM', 'AVG', 'MIN', 'MAX', 'COUNT'}:
            continue
        columns = list(aggregate.find_all(exp.Column))
        if not columns:
            continue
        source_tables = set()
        for column in columns:
            source_table = aliases.get(column.table.lower()) if column.table else None
            if source_table is None:
                matches = []
                for table_name in joined_tables:
                    table = schema_tables.get(table_name)
                    if table and any(item.name.lower() == column.name.lower() for item in table.columns):
                        matches.append(table_name)
                source_table = matches[0] if len(matches) == 1 else None
            if source_table:
                source_tables.add(source_table)
        if not source_tables:
            continue

        is_distinct_count = (name == 'COUNT' and aggregate.find(exp.Distinct) is not None
                             and len(source_tables) == 1)
        if is_distinct_count:
            continue
        if any(child in joined_tables and parent in source_tables
               for child, parent in child_parent_pairs):
            _reject('查询可能因明细 JOIN 产生重复聚合，请改用 COUNT(DISTINCT 主键) 或仅聚合明细表')


def validate_multitable_sql(sql: str, plan: dict, metadata: SchemaMetadata,
                            selected_columns: list[str]) -> str:
    if not isinstance(sql, str) or len(sql) > 12000 or re.search(r'--|/\*|#|@|\x00', sql):
        _reject()
    try:
        statements = sqlglot.parse(sql, read='mysql')
    except sqlglot.errors.ParseError:
        _reject('SQL 语法错误')
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        _reject('只允许一条 SELECT')
    tree = statements[0]
    if tree.args.get('with_'):
        _reject('禁止 CTE')
    if tree.find(exp.Union):
        _reject('禁止 UNION')
    if any(tree.args.get(key) for key in ('into', 'locks', 'offset')):
        _reject()
    planned_tables = [name.lower() for name in plan['join_tables']]
    actual_schema = {table.table_name.lower(): {column.name.lower() for column in table.columns}
                     for table in metadata.tables}
    try:
        validate_scalar_subqueries(tree, set(planned_tables), actual_schema)
    except ScalarSubqueryViolation as error:
        _reject(str(error))
    base = tree.args.get('from_')
    if not base or not isinstance(base.this, exp.Table) or base.this.db or base.this.catalog:
        _reject('缺少合法的主表')
    if base.this.name.lower() != planned_tables[0]:
        _reject('主表不符合 JOIN 规划')
    joins = tree.args.get('joins') or []
    if len(joins) != len(plan['join_path']):
        _reject('JOIN 数量不符合规划')
    aliases = {base.this.alias_or_name.lower(): planned_tables[0]}
    seen = {planned_tables[0]}
    for index, join in enumerate(joins):
        expected = plan['join_path'][index]
        table = join.this
        if not isinstance(table, exp.Table) or table.db or table.catalog or (
                table.name.lower() != expected['right_table'].lower()):
            _reject('JOIN 表不符合真实外键路径')
        if join.args.get('side') or join.args.get('kind') not in (None, 'INNER') or join.args.get('using'):
            _reject('只允许规划中的 INNER JOIN')
        alias = table.alias_or_name.lower()
        if alias in aliases:
            _reject('重复的表别名')
        aliases[alias] = table.name.lower()
        seen.add(table.name.lower())
        predicate = join.args.get('on')
        if not isinstance(predicate, exp.EQ) or not isinstance(predicate.left, exp.Column) or (
                not isinstance(predicate.right, exp.Column)):
            _reject('JOIN 条件必须是单一真实外键等式')

        def endpoint(column):
            table_name = aliases.get(column.table.lower()) if column.table else None
            return (table_name, column.name.lower())

        actual = {endpoint(predicate.left), endpoint(predicate.right)}
        required = {(expected['left_table'].lower(), expected['left_column'].lower()),
                    (expected['right_table'].lower(), expected['right_column'].lower())}
        if actual != required:
            _reject('JOIN 条件不符合真实外键')
    if seen != set(planned_tables):
        _reject('SQL 表集合不符合规划')

    _reject_parent_fanout_aggregates(tree, joins and [base.this, *(join.this for join in joins)] or [base.this],
                                     metadata, aliases)

    allowed = {(table.lower(), column.lower()) for name in selected_columns
               for table, _, column in [name.partition('.')] if table and column}
    allowed.update((edge[key].lower(), edge[key.replace('table', 'column')].lower())
                   for edge in plan['join_path'] for key in ('left_table', 'right_table'))
    output_aliases = {item.alias.lower() for item in tree.expressions if item.alias}
    for column in tree.find_all(exp.Column):
        if column.find_ancestor(exp.Subquery):
            # 子查询内部列已由 scalar_subquery 规则单独校验
            continue
        if isinstance(column.this, exp.Star):
            _reject('多表查询不允许 SELECT *')
        if not column.table and column.name.lower() in output_aliases and isinstance(
                column.parent, (exp.Ordered, exp.Group)):
            continue
        if column.table:
            resolved = aliases.get(column.table.lower())
        else:
            matches = [table for table in planned_tables if column.name.lower() in actual_schema.get(table, set())]
            resolved = matches[0] if len(matches) == 1 else None
        if not resolved or column.name.lower() not in actual_schema.get(resolved, set()) or (
                resolved, column.name.lower()) not in allowed:
            _reject('SQL 使用了未选定或不存在的字段')
    if find_unsafe_function(tree) is not None:
        _reject('不允许的 SQL 函数')
    limit = tree.args.get('limit')
    max_rows = get_settings().max_sql_rows
    if limit:
        value = limit.expression
        if not isinstance(value, exp.Literal) or not value.is_int or int(value.this) <= 0:
            _reject('LIMIT 必须是正整数')
        tree = tree.limit(min(int(value.this), max_rows))
    else:
        tree = tree.limit(max_rows)
    return tree.sql(dialect='mysql')
