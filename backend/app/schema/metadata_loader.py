"""Read table definitions from information_schema; never infer schema names."""

from app.core.config import get_settings
from app.db.mysql import connection
from app.schema.models import ColumnMetadata, ForeignKeyMetadata, SchemaMetadata, TableMetadata


def load_metadata() -> SchemaMetadata:
    database = get_settings().mysql_database
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute('''SELECT TABLE_NAME FROM information_schema.TABLES
            WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME''', (database,))
        table_rows = cursor.fetchall()
        cursor.execute('''SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_COMMENT
            FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s
            ORDER BY TABLE_NAME, ORDINAL_POSITION''', (database,))
        column_rows = cursor.fetchall()
        cursor.execute('''SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA=%s AND CONSTRAINT_NAME='PRIMARY' ''', (database,))
        primary_key_rows = cursor.fetchall()
        cursor.execute('''SELECT TABLE_NAME, CONSTRAINT_NAME, COLUMN_NAME,
                REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA=%s AND REFERENCED_TABLE_SCHEMA=%s
                AND REFERENCED_TABLE_NAME IS NOT NULL
            ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION''', (database, database))
        foreign_key_rows = cursor.fetchall()

    primary_keys = set(primary_key_rows)
    tables = {row[0]: TableMetadata(table_name=row[0], columns=[], foreign_keys=[])
              for row in table_rows}
    for table, name, data_type, nullable, comment in column_rows:
        if table in tables:
            tables[table].columns.append(ColumnMetadata(
                name=name, type=data_type, primary_key=(table, name) in primary_keys,
                nullable=nullable == 'YES', comment=comment or None))
    for table, constraint, column, referenced_table, referenced_column in foreign_key_rows:
        if table in tables:
            tables[table].foreign_keys.append(ForeignKeyMetadata(
                constraint_name=constraint, column=column,
                references_table=referenced_table, references_column=referenced_column))
    return SchemaMetadata(database=database, tables=list(tables.values()))

