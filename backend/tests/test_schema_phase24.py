import pytest

from app.schema.candidate_retriever import retrieve_candidates
from app.schema.models import ColumnMetadata, ForeignKeyMetadata, SchemaMetadata
from app.schema.schema_linker import link_schema
from tests.test_schema_phase23 import CASES, SCHEMA


@pytest.fixture
def linked_schema():
    snapshot = SCHEMA.model_copy(deep=True)
    tables = {table.table_name: table for table in snapshot.tables}
    for source, column, target, target_column in [
        ('invoice', 'CustomerId', 'customer', 'CustomerId'),
        ('invoiceline', 'InvoiceId', 'invoice', 'InvoiceId'),
        ('invoiceline', 'TrackId', 'track', 'TrackId'),
        ('track', 'GenreId', 'genre', 'GenreId')]:
        tables[source].columns.append(ColumnMetadata(name=column, type='int', primary_key=False, nullable=False))
        tables[source].foreign_keys.append(ForeignKeyMetadata(
            constraint_name=f'FK_{source}_{target}', column=column,
            references_table=target, references_column=target_column))
    return snapshot


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['question'])
def test_linking_selects_existing_table_and_field(case, linked_schema):
    candidates = retrieve_candidates(case['question'], [], linked_schema)
    linked = link_schema(case['question'], [], candidates, linked_schema)
    assert case['table'] in linked['selected_tables']
    if case['column'] != 'CustomerId':
        assert f"{case['table']}.{case['column']}" in linked['selected_columns']
    assert not linked['needs_clarification']


def test_linker_rejects_invented_candidates(linked_schema):
    fake = {'candidate_tables': [{'table': 'Imaginary', 'score': 1.0}],
            'candidate_columns': [{'table': 'Imaginary', 'column': 'Ghost', 'score': 1.0}]}
    result = link_schema('查不存在的字段', [], fake, linked_schema)
    assert result['selected_tables'] == []
    assert result['selected_columns'] == []
    assert result['needs_clarification']


def test_linker_adds_sales_table_but_not_unrelated_table(linked_schema):
    question = '每个客户消费了多少钱'
    linked = link_schema(question, [], retrieve_candidates(question, [], linked_schema), linked_schema)
    assert set(linked['selected_tables']) == {'customer', 'invoice'}
    assert 'invoice.Total' in linked['selected_columns']


def test_linker_filters_unrelated_generic_type(linked_schema):
    question = '媒体类型名称'
    linked = link_schema(question, [], retrieve_candidates(question, [], linked_schema), linked_schema)
    assert linked['selected_tables'] == ['mediatype']
