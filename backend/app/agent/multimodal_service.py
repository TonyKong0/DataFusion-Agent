"""V7 entry point reusing the bounded V5 registry/executor and Evidence model."""
from time import perf_counter
from uuid import uuid4
from app.agent.multimodal_router import route_multimodal
from app.agent.plan_models import ExecutionPlan, PlanStep
from app.agent.executor import execute_plan
from app.agent.budget import request_budget
from app.core.config import get_settings
from app.evidence.store import from_tool_result
from app.evidence.multimodal_conflict import detect_multimodal_conflicts
from app.agent.citation_guard import guard_claims


def query(question: str, document_ids: list[str]) -> dict:
    started = perf_counter()
    routing = route_multimodal(question, document_ids)
    plan = ExecutionPlan('plan_' + uuid4().hex, question, routing['route'],
                         [PlanStep(f'step_{i}', name, question)
                          for i, name in enumerate(routing['required_tools'], 1)])
    settings = get_settings()
    with request_budget(settings.max_llm_calls, settings.llm_timeout, settings.max_context_tokens) as budget:
        execution, state = execute_plan(plan, {'document_ids': routing['document_ids'],
            'document_id': routing['document_ids'][0] if len(routing['document_ids']) == 1 else None,
            'cross_source': routing['route'] == 'CROSS_SOURCE'})
        evidence = [item for step_id, result in execution.step_results.items()
                    for item in from_tool_result(result, step_id)]
        conflicts = detect_multimodal_conflicts(evidence)
        claims = []
        for step_id, result in execution.step_results.items():
            if not result.success:
                continue
            ids = [item['evidence_id'] for item in evidence if item['step_id'] == step_id]
            answer = result.data.get('answer') or result.data.get('summary')
            if ids and answer:
                claims.append({'text': str(answer), 'evidence_ids': ids})
        accepted, warnings = guard_claims(claims, evidence)
        if conflicts:
            warnings.append('不同来源的同名指标不一致；未自动选择任何一方')
        if routing['route'] == 'CHART_DATABASE':
            warnings.append('图表与数据库统计口径尚未验证一致；不能直接断言趋势相同')
        failed = [result.error['message'] for result in execution.step_results.values()
                  if not result.success and result.error]
        cross_source_link = ({'status': 'parallel',
            'summary': '本轮分别查询材料与数据库，结果没有互相作为筛选条件。'}
            if routing['route'] == 'CROSS_SOURCE' else {'status': 'single_source'})
        if routing['route'] == 'CROSS_SOURCE':
            warnings.append(cross_source_link['summary'])
        warnings.extend(failed)
        answer = '\n\n'.join(f"{item['text']} [{', '.join(item['evidence_ids'])}]" for item in accepted)
        if not answer:
            answer = failed[0] if failed else '没有可核验的证据，无法回答。'
        return {'success': True, 'question': question, 'route': routing, 'plan': plan.to_dict(),
                'document_ids': routing['document_ids'],
                'execution': state.to_dict(), 'tool_results': {key: value.to_dict()
                    for key, value in execution.step_results.items()}, 'answer': answer,
                'claims': accepted, 'evidence': evidence, 'sources': evidence,
                'conflicts': conflicts, 'warnings': warnings,
                'cross_source_link': cross_source_link,
                'latency': {'total_ms': round((perf_counter() - started) * 1000),
                            'llm_calls': budget.used}}
