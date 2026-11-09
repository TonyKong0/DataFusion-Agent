from fastapi.testclient import TestClient
from app.main import app
from app.api import documents as documents_api
from app.services import rag_service


def test_analysis_api_exposes_quality_and_complexity(monkeypatch):
    monkeypatch.setattr(documents_api, 'analyze_document', lambda _: {
        'document_id': 'doc_test', 'filename': 'report.pdf', 'quality': {'quality_score': 90, 'issues': []},
        'complexity': {'score': 12, 'level': 'Low'}, 'headings': [], 'formulas': [], 'trace': []})
    response = TestClient(app).get('/api/documents/doc_test/analysis')
    assert response.status_code == 200
    assert response.json()['quality']['quality_score'] == 90


def test_formula_answer_uses_stored_page_evidence(monkeypatch):
    formula = {'formula_id': 'formula_001', 'raw_text': '增长率=(本期值-上期值)/上期值×100%',
        'calculation': {'formula_id': 'formula_001', 'raw_text': '增长率=(本期值-上期值)/上期值×100%',
            'page': 8, 'result': 20, 'unit': '%', 'parameters': [
                {'name': '本期值', 'raw_value': '1200', 'unit': '万元', 'page': 8, 'source_text': '本期值为1200万元'},
                {'name': '上期值', 'raw_value': '1000', 'unit': '万元', 'page': 8, 'source_text': '上期值为1000万元'}]}}
    chunk = {'chunk_id': 'c1', 'document_id': 'd', 'filename': 'report.pdf', 'page': 8,
        'heading_path': ['财务分析'], 'text': formula['raw_text'] + '\n本期值为1200万元\n上期值为1000万元'}
    monkeypatch.setattr(rag_service, 'load_document', lambda _: {'status': 'indexed',
        'processing': {'formulas': [formula]}, 'content': [chunk]})
    monkeypatch.setattr(rag_service, 'ready', lambda _: True)
    result = rag_service.query('d', '请计算增长率是多少？', 5)
    assert result['answer'].endswith('20%。')
    assert result['sources'][0]['page'] == 8
    assert result['formula_calculation']['result'] == 20


def test_ambiguous_formula_does_not_fall_back_to_llm(monkeypatch):
    document = {'status': 'indexed', 'content': [], 'processing': {'formulas': [
        {'raw_text': '增长率=(本期值-上期值)/上期值×100%', 'calculation_error': '参数有歧义'}]}}
    monkeypatch.setattr(rag_service, 'load_document', lambda _: document)
    monkeypatch.setattr(rag_service, 'ready', lambda _: True)
    monkeypatch.setattr(rag_service, 'chat_json', lambda *args: (_ for _ in ()).throw(AssertionError('LLM should not run')))
    result = rag_service.query('d', '请计算增长率是多少？', 5)
    assert result['formula_calculation'] is None
    assert '歧义' in result['answer']
