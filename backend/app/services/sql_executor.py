from datetime import date, datetime
from decimal import Decimal
import pymysql
from app.core.errors import AppError
from app.core.config import get_settings
from app.db.mysql import connection


def serialize(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return value


def execute_sql(sql: str, params: tuple | list = ()) -> tuple[list[str], list[list]]:
    """Execute validated SQL inside a read-only transaction with server timeout."""
    try:
        with connection() as conn, conn.cursor() as cursor:
            cursor.execute('SET SESSION MAX_EXECUTION_TIME=5000')
            cursor.execute('START TRANSACTION READ ONLY')
            if params:
                cursor.execute(sql, tuple(params))
            else:
                cursor.execute(sql)
            columns = [item[0] for item in cursor.description]
            rows = [[serialize(value) for value in row] for row in cursor.fetchmany(get_settings().max_sql_rows)]
            return columns, rows
    except pymysql.MySQLError:
        raise AppError('SQL_EXECUTION_FAILED', 'SQL 执行失败，请检查表结构和查询条件', 422) from None
