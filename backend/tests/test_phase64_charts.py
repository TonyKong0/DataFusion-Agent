from app.document.chart import analyzer


def test_labeled_line_chart_fastest_growth_and_page(monkeypatch):
    chart = analyzer.analyze_chart_text('月度增长折线图\n一月 100\n二月 120\n三月 170\n图例：销量',
                                        18, 'doc_x', 'report.pdf')[0]
    monkeypatch.setattr(analyzer, 'extract_charts', lambda document_id: [chart])
    result = analyzer.query_chart('doc_x', '折线图中哪个月份增长最快？')
    assert chart['type'] == 'line_chart' and chart['page'] == 18
    assert '二月到三月' in result['answer'] and '50' in result['answer']
