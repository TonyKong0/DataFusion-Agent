"""Bounded, sequential execution. All work goes through the tool registry."""
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextvars import copy_context
from time import monotonic
from app.agent.execution_context import ExecutionContext
from app.agent.execution_state import ExecutionState
from app.agent.plan_validator import validate_plan
from app.agent.tool_registry import call_tool
from app.agent.models import ToolResult
from app.agent.result_values import _extract_number, _primary_value
from app.core.config import get_settings

RETRYABLE = {'TIMEOUT', 'TEMPORARY_ERROR', 'SERVICE_UNAVAILABLE'}
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix='agent-tool')


def _resolve(result, name):
    if name == 'extracted_number':
        return _extract_number(result.data)
    if name == 'primary_value':
        return _primary_value(result.data)
    return result.data.get(name)


def execute_plan(plan, context: dict | None = None):
    validate_plan(plan)
    execution = ExecutionContext(plan.question, plan.plan_id)
    state = ExecutionState('running')
    base_context = dict(context or {})
    settings = get_settings()
    deadline = monotonic() + settings.plan_timeout
    for step in plan.steps:
        bindings = {}
        for key, reference in step.inputs_from.items():
            source_id, _, name = reference.partition('.data.')
            source = execution.step_results.get(source_id)
            value = _resolve(source, name) if source and source.success else None
            if value is None:
                state.status, state.failed_step = 'partial_success' if execution.step_results else 'need_clarification', step.id
                state.trace.append({'step_id': step.id, 'tool': step.tool, 'status': 'missing_dependency',
                                    'message': f'{reference} 没有可核实的值', 'latency_ms': 0})
                return execution, state
            bindings[key] = value
        instruction = step.instruction
        for key, value in bindings.items():
            instruction = instruction.replace('{' + key + '}', str(value))
        if 'threshold' in bindings:
            instruction = re.sub(r'这个值|该值', str(bindings['threshold']), instruction)
        attempts = 0
        while True:
            attempts += 1
            remaining = deadline - monotonic()
            tool_limit = settings.document_timeout if step.tool in ('document_search', 'formula_calculate',
                'multi_document_search', 'document_compare', 'table_query', 'chart_analyze', 'image_query') else settings.database_timeout
            if remaining <= 0:
                result = ToolResult(step.tool, False, error={'code': 'PLAN_TIMEOUT', 'message': '计划执行超时'})
                break
            submitted = monotonic()
            previous_database = next((value.data for value in execution.step_results.values()
                                      if value.tool == 'database_query' and value.success), None)
            future = _pool.submit(copy_context().run, call_tool, step.tool, instruction,
                                  {**base_context, **bindings, 'top_k': settings.max_retrieved_chunks,
                                   'database_result': previous_database})
            try:
                result = future.result(timeout=min(remaining, tool_limit))
            except FutureTimeout:
                future.cancel()
                result = ToolResult(step.tool, False, error={'code': 'TIMEOUT', 'message': '工具执行超时'},
                                    latency_ms=round((monotonic() - submitted) * 1000))
            except Exception:
                result = ToolResult(step.tool, False, error={'code': 'TOOL_FAILED', 'message': '工具执行失败'},
                                    latency_ms=round((monotonic() - submitted) * 1000))
            if result.success or attempts >= 2 or (result.error or {}).get('code') not in RETRYABLE:
                break
        execution.step_results[step.id] = result
        execution.variables.update(bindings)
        state.trace.append({'step_id': step.id, 'tool': step.tool,
                            'status': 'success' if result.success else (result.error or {}).get('code', 'failed').lower(),
                            'attempts': attempts, 'latency_ms': result.latency_ms,
                            'error': result.error})
        if not result.success:
            state.failed_step = step.id
            state.status = 'partial_success' if any(r.success for r in execution.step_results.values()) else (
                'need_clarification' if (result.error or {}).get('code') == 'NEED_CLARIFICATION' else 'failed')
            return execution, state
    state.status = 'success'
    return execution, state
