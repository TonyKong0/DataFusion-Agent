"""Validate a small query language and compile it to parameterized MySQL SQL."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator
from pydantic import ValidationError

from app.core.errors import AppError
from app.schema.models import SchemaMetadata


Scalar = StrictStr | StrictInt | StrictFloat | StrictBool
Aggregate = Literal['COUNT', 'COUNT_DISTINCT', 'SUM', 'AVG', 'MIN', 'MAX']
FilterOperator = Literal[
    'eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'in', 'not_in', 'between',
    'contains', 'is_null', 'is_not_null',
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class QueryField(StrictModel):
    table: str | None = Field(default=None, min_length=1, max_length=128)
    column: str = Field(min_length=1, max_length=128)


class ScalarSubquery(StrictModel):
    """The only nested-query shape the DSL can express: one aggregate over one table."""

    aggregate: Literal['AVG', 'SUM', 'MIN', 'MAX', 'COUNT']
    field: QueryField | None = None

    @model_validator(mode='after')
    def validate_shape(self) -> ScalarSubquery:
        if self.aggregate != 'COUNT' and self.field is None:
            raise ValueError('scalar subquery aggregates other than COUNT require a field')
        return self



class SelectItem(StrictModel):
    kind: Literal['column', 'aggregate']
    field: QueryField | None = None
    function: Aggregate | None = None
    alias: str | None = Field(default=None, pattern=r'^[A-Za-z][A-Za-z0-9_]{0,63}$')

    @model_validator(mode='after')
    def validate_shape(self) -> SelectItem:
        if self.kind == 'column' and (self.field is None or self.function is not None):
            raise ValueError('column selection requires a field and forbids a function')
        if self.kind == 'aggregate':
            if self.function is None:
                raise ValueError('aggregate selection requires an approved function')
            if self.function != 'COUNT' and self.field is None:
                raise ValueError('aggregate selection requires a field')
            if self.alias is None:
                raise ValueError('aggregate selection requires an output alias')
        return self


class FilterExpression(StrictModel):
    logic: Literal['AND', 'OR'] | None = None
    conditions: list[FilterExpression] = Field(default_factory=list, max_length=10)
    field: QueryField | None = None
    operator: FilterOperator | None = None
    values: list[Scalar] = Field(default_factory=list, max_length=100)
    subquery: ScalarSubquery | None = None

    @model_validator(mode='after')
    def validate_shape(self) -> FilterExpression:
        if self.logic is not None:
            if (self.field is not None or self.operator is not None or self.values
                    or self.subquery is not None or len(self.conditions) < 2):
                raise ValueError('boolean filter groups require at least two child conditions')
            return self
        if self.conditions or self.field is None or self.operator is None:
            raise ValueError('filter leaves require a field and approved operator')
        if self.subquery is not None:
            if self.operator not in {'eq', 'neq', 'gt', 'gte', 'lt', 'lte'}:
                raise ValueError('scalar subqueries only support eq/neq/gt/gte/lt/lte comparisons')
            if self.values:
                raise ValueError('scalar subquery comparisons do not accept literal values')
            return self
        if self.operator in {'is_null', 'is_not_null'}:
            if self.values:
                raise ValueError('null checks do not accept values')
        elif self.operator == 'between':
            if len(self.values) != 2:
                raise ValueError('between requires exactly two values')
        elif self.operator in {'in', 'not_in'}:
            if not self.values:
                raise ValueError('set membership requires at least one value')
        elif len(self.values) != 1:
            raise ValueError('comparison filters require exactly one value')
        if self.operator == 'contains' and not isinstance(self.values[0], str):
            raise ValueError('contains requires a string value')
        if any(isinstance(value, float) and not isfinite(value) for value in self.values):
            raise ValueError('filter values must be finite')
        return self


FilterExpression.model_rebuild()


class SortItem(StrictModel):
    field: str = Field(min_length=1, max_length=256)
    direction: Literal['ASC', 'DESC']


def _count_subqueries(node: FilterExpression | None) -> int:
    if node is None:
        return 0
    return ((1 if node.subquery is not None else 0)
            + sum(_count_subqueries(child) for child in node.conditions))


class QueryDSL(StrictModel):
    table: str = Field(min_length=1, max_length=128)
    select: list[SelectItem] = Field(min_length=1, max_length=16)
    filters: FilterExpression | None = None
    group_by: list[QueryField | StrictStr] = Field(default_factory=list, max_length=16)
    order_by: list[SortItem] = Field(default_factory=list, max_length=16)
    limit: int = Field(default=100, ge=1, le=10000)

    @model_validator(mode='after')
    def validate_shape(self) -> QueryDSL:
        aliases = [item.alias.casefold() for item in self.select if item.alias]
        if len(aliases) != len(set(aliases)):
            raise ValueError('output aliases must be unique')
        group_fields = [((field.table.casefold() if field.table else None), field.column.casefold())
                        if isinstance(field, QueryField) else (None, field.casefold())
                        for field in self.group_by]
        if len(group_fields) != len(set(group_fields)):
            raise ValueError('grouping fields must be unique')
        if _count_subqueries(self.filters) > 1:
            raise ValueError('at most one scalar subquery is allowed per query')
        return self


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    params: tuple
    table: str


def _invalid(diagnostic: str | None = None) -> AppError:
    error = AppError('QUERY_DSL_INVALID', '结构化查询不符合当前 Schema 或安全规则', 422)
    if diagnostic:
        error.diagnostic = diagnostic[:1000]
    return error


def _schema_index(schema: list[dict] | SchemaMetadata) -> dict[str, tuple[str, dict[str, str]]]:
    if isinstance(schema, SchemaMetadata):
        tables = [(table.table_name, [column.name for column in table.columns])
                  for table in schema.tables]
    elif isinstance(schema, list):
        tables = [(table.get('table'), [column.get('name') for column in table.get('columns', [])])
                  for table in schema if isinstance(table, dict)]
    else:
        raise _invalid()
    result = {}
    for name, columns in tables:
        if not isinstance(name, str) or not name:
            raise _invalid()
        indexed_columns = {column.casefold(): column for column in columns
                           if isinstance(column, str) and column}
        result[name.casefold()] = (name, indexed_columns)
    return result


def _quote(identifier: str) -> str:
    return '`' + identifier.replace('`', '``') + '`'


def _field_key(table: str, column: str) -> tuple[str, str]:
    return table.casefold(), column.casefold()


def _collapse_single_condition_groups(node):
    """Fold a one-child AND/OR group into its leaf (a common LLM output shape).

    FilterExpression requires at least two children for a boolean group. Models
    routinely emit ``{"logic":"AND","conditions":[leaf]}`` anyway; normalizing it
    here preserves the strict model without rejecting an unambiguous query.
    """
    if not isinstance(node, dict):
        return node
    result = dict(node)
    conditions = result.get('conditions')
    if isinstance(conditions, list):
        children = [_collapse_single_condition_groups(child) for child in conditions]
        result['conditions'] = children
        if result.get('logic') and len(children) == 1:
            return children[0]
    return result


def _normalize_query_payload(payload: dict, planned_tables: list[str],
                             join_plan: dict | None) -> dict:
    """Normalize only unambiguous structural variants; trusted planning owns all joins."""
    normalized = dict(payload)
    source = normalized.pop('from', None)
    normalized.pop('join', None)
    normalized.pop('joins', None)
    if 'table' not in normalized:
        if join_plan is not None:
            normalized['table'] = planned_tables[0]
        elif isinstance(source, dict) and isinstance(source.get('table'), str):
            normalized['table'] = source['table']
    elif join_plan is not None:
        # A generated FROM may name the measure's source table. The planner's
        # root remains authoritative; never let model output choose join order.
        normalized['table'] = planned_tables[0]
    filters = normalized.get('filters')
    if filters is None and isinstance(normalized.get('where'), (dict, list)):
        filters = normalized['where']
        normalized['filters'] = filters
    normalized.pop('where', None)
    if isinstance(filters, list):
        if len(filters) == 1:
            normalized['filters'] = filters[0]
        elif len(filters) > 1:
            normalized['filters'] = {'logic': 'AND', 'conditions': filters}
    if isinstance(normalized.get('filters'), dict):
        normalized['filters'] = _collapse_single_condition_groups(dict(normalized['filters']))
    order_by = normalized.get('order_by')
    if isinstance(order_by, list):
        aggregate_aliases = {}
        for selected in normalized.get('select', []):
            if (not isinstance(selected, dict) or selected.get('kind') != 'aggregate'
                    or not isinstance(selected.get('field'), dict)
                    or not isinstance(selected.get('alias'), str)):
                continue
            field = selected['field']
            if isinstance(field.get('table'), str) and isinstance(field.get('column'), str):
                aggregate_aliases[
                    f"{field['table']}.{field['column']}".casefold()
                ] = selected['alias']
        normalized['order_by'] = [
            {'field': aggregate_aliases.get(
                f"{item['field']['table']}.{item['field']['column']}".casefold(),
                f"{item['field']['table']}.{item['field']['column']}"),
             'direction': item.get('direction')}
            if isinstance(item, dict) and isinstance(item.get('field'), dict)
            and isinstance(item['field'].get('table'), str)
            and isinstance(item['field'].get('column'), str)
            else {'field': item.get('field'), 'direction': item.get('direction')}
            if isinstance(item, dict)
            else item
            for item in order_by
        ]
    return normalized


_RANKING_INTENT = re.compile(r'最高|最多|最大|最小|最低|最少|最贵|最便宜|排名第一|第一名|销量最高|销量最大|\btop\b', re.IGNORECASE)
_RANKING_ASC = re.compile(r'最低|最少|最小|最便宜', re.IGNORECASE)
_EXPLICIT_RANK_LIMIT = re.compile(r'(?:前\s*|top\s*)(\d{1,3})', re.IGNORECASE)
_GROUPING_INTENT = re.compile(r'每个|每位|每种|每张|各|分别')


def normalize_ranking_query(payload: dict, question: str) -> dict:
    """Make explicit ranking intent deterministic in the structured query."""
    normalized = dict(payload)
    if not _RANKING_INTENT.search(question):
        if _GROUPING_INTENT.search(question) and isinstance(normalized.get('select'), list):
            dimensions = [item['field'] for item in normalized['select']
                          if isinstance(item, dict) and item.get('kind') == 'column'
                          and isinstance(item.get('field'), dict)]
            if dimensions:
                normalized['order_by'] = [
                    {'field': field, 'direction': 'ASC'} for field in dimensions
                ]
        return normalized
    selected = normalized.get('select')
    if not isinstance(selected, list):
        return normalized
    aggregates = [item for item in selected if isinstance(item, dict)
                  and item.get('kind') == 'aggregate'
                  and isinstance(item.get('alias'), str)]
    if len(aggregates) != 1:
        return normalized
    aggregate = aggregates[0]
    alias = aggregate['alias']
    direction = 'ASC' if _RANKING_ASC.search(question) else 'DESC'
    matches = _EXPLICIT_RANK_LIMIT.search(question)
    limit = int(matches.group(1)) if matches else 1
    if limit > 0:
        current = normalized.get('limit', 100)
        normalized['limit'] = min(current, limit) if isinstance(current, int) else limit
    order_by = normalized.get('order_by')
    stable_order = []
    if isinstance(order_by, list):
        for item in order_by:
            if not isinstance(item, dict):
                stable_order.append(item)
                continue
            field = item.get('field')
            if field == alias or (isinstance(field, dict) and aggregate.get('field') == field):
                continue
            stable_order.append(item)
    normalized['order_by'] = [{'field': alias, 'direction': direction}, *stable_order]
    return normalized


def _validate_payload_bounds(payload: dict) -> None:
    stack = [(payload, 0)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if depth > 16 or nodes > 512:
            raise _invalid('Query DSL exceeds structural limits')
        if isinstance(value, dict):
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)


def compile_query_dsl(payload: dict | QueryDSL, schema: list[dict] | SchemaMetadata, *,
                      join_plan: dict | None = None, selected_columns: list[str] | None = None,
                      max_rows: int = 100) -> CompiledQuery:
    """Compile validated fields and literal values without accepting model-authored SQL."""
    try:
        planned_tables = list(join_plan['join_tables']) if join_plan else []
        if isinstance(payload, QueryDSL):
            query = payload
        else:
            if not isinstance(payload, dict):
                raise _invalid()
            _validate_payload_bounds(payload)
            normalized_payload = _normalize_query_payload(payload, planned_tables, join_plan)
            query = QueryDSL.model_validate(normalized_payload)
        aggregate_present = any(item.kind == 'aggregate' for item in query.select)
        if aggregate_present:
            group_keys = {
                ((field.table.casefold() if field.table else None), field.column.casefold())
                if isinstance(field, QueryField) else (None, field.casefold())
                for field in query.group_by
            }
            appended_fields = []
            for item in query.select:
                if item.kind != 'column' or item.field is None:
                    continue
                key = (item.field.table.casefold() if item.field.table else None,
                       item.field.column.casefold())
                if key not in group_keys:
                    appended_fields.append(item.field)
                    group_keys.add(key)
            if appended_fields:
                query.group_by.extend(appended_fields)
        schema_tables = _schema_index(schema)
        if join_plan is None:
            planned_tables = [query.table]
        table_keys = [name.casefold() for name in planned_tables]
        if not table_keys or len(set(table_keys)) != len(table_keys):
            raise _invalid()
        if any(name not in schema_tables for name in table_keys):
            raise _invalid()
        base_key = table_keys[0]
        if query.table.casefold() != base_key:
            raise _invalid()
        base_table = schema_tables[base_key][0]
        max_rows = int(max_rows)
        if max_rows < 1:
            raise _invalid()
        allowed = None
        if join_plan is not None:
            allowed = set()
            for item in selected_columns or []:
                table_name, separator, column_name = item.partition('.')
                if separator and table_name and column_name:
                    allowed.add((table_name.casefold(), column_name.casefold()))
        aliases = {table_key: f't{index}' for index, table_key in enumerate(table_keys)}
        params: list[object] = []

        def resolve_field(field: QueryField) -> tuple[str, str]:
            column_key = field.column.casefold()
            if field.table is not None:
                candidates = [field.table.casefold()]
            else:
                candidates = [table_key for table_key in table_keys
                              if column_key in schema_tables[table_key][1]]
            matches = [table_key for table_key in candidates
                       if table_key in table_keys and column_key in schema_tables[table_key][1]]
            if len(matches) != 1:
                raise _invalid()
            table_key = matches[0]
            table_name, columns = schema_tables[table_key]
            column_name = columns[column_key]
            if allowed is not None and (table_key, column_key) not in allowed:
                raise _invalid()
            return table_name, column_name

        def field_sql(field: QueryField) -> tuple[str, tuple[str, str]]:
            table_name, column_name = resolve_field(field)
            table_key = table_name.casefold()
            qualifier = aliases[table_key] if join_plan is not None else table_name
            return f'{_quote(qualifier)}.{_quote(column_name)}', _field_key(table_name, column_name)

        select_parts = []
        output_aliases = set()
        selected_field_keys = set()
        aggregate_present = False
        nonaggregate_field_keys = []
        for item in query.select:
            if item.kind == 'column':
                expression, field_key = field_sql(item.field)
                selected_field_keys.add(field_key)
                nonaggregate_field_keys.append(field_key)
            elif item.function == 'COUNT' and item.field is None:
                expression = 'COUNT(*)'
                aggregate_present = True
            else:
                aggregate_present = True
                function = 'COUNT' if item.function == 'COUNT_DISTINCT' else item.function
                if item.field is None:
                    raise _invalid()
                field_expression, _ = field_sql(item.field)
                if item.function == 'COUNT_DISTINCT':
                    expression = f'COUNT(DISTINCT {field_expression})'
                else:
                    expression = f'{function}({field_expression})'
            if item.alias:
                output_aliases.add(item.alias.casefold())
                expression += f' AS {_quote(item.alias)}'
            select_parts.append(expression)

        group_parts = []
        group_field_keys = set()
        for group_field in query.group_by:
            field = group_field if isinstance(group_field, QueryField) else QueryField(column=group_field)
            expression, field_key = field_sql(field)
            group_parts.append(expression)
            group_field_keys.add(field_key)
        if aggregate_present and any(key not in group_field_keys for key in nonaggregate_field_keys):
            raise _invalid()

        def compile_scalar_subquery(spec: ScalarSubquery) -> str:
            if spec.field is None:
                return f'(SELECT COUNT(*) FROM {_quote(base_table)})'
            table_name, column_name = resolve_field(spec.field)
            return (f'(SELECT {spec.aggregate}({_quote(column_name)}) '
                    f'FROM {_quote(table_name)})')

        def compile_filter(node: FilterExpression) -> str:
            if node.logic is not None:
                return '(' + f' {node.logic} '.join(compile_filter(child) for child in node.conditions) + ')'
            expression, _ = field_sql(node.field)
            operator = node.operator
            if node.subquery is not None:
                sql_operator = {
                    'eq': '=', 'neq': '<>', 'gt': '>', 'gte': '>=', 'lt': '<', 'lte': '<=',
                }[operator]
                return f'{expression} {sql_operator} {compile_scalar_subquery(node.subquery)}'
            if operator == 'is_null':
                return f'{expression} IS NULL'
            if operator == 'is_not_null':
                return f'{expression} IS NOT NULL'
            if operator in {'in', 'not_in'}:
                params.extend(node.values)
                placeholders = ', '.join('?' for _ in node.values)
                sql_operator = 'IN' if operator == 'in' else 'NOT IN'
                return f'{expression} {sql_operator} ({placeholders})'
            if operator == 'between':
                params.extend(node.values)
                return f'{expression} BETWEEN ? AND ?'
            if operator == 'contains':
                value = node.values[0]
                escaped = value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
                params.append(f'%{escaped}%')
                return f"{expression} LIKE ? ESCAPE '\\\\'"
            params.append(node.values[0])
            sql_operator = {
                'eq': '=', 'neq': '<>', 'gt': '>', 'gte': '>=', 'lt': '<', 'lte': '<=',
            }[operator]
            return f'{expression} {sql_operator} ?'

        parts = [f"SELECT {', '.join(select_parts)}"]
        if join_plan is not None:
            parts.append(f'FROM {_quote(base_table)} AS {_quote(aliases[base_key])}')
            for edge in join_plan['join_path']:
                left_key = edge['left_table'].casefold()
                right_key = edge['right_table'].casefold()
                if left_key not in aliases or right_key not in aliases:
                    raise _invalid()
                left_table, left_columns = schema_tables[left_key]
                right_table, right_columns = schema_tables[right_key]
                left_column = left_columns.get(edge['left_column'].casefold())
                right_column = right_columns.get(edge['right_column'].casefold())
                if not left_column or not right_column:
                    raise _invalid()
                parts.append(
                    f'JOIN {_quote(right_table)} AS {_quote(aliases[right_key])} ON '
                    f'{_quote(aliases[left_key])}.{_quote(left_column)} = '
                    f'{_quote(aliases[right_key])}.{_quote(right_column)}'
                )
        else:
            parts.append(f'FROM {_quote(base_table)}')
        if query.filters is not None:
            parts.append('WHERE ' + compile_filter(query.filters))
        if group_parts:
            parts.append('GROUP BY ' + ', '.join(group_parts))

        order_parts = []
        for item in query.order_by:
            if item.field.casefold() in output_aliases:
                expression = _quote(item.field)
            else:
                table_name, separator, column_name = item.field.partition('.')
                field = QueryField(table=table_name, column=column_name) if separator else QueryField(column=item.field)
                expression, field_key = field_sql(field)
                if field_key not in selected_field_keys | group_field_keys:
                    raise _invalid()
            order_parts.append(f'{expression} {item.direction}')
        if order_parts:
            parts.append('ORDER BY ' + ', '.join(order_parts))
        parts.append(f'LIMIT {min(query.limit, max_rows)}')
        compiled_sql = ' '.join(parts)
        if len(compiled_sql) > 12000:
            raise _invalid('Compiled SQL exceeds the validation length limit')
        return CompiledQuery(compiled_sql, tuple(params), base_table)
    except AppError:
        raise
    except ValidationError as error:
        issues = '; '.join(
            f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}"
            for issue in error.errors()[:8]
        )
        raise _invalid(issues) from None
    except (KeyError, TypeError, ValueError) as error:
        raise _invalid(f'{type(error).__name__}: {error}') from None


def render_pymysql_sql(sql: str) -> str:
    """Translate SQLGlot's `?` placeholders without altering quoted identifiers or text."""
    output = []
    quote = None
    index = 0
    while index < len(sql):
        char = sql[index]
        if quote is not None:
            output.append(char)
            if char == '\\' and quote != '`' and index + 1 < len(sql):
                index += 1
                output.append(sql[index])
            elif char == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    index += 1
                    output.append(sql[index])
                else:
                    quote = None
        elif char in {"'", '"', '`'}:
            quote = char
            output.append(char)
        elif char == '?':
            output.append('%s')
        else:
            output.append(char)
        index += 1
    return ''.join(output)
