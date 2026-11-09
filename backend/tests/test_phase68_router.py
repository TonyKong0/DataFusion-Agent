from app.agent.multimodal_router import route_multimodal
from app.agent.tool_registry import tool_names


def test_router_selects_specialized_tools_only_with_cues():
    ids = ['doc_a']
    assert route_multimodal('表格中2025年销售额是多少？', ids)['required_tools'] == ['table_query']
    assert route_multimodal('折线图中哪个月最高？', ids)['required_tools'] == ['chart_analyze']
    assert route_multimodal('架构图有哪些模块？', ids)['required_tools'] == ['image_query']
    assert route_multimodal('文档主要讲什么？', ids)['required_tools'] == ['document_search']
    assert route_multimodal('正文和表格中的增长率是否一致？', ids)['required_tools'] == ['document_search', 'table_query']
    assert route_multimodal('两份报告的架构描述？', ['doc_a', 'doc_b'])['required_tools'] == ['multi_document_search']
    assert route_multimodal('新版相对旧版修改了什么？', ['doc_a', 'doc_b'])['required_tools'] == ['document_compare']
    assert {'table_query', 'chart_analyze', 'image_query', 'multi_document_search',
            'document_compare'} <= set(tool_names())
