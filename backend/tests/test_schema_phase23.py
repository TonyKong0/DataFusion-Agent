import json
from pathlib import Path

import pytest

from app.schema.candidate_retriever import retrieve_candidates
from app.schema.models import ColumnMetadata, SchemaMetadata, TableMetadata


CASES = json.loads((Path(__file__).parent / 'cases' / 'schema_candidate_cases.json').read_text(encoding='utf-8'))
TABLE_COLUMNS = {
    'album': ['AlbumId', 'Title'], 'artist': ['ArtistId', 'Name'],
    'customer': ['CustomerId', 'FirstName', 'LastName', 'Company', 'City', 'Country', 'Phone', 'Email'],
    'employee': ['EmployeeId', 'Title', 'HireDate', 'ReportsTo'],
    'genre': ['GenreId', 'Name'], 'invoice': ['InvoiceId', 'InvoiceDate', 'Total', 'BillingCountry', 'BillingCity'],
    'invoiceline': ['InvoiceLineId', 'Quantity', 'UnitPrice'], 'mediatype': ['MediaTypeId', 'Name'],
    'playlist': ['PlaylistId', 'Name'], 'track': ['TrackId', 'Name', 'Composer', 'Milliseconds', 'Bytes', 'UnitPrice'],
}
SCHEMA = SchemaMetadata(database='chinook', tables=[TableMetadata(
    table_name=table, columns=[ColumnMetadata(name=column, type='int', primary_key=False, nullable=True)
                               for column in columns], foreign_keys=[])
    for table, columns in TABLE_COLUMNS.items()])


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['question'])
def test_candidate_recall(case):
    result = retrieve_candidates(case['question'], [], SCHEMA)
    assert case['table'] in [item['table'] for item in result['candidate_tables'][:5]]
    if case['column'] != 'CustomerId':
        assert (case['table'], case['column']) in [
            (item['table'], item['column']) for item in result['candidate_columns'][:10]]


def test_candidates_never_include_unloaded_schema():
    result = retrieve_candidates('客户邮箱和订单金额', [], SchemaMetadata(database='chinook', tables=[]))
    assert result == {'candidate_tables': [], 'candidate_columns': []}
