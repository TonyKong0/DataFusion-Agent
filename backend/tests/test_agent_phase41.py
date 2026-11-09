from app.agent.models import ToolResult
from app.agent.tool_registry import call_tool, tool_names
from app.agent import tool_registry


def test_registry_has_existing_capabilities_and_uniform_result(monkeypatch):
    assert {'database_query', 'document_search', 'formula_calculate', 'clarification'} <= set(tool_names())
    monkeypatch.setitem(tool_registry._TOOLS, 'database_query', lambda q, c: ToolResult('database_query', True, {'rows': [[1]]}))
    result = call_tool('database_query', '一共有多少艺术家')
    assert result.to_dict()['success'] and result.data['rows'] == [[1]]
    assert result.latency_ms >= 0


def test_formula_adapter_reuses_stored_safe_calculation(monkeypatch):
    from app.agent.tools import formula_tool
    monkeypatch.setattr(formula_tool, 'load_document', lambda _: {
        'processing': {'formulas': [{'formula_id': 'f1', 'calculation': {'result': 20, 'page': 8,
            'raw_text': 'a+b'}}]},
        'content': [{'page': 8, 'chunk_id': 'c1', 'heading_path': ['计算'], 'text': 'a+b=20'}]})
    result = call_tool('formula_calculate', '增长率', {'document_id': 'doc_a', 'formula_id': 'f1'})
    assert result.success and result.data['result'] == 20
