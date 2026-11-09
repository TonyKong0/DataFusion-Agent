from app.core.config import get_settings
from app.db.mysql import connection


def load_schema() -> list[dict]:
    """Load live tables, columns, primary keys and foreign keys from MySQL metadata."""
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute('''SELECT c.TABLE_NAME, c.COLUMN_NAME, c.COLUMN_TYPE, c.COLUMN_KEY,
            c.IS_NULLABLE FROM information_schema.COLUMNS c
            JOIN information_schema.TABLES t ON c.TABLE_SCHEMA=t.TABLE_SCHEMA AND c.TABLE_NAME=t.TABLE_NAME
            WHERE c.TABLE_SCHEMA=%s AND t.TABLE_TYPE='BASE TABLE'
            ORDER BY c.TABLE_NAME,c.ORDINAL_POSITION''', (get_settings().mysql_database,))
        columns = cursor.fetchall()
        cursor.execute('''SELECT TABLE_NAME,COLUMN_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA=%s AND REFERENCED_TABLE_NAME IS NOT NULL''', (get_settings().mysql_database,))
        foreign_keys = cursor.fetchall()
    tables = {}
    for table, column, dtype, key, nullable in columns:
        tables.setdefault(table, {'table': table, 'columns': [], 'foreign_keys': []})['columns'].append(
            {'name': column, 'type': dtype, 'primary_key': key == 'PRI', 'nullable': nullable == 'YES'})
    for table, column, ref_table, ref_column in foreign_keys:
        tables[table]['foreign_keys'].append({'column': column, 'references_table': ref_table, 'references_column': ref_column})
    return list(tables.values())
