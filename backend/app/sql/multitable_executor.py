"""Read-only execution with bounded, sanitized feedback for SQL repair."""

import pymysql

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.mysql import connection
from app.services.sql_executor import serialize


_FEEDBACK = {1054: 'Unknown column', 1064: 'Syntax error', 1052: 'Ambiguous column'}


def execute_multitable_sql(sql: str, params: tuple | list = ()) -> tuple[list[str], list[list]]:
    try:
        with connection() as conn, conn.cursor() as cursor:
            cursor.execute('SET SESSION MAX_EXECUTION_TIME=5000')
            cursor.execute('START TRANSACTION READ ONLY')
            if params:
                cursor.execute(sql, tuple(params))
            else:
                cursor.execute(sql)
            columns = [item[0] for item in cursor.description]
            rows = [[serialize(value) for value in row]
                    for row in cursor.fetchmany(get_settings().max_sql_rows)]
            return columns, rows
    except pymysql.MySQLError as error:
        code = error.args[0] if error.args else None
        failure = AppError('SQL_EXECUTION_FAILED', '多表查询执行失败', 422)
        failure.diagnostic = _FEEDBACK.get(code, 'Database execution error')
        raise failure from None
