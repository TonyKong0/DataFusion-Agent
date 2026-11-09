from app.evidence.multimodal_conflict import detect_multimodal_conflicts


def test_text_table_database_conflict_keeps_every_source():
    evidence = [
        {'evidence_id': 'a', 'source_type': 'text', 'source_name': 'r.pdf',
         'content': '增长率为20%', 'provenance': {'page': 2}},
        {'evidence_id': 'b', 'source_type': 'table', 'source_name': 'r.pdf',
         'content': {'headers': ['年份', '增长率'], 'row': ['2025', '18%'], 'column_index': 1},
         'provenance': {'page': 3}},
        {'evidence_id': 'c', 'source_type': 'database', 'source_name': 'Chinook',
         'content': {'columns': ['增长率'], 'rows': [[19.6]]}, 'provenance': {'sql': 'SELECT ...'}},
    ]
    conflicts = detect_multimodal_conflicts(evidence)
    assert len(conflicts) == 1
    assert conflicts[0]['topic'] == '增长率'
    assert {item['evidence_id'] for item in conflicts[0]['values']} == {'a', 'b', 'c'}
    assert conflicts[0]['resolution'] == 'unresolved'
