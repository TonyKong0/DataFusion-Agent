from app.agent.models import ToolResult
from app.evidence.store import from_tool_result


def test_table_and_image_evidence_retain_exact_coordinates():
    table = {'document_id': 'd', 'filename': 'r.pdf', 'page': 12, 'row_index': 2,
             'column_index': 1, 'row': ['2025', '1200'], 'headers': ['年', '销售额']}
    image = {'document_id': 'd', 'filename': 'r.pdf', 'page': 20, 'image_index': 2,
             'ocr_labels': [{'text': 'Router'}]}
    table_ev = from_tool_result(ToolResult('table_query', True, {'sources': [table]}), 'step_1')[0]
    image_ev = from_tool_result(ToolResult('image_query', True, {'sources': [image]}), 'step_2')[0]
    assert table_ev['source_type'] == 'table' and table_ev['provenance']['row_index'] == 2
    assert image_ev['source_type'] == 'image' and image_ev['provenance']['image_index'] == 2
