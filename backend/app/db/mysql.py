from contextlib import contextmanager
from collections.abc import Iterator
import pymysql
from app.core.config import get_settings
from app.core.errors import AppError


@contextmanager
def connection() -> Iterator[pymysql.Connection]:
    settings = get_settings()
    if not settings.mysql_user:
        raise AppError('MYSQL_NOT_CONFIGURED', '请配置本地 MySQL 连接信息', 503)
    try:
        conn = pymysql.connect(host=settings.mysql_host, port=settings.mysql_port,
            user=settings.mysql_user, password=settings.mysql_password.get_secret_value(),
            database=settings.mysql_database, charset='utf8mb4',
            connect_timeout=5, read_timeout=15, write_timeout=5, autocommit=False)
    except pymysql.MySQLError:
        raise AppError('MYSQL_CONNECTION_FAILED', 'MySQL 连接失败，请检查服务、配置和数据库', 503) from None
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def database_status() -> dict:
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s AND table_type=%s',
                       (get_settings().mysql_database, 'BASE TABLE'))
        count = cursor.fetchone()[0]
    return {'connected': True, 'database': get_settings().mysql_database, 'tables': count}
