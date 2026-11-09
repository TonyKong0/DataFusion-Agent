from app.agent.models import ToolResult
from app.agent.service import _tool_latency


def test_measured_tool_and_nested_sql_timings():
    results = {
        'db': ToolResult('database_query', True, latency_ms=120,
                         data={'trace': [
                             {'name': 'question_normalize', 'duration_ms': 3},
                             {'name': 'schema_linking_completed', 'duration_ms': 8},
                             {'name': 'sql_generate', 'duration_ms': 90},
                             {'name': 'sql_execute', 'duration_ms': 4}]}),
        'doc': ToolResult('document_search', True, latency_ms=50),
    }
    timings = _tool_latency(results)
    assert timings == {'database_ms': 120, 'retrieval_ms': 50, 'formula_ms': 0,
                       'semantic_ms': 3, 'schema_linking_ms': 8, 'sql_ms': 94}
