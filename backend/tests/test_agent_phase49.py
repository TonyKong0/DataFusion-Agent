import threading
import pytest
from types import SimpleNamespace
from app.agent.budget import request_budget, current_budget
from app.agent.executor import execute_plan
from app.agent.plan_models import ExecutionPlan, PlanStep
from app.agent.models import ToolResult
from app.core.errors import AppError


def test_llm_budget_counts_and_caps_calls():
    with request_budget(2, 10, 1000) as budget:
        current_budget().consume('short')
        current_budget().consume('short')
        assert budget.used == 2
        with pytest.raises(AppError) as caught:
            current_budget().consume('short')
        assert caught.value.code == 'LLM_BUDGET_EXCEEDED'


def test_context_budget_rejects_large_payload():
    with request_budget(2, 10, 1000):
        with pytest.raises(AppError) as caught:
            current_budget().consume('x' * 4000)
        assert caught.value.code == 'CONTEXT_BUDGET_EXCEEDED'


def test_timeout_yields_failed_plan_and_bounded_retry(monkeypatch):
    settings = SimpleNamespace(plan_timeout=5.0, database_timeout=0.02,
                               document_timeout=0.02, max_retrieved_chunks=2, max_plan_steps=5)
    monkeypatch.setattr('app.agent.executor.get_settings', lambda: settings)
    monkeypatch.setattr('app.agent.plan_validator.get_settings', lambda: settings)
    calls = []
    release = threading.Event()
    def slow_call(name, question, context):
        calls.append(name)
        release.wait(10)
        return ToolResult(name, True)
    monkeypatch.setattr('app.agent.executor.call_tool', slow_call)
    plan = ExecutionPlan('p', 'q', 'DATABASE_ONLY', [PlanStep('step_1', 'database_query', 'q')])
    try:
        _, state = execute_plan(plan)
        assert state.status == 'failed'
        assert state.trace[0]['attempts'] == 2
        assert state.trace[0]['error']['code'] == 'TIMEOUT'
    finally:
        release.set()


def test_single_source_plan_is_one_step():
    from app.agent.router import route_query
    from app.agent.planner import create_plan
    for question in ('数据库有多少客户？', '文档讲了什么？'):
        assert len(create_plan(question, route_query(question, allow_llm=False)).steps) == 1
