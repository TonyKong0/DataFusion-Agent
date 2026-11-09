from app.document.table.extractor import normalize_table
from app.document.table import qa


def test_table_structure_and_grounded_growth(monkeypatch):
    table = normalize_table({'rows': [['年份', '销售额', '增长率'],
                                      ['2024', '1000', '-'], ['2025', '1200', '20%']]},
                            12, 1, 'report.pdf', 'doc_1')
    assert table['headers'] == ['年份', '销售额', '增长率']
    monkeypatch.setattr(qa, 'extract_tables', lambda document_id: [table])
    result = qa.query_table('doc_1', '2025年销售额比2024年增长多少？')
    assert result['value'] == 20
    assert {item['row_index'] for item in result['sources']} == {1, 2}
    assert all(item['page'] == 12 and item['column_index'] == 1 for item in result['sources'])
