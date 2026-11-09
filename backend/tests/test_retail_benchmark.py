from datetime import datetime
from decimal import Decimal

import pytest

from scripts.prepare_retail_benchmark import _clean_row, sample_indices
from scripts.evaluate_retail_benchmark import evaluate_output
from app.schema.candidate_retriever import retrieve_candidates
from app.schema.models import ColumnMetadata, SchemaMetadata, TableMetadata
from app.semantic.element_extractor import extract_rule_elements
from app.semantic.element_merger import merge_elements
from app.semantic.semantic_validator import validate_semantics
from app.services.multitable_service import is_multitable_intent


def test_sample_indices_are_deterministic_evenly_spaced_and_include_boundaries():
    first = sample_indices(100_000, 10_000)
    second = sample_indices(100_000, 10_000)

    assert first == second
    assert len(first) == 10_000
    assert first[0] == 0 and first[-1] == 99_999
    assert max(b - a for a, b in zip(first, first[1:])) - min(
        b - a for a, b in zip(first, first[1:])) <= 1


def test_clean_row_maps_uci_headers_and_keeps_missing_customer_id_null():
    header = ['Invoice', 'StockCode', 'Description', 'Quantity', 'InvoiceDate',
              'Price', 'Customer ID', 'Country']
    columns = {name.strip().casefold().replace(' ', ''): index for index, name in enumerate(header)}
    columns['invoiceno'] = columns['invoice']
    columns['unitprice'] = columns['price']
    row = ('536365', '85123A', 'White hanging heart', 6,
           datetime(2010, 12, 1, 8, 26), Decimal('2.55'), None, 'United Kingdom')

    cleaned = _clean_row(row, columns)

    assert cleaned == ('536365', '85123A', 'White hanging heart', 6,
                       datetime(2010, 12, 1, 8, 26), Decimal('2.5500'), None,
                       'United Kingdom')


def test_sample_indices_reject_too_small_source():
    with pytest.raises(ValueError, match='need at least'):
        sample_indices(9999, 10_000)


def test_retail_entity_and_country_scope_link_to_only_the_live_retail_table():
    question = '英国有多少笔零售交易记录'
    extracted = merge_elements(extract_rule_elements(question))
    schema = SchemaMetadata(database='retail_bench_1k', tables=[TableMetadata(
        table_name='retail_transaction', columns=[
            ColumnMetadata(name='InvoiceNo', type='varchar', primary_key=False, nullable=False),
            ColumnMetadata(name='Quantity', type='int', primary_key=False, nullable=False),
            ColumnMetadata(name='Country', type='varchar', primary_key=False, nullable=False),
        ], foreign_keys=[])])

    candidates = retrieve_candidates(question, [item.to_dict() for item in extracted['elements']], schema)

    assert {item.canonical_value for item in extracted['elements'] if item.type == 'entity'} == {'RetailTransaction'}
    assert not validate_semantics(question, extracted)['need_clarification']
    assert [item['table'] for item in candidates['candidate_tables']] == ['retail_transaction']
    assert any(item['column'] == 'Country' for item in candidates['candidate_columns'])
    assert is_multitable_intent('零售交易中销量最高的10个商品编号是什么') is False


@pytest.mark.parametrize('question', [
    '零售商品的平均单价是多少',
    '退货记录中的商品数量总和是多少',
])
def test_retail_questions_identify_the_table_without_model_fallback(question):
    extracted = extract_rule_elements(question)
    assert any(item.type == 'entity' and item.canonical_value == 'RetailTransaction'
               for item in extracted)


def test_clarification_is_scored_as_wrong_without_crashing():
    case = {'expected_table': 'retail_transaction'}
    assert evaluate_output({'table': None, 'rows': [], 'need_clarification': True},
                           case['expected_table'], [[1000]]) == (False, 'NEED_CLARIFICATION')
