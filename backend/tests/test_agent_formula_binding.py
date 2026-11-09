from app.agent.tools import formula_tool
from app.core.errors import AppError
import pytest


def document():
    raw = '增长率=(本期值-上期值)/上期值×100%'
    return {'processing': {'formulas': [{'formula_id': 'f1', 'page': 3, 'raw_text': raw,
        'variables': ['本期值', '上期值'], 'heading_path': ['计算'],
        'calculation': {'result': 10, 'page': 3, 'raw_text': raw}}]},
        'content': [{'page': 3, 'chunk_id': 'chunk_1', 'heading_path': ['计算'], 'text': raw}]}


def test_exact_database_columns_bind_to_existing_safe_formula(monkeypatch):
    monkeypatch.setattr(formula_tool, 'load_document', lambda _: document())
    result = formula_tool.formula_calculate('计算增长率', {'document_id': 'doc_test',
        'formula_id': 'f1', 'cross_source': True,
        'database_result': {'sql': 'SELECT 120 AS 本期值, 100 AS 上期值 FROM Invoice',
                            'columns': ['本期值', '上期值'], 'rows': [[120, 100]]}})
    assert result.data['result'] == 20
    assert result.data['parameter_source'] == 'database'
    assert result.data['source']['page'] == 3
    assert result.data['database_sql'].startswith('SELECT')


def test_unmatched_database_columns_do_not_use_document_values(monkeypatch):
    monkeypatch.setattr(formula_tool, 'load_document', lambda _: document())
    with pytest.raises(AppError) as caught:
        formula_tool.formula_calculate('计算增长率', {'document_id': 'doc_test',
            'formula_id': 'f1', 'cross_source': True,
            'database_result': {'sql': 'SELECT 120 AS sales FROM Invoice',
                                'columns': ['sales'], 'rows': [[120]]}})
    assert caught.value.code == 'FORMULA_PARAMETER_UNCERTAIN'
