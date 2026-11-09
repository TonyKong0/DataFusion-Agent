from app.document.complexity.scorer import score_complexity


def test_complexity_changes_pipeline_strategy():
    low = score_complexity([{'page': 1, 'text': '普通正文', 'text_blocks': 2, 'image_count': 0, 'image_ratio': 0}])
    complex_doc = score_complexity([{'page': 1, 'text': '第一章 总览\n1.1 方法\n增长率=(本期值-上期值)/上期值×100%',
        'text_blocks': 0, 'image_count': 1, 'image_ratio': .95}])
    assert low['level'] == 'Low' and low['recommended_strategy'] == ['native_parser']
    assert 'enable_ocr' in complex_doc['recommended_strategy']
    assert 'enable_formula_parser' in complex_doc['recommended_strategy']
    assert 'hierarchical_chunking' in complex_doc['recommended_strategy']
