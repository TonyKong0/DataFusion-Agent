from app.agent.executor import execute_plan
from app.agent.models import ToolResult
from app.agent.plan_models import ExecutionPlan, PlanStep


def test_pass_verified_document_number_to_database(monkeypatch):
    seen = []
    def fake_call(name, question, context):
        seen.append((name, question, context))
        if name == 'document_search':
            return ToolResult(name, True, {'answer': '阈值为 500 元', 'sources': [{'text': '审核阈值为 500 元'}]})
        return ToolResult(name, True, {'columns': ['count'], 'rows': [[3]], 'sql': 'SELECT COUNT(*) FROM Invoice'})
    monkeypatch.setattr('app.agent.executor.call_tool', fake_call)
    plan = ExecutionPlan('p', 'q', 'CROSS_SOURCE', [PlanStep('step_1', 'document_search', '阈值？'),
        PlanStep('step_2', 'database_query', '超过这个值的订单数？', ['step_1'], {'threshold': 'step_1.data.extracted_number'})])
    context, state = execute_plan(plan)
    assert state.status == 'success'
    assert seen[1][1] == '超过500的订单数？'
    assert seen[1][2]['threshold'] == 500
    assert context.step_results['step_2'].success


def test_uncited_number_stops_dependent_step(monkeypatch):
    calls = []
    def fake_call(name, question, context):
        calls.append(name)
        return ToolResult(name, True, {'answer': '阈值为 500', 'sources': [{'text': '没有数值'}]})
    monkeypatch.setattr('app.agent.executor.call_tool', fake_call)
    plan = ExecutionPlan('p', 'q', 'CROSS_SOURCE', [PlanStep('step_1', 'document_search', 'q'),
        PlanStep('step_2', 'database_query', '{threshold}', ['step_1'], {'threshold': 'step_1.data.extracted_number'})])
    context, state = execute_plan(plan)
    assert state.status == 'partial_success'
    assert calls == ['document_search']
    assert context.step_results['step_1'].success


def test_retry_once_and_trace(monkeypatch):
    calls = []
    def fake_call(name, question, context):
        calls.append(name)
        return ToolResult(name, len(calls) == 2, error=None if len(calls) == 2 else {'code': 'TIMEOUT'})
    monkeypatch.setattr('app.agent.executor.call_tool', fake_call)
    plan = ExecutionPlan('p', 'q', 'DATABASE_ONLY', [PlanStep('step_1', 'database_query', 'q')])
    _, state = execute_plan(plan)
    assert state.status == 'success' and state.trace[0]['attempts'] == 2
