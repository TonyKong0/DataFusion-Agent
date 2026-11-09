import pytest
from app.agent.models import ToolResult
from app.evidence.store import from_tool_result
from app.evidence.validator import validate_evidence
from app.evidence.lineage import evidence_lineage
from app.core.errors import AppError


def test_database_sql_and_tables_preserved():
    result = ToolResult('database_query', True, {'sql': 'SELECT c.CustomerId FROM Customer c JOIN Invoice i ON c.CustomerId=i.CustomerId',
        'columns': ['CustomerId'], 'rows': [[1]], 'row_count': 1})
    item = from_tool_result(result, 'step_1')[0]
    assert item['provenance']['tables'] == ['Customer', 'Invoice']
    assert item['provenance']['sql'].startswith('SELECT')
    assert evidence_lineage(item)['step_id'] == 'step_1'


def test_document_page_heading_and_original_text_preserved():
    result = ToolResult('document_search', True, {'document_id': 'doc_1', 'sources': [
        {'chunk_id': 'c1', 'page': 3, 'heading_path': ['第一章', '审核'], 'text': '阈值是 500', 'score': .9}]})
    item = from_tool_result(result, 'step_2', 'rules.pdf')[0]
    assert item['provenance']['page'] == 3
    assert item['provenance']['heading_path'] == ['第一章', '审核']
    assert item['provenance']['text'] == '阈值是 500'
    assert item['source_name'] == 'rules.pdf'


def test_invalid_document_source_not_silently_accepted():
    result = ToolResult('document_search', True, {'sources': [{'text': 'x'}]})
    with pytest.raises(AppError):
        from_tool_result(result, 'step_1')


def test_formula_requires_original_page():
    with pytest.raises(AppError):
        validate_evidence({'source_type': 'formula', 'provenance': {'expression': 'a+b'}})
