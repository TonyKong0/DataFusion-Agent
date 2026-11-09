"""Import the official Chinook script only into an empty database."""
import re
import sys
from pathlib import Path
import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    if not settings.mysql_user:
        raise SystemExit('请先配置 backend/.env 中的 MySQL 连接信息')
    database = settings.mysql_database
    if not re.fullmatch(r'[A-Za-z0-9_]+', database):
        raise SystemExit('数据库名称仅允许字母、数字和下划线')
    conn = pymysql.connect(host=settings.mysql_host, port=settings.mysql_port,
        user=settings.mysql_user, password=settings.mysql_password.get_secret_value(),
        charset='utf8mb4', autocommit=True, connect_timeout=5)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s', (database,))
            if cursor.fetchone()[0]:
                raise SystemExit('目标库非空，已拒绝导入；不会覆盖或删除现有数据')
            cursor.execute(f'CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
            cursor.execute(f'USE `{database}`')
            script = (Path(__file__).resolve().parents[2] / 'database/Chinook_MySql.sql').read_text(encoding='utf-8-sig')
            script = re.sub(r'/\*.*?\*/', '', script, flags=re.S)
            # The upstream script contains database DROP/CREATE/USE statements. Never execute them.
            for statement in script.split(';'):
                statement = statement.strip()
                if not statement or re.match(r'^(DROP\s+DATABASE|CREATE\s+DATABASE|USE\s)', statement, re.I):
                    continue
                cursor.execute(statement)
            cursor.execute('SHOW TABLES')
            print(f'Chinook 导入完成，共 {len(cursor.fetchall())} 张表')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
