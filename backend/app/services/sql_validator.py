import re
import sqlglot
from sqlglot import exp
from app.core.config import get_settings
from app.core.errors import AppError
from app.sql.scalar_subquery import ScalarSubqueryViolation, validate_scalar_subqueries

SAFE_FUNCTIONS = {'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'ROUND', 'COALESCE', 'LOWER', 'UPPER',
                  'LENGTH', 'CHAR_LENGTH', 'ABS', 'YEAR', 'MONTH', 'DAY', 'DATE', 'CAST', 'CONCAT'}


def find_unsafe_function(tree: exp.Expression) -> exp.Func | None:
    """Return the first unapproved SQL function, ignoring non-callable AST nodes."""
    for function in tree.find_all(exp.Func):
        # Boolean operators inherit from Func in SQLGlot, but are SQL operators.
        if isinstance(function, (exp.And, exp.Or)):
            continue
        # YEAR(date_column) contains an implicit SQLGlot date coercion. The same
        # node with source metadata came from an explicit, unlisted function call.
        if isinstance(function, exp.TsOrDsToDate):
            if function.meta:
                return function
            continue
        name = function.name.upper() if isinstance(function, exp.Anonymous) else function.sql_name().upper()
        if name not in SAFE_FUNCTIONS:
            return function
    return None


def reject(message: str | None = None) -> None:
    raise AppError('UNSAFE_SQL', message or
                   '仅允许已知字段的单表 SELECT 查询，禁止 JOIN、CTE、多层或相关子查询、写操作及危险函数')


def validate_sql(sql: str, selected_table: str, schema: list[dict]) -> tuple[str, str]:
    """Validate the parsed AST, then bound rows before executing anything."""
    if not isinstance(sql, str) or len(sql) > 12000 or re.search(r'--|/\*|#|@|\x00', sql):
        reject()
    try:
        statements = sqlglot.parse(sql, read='mysql')
    except sqlglot.errors.ParseError:
        reject()
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        reject()
    tree = statements[0]
    if tree.args.get('with_') or tree.find(exp.Join) or tree.find(exp.Union):
        reject()
    if any(tree.args.get(key) for key in ('into', 'locks', 'offset')):
        reject()
    base = tree.args.get('from_')
    if not base or not isinstance(base.this, exp.Table) or base.this.db or base.this.catalog:
        reject()
    metadata = next((t for t in schema if t['table'].lower() == base.this.name.lower()), None)
    if not metadata or selected_table.lower() != metadata['table'].lower():
        reject()
    known_columns = {c['name'].lower() for c in metadata['columns']}
    try:
        validate_scalar_subqueries(tree, {metadata['table'].lower()},
                                   {metadata['table'].lower(): known_columns})
    except ScalarSubqueryViolation as error:
        reject(str(error))
    aliases = {e.alias.lower() for e in tree.expressions if e.alias}
    table_names = {base.this.name.lower(), base.this.alias_or_name.lower()}
    for column in tree.find_all(exp.Column):
        if column.find_ancestor(exp.Subquery):
            # 子查询内部列已由 scalar_subquery 规则单独校验
            continue
        if column.table and column.table.lower() not in table_names:
            reject()
        if isinstance(column.this, exp.Star):
            continue
        if column.name.lower() not in known_columns:
            # SQL permits output aliases only in ORDER BY and GROUP BY.
            parent = column.parent
            allowed_alias = column.name.lower() in aliases and (
                isinstance(parent, exp.Ordered) or isinstance(parent, exp.Group))
            if not allowed_alias:
                reject()
    if find_unsafe_function(tree) is not None:
        reject()
    base.this.set('this', exp.to_identifier(metadata['table']))
    max_rows = get_settings().max_sql_rows
    limit = tree.args.get('limit')
    if limit:
        value = limit.expression
        if not isinstance(value, exp.Literal) or not value.is_int:
            reject()
        rows = int(value.this)
        if rows <= 0:
            reject()
        tree = tree.limit(min(rows, max_rows))
    else:
        tree = tree.limit(max_rows)
    return tree.sql(dialect='mysql'), metadata['table']
