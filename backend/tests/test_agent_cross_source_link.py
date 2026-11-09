from app.agent.answer_composer import compose_answer
from app.agent.cross_source_link import build_cross_source_link
from app.agent.models import ToolResult
from app.agent.plan_models import ExecutionPlan, PlanStep


def document_first(sql='SELECT COUNT(*) AS n FROM Invoice WHERE Total > 5'):
    plan = ExecutionPlan('p', '文档阈值与数据库发票', 'CROSS_SOURCE', [
        PlanStep('step_1', 'document_search', '阈值是多少？'),
        PlanStep('step_2', 'database_query', '超过这个值的发票有多少？',
                 ['step_1'], {'threshold': 'step_1.data.extracted_number'})])
    results = {
        'step_1': ToolResult('document_search', True, {'answer': '阈值为 5 元',
            'sources': [{'text': '单笔金额阈值为 5 元'}]}),
        'step_2': ToolResult('database_query', True, {'sql': sql, 'columns': ['n'],
            'rows': [[27]], 'row_count': 1}),
    }
    evidence = [
        {'evidence_id': 'doc', 'source_type': 'document', 'source_name': 'rules.pdf', 'step_id': 'step_1',
         'content': '单笔金额阈值为 5 元',
         'provenance': {'page': 3, 'chunk_id': 'c1', 'text': '单笔金额阈值为 5 元'}},
        {'evidence_id': 'db', 'source_type': 'database', 'source_name': 'Chinook', 'step_id': 'step_2',
         'content': {'columns': ['n'], 'rows': [[27]], 'row_count': 1},
         'provenance': {'sql': sql, 'tables': ['Invoice']}},
    ]
    return plan, results, evidence


def test_document_number_is_verified_in_sql_where_and_dual_cited():
    plan, results, evidence = document_first()
    link = build_cross_source_link(plan, results, evidence)
    assert link['status'] == 'linked'
    assert link['binding']['value'] == 5
    assert link['evidence_ids'] == ['doc', 'db']
    output = compose_answer(evidence, {'conflicts': [], 'missing': []}, results, link)
    assert output['claims'][0]['evidence_ids'] == ['doc', 'db']
    assert '第 3 页' in output['answer'] and '27' in output['answer']


def test_sql_without_bound_threshold_does_not_claim_cross_source_link():
    plan, results, evidence = document_first('SELECT COUNT(*) AS n FROM Invoice WHERE Total > 8 LIMIT 5')
    link = build_cross_source_link(plan, results, evidence)
    assert link['status'] == 'unverified'
    output = compose_answer(evidence, {'conflicts': [], 'missing': []}, results, link)
    assert all(len(claim['evidence_ids']) == 1 for claim in output['claims'])


def test_partial_number_match_cannot_be_used_as_threshold():
    plan, results, evidence = document_first()
    results['step_1'].data['sources'][0]['text'] = '单笔金额阈值为 15 元'
    evidence[0]['content'] = '单笔金额阈值为 15 元'
    assert build_cross_source_link(plan, results, evidence)['status'] == 'unverified'


def test_database_name_must_appear_in_cited_document_snippet():
    plan = ExecutionPlan('p', '数据库类型的文档描述', 'CROSS_SOURCE', [
        PlanStep('step_1', 'database_query', '销量最高的音乐类型？'),
        PlanStep('step_2', 'document_search', '查询 {topic} 在文档中的说明',
                 ['step_1'], {'topic': 'step_1.data.primary_value'})])
    results = {'step_1': ToolResult('database_query', True, {'columns': ['genre'], 'rows': [['Rock']]}),
               'step_2': ToolResult('document_search', True, {'answer': 'Rock 是一种音乐类型'})}
    evidence = [
        {'evidence_id': 'db', 'step_id': 'step_1', 'source_type': 'database', 'content': {},
         'provenance': {'sql': 'SELECT Name FROM Genre', 'tables': ['Genre']}},
        {'evidence_id': 'doc', 'step_id': 'step_2', 'source_type': 'document', 'content': 'Rock 音乐具有强烈节奏',
         'source_name': 'guide.pdf', 'provenance': {'page': 2, 'chunk_id': 'c2', 'text': 'Rock 音乐具有强烈节奏'}},
    ]
    link = build_cross_source_link(plan, results, evidence)
    assert link['status'] == 'linked' and link['evidence_ids'] == ['db', 'doc']
    evidence[1]['content'] = '此处仅介绍古典音乐'
    assert build_cross_source_link(plan, results, evidence)['status'] == 'unverified'


def test_agent_response_exposes_verified_link_and_source_ids(monkeypatch):
    import pytest
    pytest.importorskip('faiss', reason='本机 faiss 原生库不可用', exc_type=ImportError)
    from app.agent.service import query
    def fake_call(name, instruction, context):
        if name == 'document_search':
            return ToolResult(name, True, {'document_id': 'doc_demo', 'answer': '单笔金额阈值为 5 元',
                'sources': [{'chunk_id': 'chunk_1', 'page': 2, 'heading_path': ['审核规则'],
                             'text': '单笔金额阈值为 5 元', 'score': .9}],
                'trace': [{'step': 'vector_search', 'name': 'vector_search',
                           'status': 'success', 'duration_ms': 12}]})
        assert context['threshold'] == 5
        return ToolResult(name, True, {'sql': 'SELECT COUNT(*) AS n FROM Invoice WHERE Total > 5',
            'columns': ['n'], 'rows': [[27]], 'row_count': 1,
            'semantic': {'normalized_question': '超过 5 的发票有多少？', 'elements': []},
            'schema_linking': {'selected_tables': ['Invoice'], 'selected_columns': ['Invoice.Total']},
            'join_plan': {'join_tables': ['Invoice'], 'join_path': []}})
    monkeypatch.setattr('app.agent.executor.call_tool', fake_call)
    monkeypatch.setattr('app.agent.service.list_documents', lambda: [{'document_id': 'doc_demo', 'filename': 'rules.pdf'}])
    output = query('文档规定的单笔金额阈值是多少，数据库里有多少发票超过这个值？',
                   'doc_demo', allow_router_llm=False)
    link = output['cross_source_link']
    assert link['status'] == 'linked'
    assert len(link['evidence_ids']) == 2
    assert output['claims'][0]['evidence_ids'] == link['evidence_ids']
    assert output['fusion']['sufficient']
    assert output['semantic']['normalized_question'] == '超过 5 的发票有多少？'
    assert output['schema_linking']['selected_tables'] == ['Invoice']
    assert output['join_plan']['join_tables'] == ['Invoice']
    assert output['execution']['trace'][0]['children'] == [
        {'step': 'vector_search', 'name': 'vector_search', 'status': 'success', 'duration_ms': 12}]


def test_database_clarification_exposes_reason_and_clickable_options(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    def fake_call(name, question, context):
        assert name == 'database_query'
        return ToolResult(name, False, data={
            'need_clarification': True,
            'answer': '请说明需要统计哪一种订单。',
            'clarification': {'session_id': 'clarify_1', 'question': '请说明需要统计哪一种订单。',
                              'kind': 'single_choice', 'options': ['发票数量', '订单金额']},
            'semantic': {'normalized_question': question,
                         'elements': [], 'validation': {'missing': ['统计指标']}},
            'trace': [{'step': 'semantic_validate', 'name': 'semantic_validate',
                       'status': 'success', 'duration_ms': 4}],
        }, error={'code': 'NEED_CLARIFICATION', 'message': '需要澄清'})

    monkeypatch.setattr('app.agent.executor.call_tool', fake_call)
    response = TestClient(app).post('/api/agent/query', json={'question': '数据库里有多少订单？'})

    assert response.status_code == 200
    result = response.json()
    assert result['execution']['status'] == 'need_clarification'
    assert result['semantic']['validation']['missing'] == ['统计指标']
    assert result['clarification']['options'] == ['发票数量', '订单金额']
    assert result['execution']['trace'][0]['children'][0]['step'] == 'semantic_validate'
