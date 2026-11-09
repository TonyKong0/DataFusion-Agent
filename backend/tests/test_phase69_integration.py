from pathlib import Path
from app.services import document_service
from app.document.table.qa import query_table
from app.document.chart.analyzer import query_chart
from app.document.image.image_qa import query_image
from app.document.versioning.comparator import compare
from app.agent.multimodal_service import query as agent_query
from app.agent.tools import document_tool
from fastapi.testclient import TestClient
from app.main import app
from app.agent.models import ToolResult
from app.agent.tool_registry import _TOOLS
from app.conversation import store as conversation_store
from app.api import conversations as conversation_api

FIXTURES = Path(__file__).parent / 'fixtures' / 'v7'


def test_real_pdf_table_chart_image_version_and_agent(tmp_path, monkeypatch):
    monkeypatch.setattr(document_service, 'DOCUMENT_DIR', tmp_path)
    ids = {}
    for filename in ('multimodal.pdf', 'policy_v1.pdf', 'policy_v2.pdf'):
        ids[filename] = document_service.import_document((FIXTURES / filename).read_bytes(), filename)['document_id']
    doc = ids['multimodal.pdf']
    table = query_table(doc, '表格中2025年销售额比2024年增长多少？')
    chart = query_chart(doc, '折线图中哪个阶段增长最快？')
    image = query_image(doc, '第3页架构图包含哪些模块？')
    diff = compare(ids['policy_v1.pdf'], ids['policy_v2.pdf'])
    agent = agent_query('表格中2025年销售额是多少？', [doc])
    chart_agent = agent_query('折线图中哪个阶段增长最快？', [doc])
    image_agent = agent_query('第3页架构图包含哪些模块？', [doc])
    version_agent = agent_query('新版相对旧版修改了什么？',
                                [ids['policy_v1.pdf'], ids['policy_v2.pdf']])
    assert table['value'] == 20 and table['sources'][0]['page'] == 1
    assert '二月到三月' in chart['answer'] and chart['chart']['page'] == 2
    assert {'Router', 'Planner', 'RAG'} <= set(image['image']['entities'])
    assert image['image']['page'] == 3 and image['image']['image_index'] == 1
    assert any(change['change_type'] == 'modified' for change in diff['changes'])
    assert agent['route']['route'] == 'TABLE' and agent['evidence'][0]['source_type'] == 'table'
    assert agent['evidence'][0]['provenance']['row_index'] == 20
    assert chart_agent['evidence'][0]['source_type'] == 'chart'
    assert chart_agent['evidence'][0]['provenance']['page'] == 2
    assert image_agent['evidence'][0]['source_type'] == 'image'
    assert image_agent['evidence'][0]['provenance']['image_index'] == 1
    assert version_agent['evidence'][0]['source_type'] == 'version_diff'
    monkeypatch.setattr(document_tool, 'query_documents', lambda document_ids, question, top_k: {
        'document_ids': document_ids, 'answer': '正文写增长率为20%。',
        'sources': [{'page': 1, 'chunk_id': 'body', 'text': '正文：增长率为20%。', 'score': 1.0}]})
    conflict_agent = agent_query('正文和表格中的增长率是否一致？', [doc])
    assert conflict_agent['route']['route'] == 'MULTIMODAL'
    assert {item['source_type'] for item in conflict_agent['evidence']} == {'document', 'table'}
    assert conflict_agent['conflicts'][0]['topic'] == '增长率'
    assert conflict_agent['conflicts'][0]['resolution'] == 'unresolved'
    response = TestClient(app).post('/api/multimodal/query', json={
        'question': '表格中2025年销售额是多少？', 'document_ids': [doc]})
    assert response.status_code == 200
    assert response.json()['evidence'][0]['provenance']['page'] == 1
    assets = TestClient(app).get(f'/api/multimodal/documents/{doc}/assets')
    assert assets.status_code == 200
    assert assets.json()['tables'] and assets.json()['charts'] and assets.json()['images']


def test_agent_conversation_keeps_document_scoped_entity_question_document_only(monkeypatch):
    document_id = 'doc_' + 'a' * 32
    owner_id = 'agent-conversation-regression'
    conversation_id = 'b' * 32
    conversation = {'id': conversation_id, 'mode': 'agent', 'document_id': document_id,
                    'document_name': 'orders-policy.pdf', 'summary': '', 'state': {}}
    monkeypatch.setattr(conversation_api, 'load_document', lambda _: {'filename': 'orders-policy.pdf'})
    monkeypatch.setattr(conversation_store, 'create', lambda *_args, **_kwargs: conversation)
    monkeypatch.setattr(conversation_store, 'get', lambda *_args, **_kwargs: conversation)
    monkeypatch.setattr(conversation_store, 'recent_turns', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(conversation_store, 'append_turn', lambda *_args, **_kwargs: None)

    def document_search(question, context):
        return ToolResult('document_search', True, data={
            'document_id': document_id,
            'answer': '单笔订单金额审核阈值为 5 元。',
            'sources': [{'page': 1, 'chunk_id': 'threshold',
                         'text': '单笔订单金额审核阈值为 5 元。', 'score': 1.0}],
        })

    monkeypatch.setitem(_TOOLS, 'document_search', document_search)
    client = TestClient(app)
    headers = {'X-Client-Id': owner_id}
    created = client.post('/api/conversations',
                          json={'mode': 'agent', 'document_id': document_id}, headers=headers)
    assert created.status_code == 200

    response = client.post(f'/api/conversations/{conversation_id}/query',
                           json={'question': '文档中的订单金额审核阈值是多少？'}, headers=headers)

    assert response.status_code == 200
    result = response.json()
    assert result['route']['route'] == 'DOCUMENT_ONLY'
    assert result['execution']['status'] == 'success'
    assert set(result['tool_results']) == {'step_1'}
    assert result['tool_results']['step_1']['tool'] == 'document_search'
    assert result['evidence'][0]['provenance']['page'] == 1
