"""Phase 21: real metadata shape, cache lifecycle, and refresh endpoint."""

from contextlib import contextmanager

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.api import schema as schema_api
from app.schema import metadata_loader, metadata_store, schema_cache
from app.schema.models import SchemaMetadata, TableMetadata


def test_loader_reads_columns_keys_comments_and_nullability(monkeypatch):
    batches = [
        [('Customer',), ('Invoice',)],
        [('Customer', 'CustomerId', 'int', 'NO', ''),
         ('Customer', 'Country', 'varchar(40)', 'YES', '客户所在国家'),
         ('Invoice', 'InvoiceId', 'int', 'NO', ''),
         ('Invoice', 'CustomerId', 'int', 'NO', '')],
        [('Customer', 'CustomerId'), ('Invoice', 'InvoiceId')],
        [('Invoice', 'FK_InvoiceCustomer', 'CustomerId', 'Customer', 'CustomerId')],
    ]

    class Cursor:
        def __init__(self):
            self.queries = []

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def execute(self, sql, params):
            assert params == (('chinook', 'chinook') if 'REFERENCED_TABLE_SCHEMA' in sql else ('chinook',))
            self.queries.append(sql)

        def fetchall(self):
            return batches[len(self.queries) - 1]

    cursor = Cursor()

    class Connection:
        def cursor(self):
            return cursor

    @contextmanager
    def fake_connection():
        yield Connection()

    monkeypatch.setattr(metadata_loader, 'connection', fake_connection)
    monkeypatch.setattr(metadata_loader, 'get_settings', lambda: type('Settings', (), {'mysql_database': 'chinook'})())
    snapshot = metadata_loader.load_metadata()
    assert len(cursor.queries) == 4
    assert [table.table_name for table in snapshot.tables] == ['Customer', 'Invoice']
    country = snapshot.tables[0].columns[1]
    assert (country.type, country.primary_key, country.nullable, country.comment) == (
        'varchar(40)', False, True, '客户所在国家')
    assert snapshot.tables[0].columns[0].primary_key is True
    assert snapshot.tables[1].foreign_keys[0].model_dump() == {
        'constraint_name': 'FK_InvoiceCustomer', 'column': 'CustomerId',
        'references_table': 'Customer', 'references_column': 'CustomerId'}


def test_store_caches_once_and_refresh_is_atomic(monkeypatch):
    cache = {'value': None}
    loads = []
    monkeypatch.setattr(metadata_store, 'get_cached_metadata', lambda: cache['value'])
    monkeypatch.setattr(metadata_store, 'replace_cached_metadata', lambda value: cache.update(value=value))

    def loader():
        loads.append(True)
        return SchemaMetadata(database='chinook', tables=[TableMetadata(
            table_name=f'Table{len(loads)}', columns=[], foreign_keys=[])])

    monkeypatch.setattr(metadata_store, 'load_metadata', loader)
    assert metadata_store.get_metadata().tables[0].table_name == 'Table1'
    assert metadata_store.get_metadata().tables[0].table_name == 'Table1'
    assert len(loads) == 1
    assert metadata_store.refresh_metadata().tables[0].table_name == 'Table2'

    def broken_loader():
        raise RuntimeError('offline')

    monkeypatch.setattr(metadata_store, 'load_metadata', broken_loader)
    with pytest.raises(RuntimeError):
        metadata_store.refresh_metadata()
    assert metadata_store.get_metadata().tables[0].table_name == 'Table2'


def test_cache_returns_isolated_snapshot(monkeypatch):
    monkeypatch.setattr(schema_cache, '_snapshot', None)
    schema_cache.replace_cached_metadata(SchemaMetadata(database='chinook', tables=[
        TableMetadata(table_name='Customer', columns=[], foreign_keys=[])]))
    copy = schema_cache.get_cached_metadata()
    copy.tables[0].table_name = 'Changed'
    assert schema_cache.get_cached_metadata().tables[0].table_name == 'Customer'
    monkeypatch.setattr(schema_cache, '_snapshot', None)


def test_refresh_endpoint_returns_snapshot(monkeypatch):
    monkeypatch.setattr(schema_api, 'refresh_metadata', lambda: SchemaMetadata(
        database='chinook', tables=[TableMetadata(table_name='Customer', columns=[], foreign_keys=[])]))
    response = TestClient(app).post('/api/schema/refresh')
    assert response.status_code == 200
    assert response.json() == {'success': True, 'schema': {'database': 'chinook', 'tables': [
        {'table_name': 'Customer', 'columns': [], 'foreign_keys': []}]}}
