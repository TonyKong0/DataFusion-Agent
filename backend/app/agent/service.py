"""Public V5 orchestration; existing domain services remain the only workers."""
from time import perf_counter
import re
from app.agent.router import route_query
from app.agent.planner import create_plan
from app.agent.executor import execute_plan
from app.agent.executor import _extract_number, _primary_value
from app.agent.answer_composer import compose_answer
from app.agent.cross_source_link import build_cross_source_link
from app.evidence.store import from_tool_result
from app.evidence.fusion import fuse_evidence
from app.core.errors import AppError
from app.services.document_service import list_documents
from app.agent.budget import current_budget, request_budget
from app.core.config import get_settings
from app.services.question_provenance import preserve_question

COMPARABLE_METRICS = ('审核阈值', '金额上限', '预算值', '目标值', '价格', '客户数', '订单数', '数量')


def _mark_explicit_comparison(question: str, evidence: list[dict], step_results: dict):
    if not re.search(r'是否一致|对比|比较|差异|冲突|相同吗', question):
        return
    metric = next((name for name in COMPARABLE_METRICS if question.count(name) >= 2), None)
    if not metric:
        return
    for item in evidence:
        result = step_results.get(item['step_id'])
        if not result:
            continue
        if item['source_type'] == 'database':
            value = _primary_value(result.data)
        elif item['source_type'] == 'document':
            value = _extract_number({'answer': result.data.get('answer'),
                                     'sources': [{'text': item['content']}]})
        else:
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            item['fact_key'], item['fact_value'] = metric, value


def _tool_latency(step_results: dict) -> dict:
    """Expose measured tool and SQL pipeline timings without changing execution."""
    totals = {'database_ms': 0, 'retrieval_ms': 0, 'formula_ms': 0,
              'semantic_ms': 0, 'schema_linking_ms': 0, 'sql_ms': 0}
    for result in step_results.values():
        elapsed = max(0, result.latency_ms or 0)
        if result.tool == 'database_query':
            totals['database_ms'] += elapsed
            for step in result.data.get('trace') or []:
                duration = max(0, step.get('duration_ms') or 0)
                name = step.get('name', '')
                if name in {'question_normalize', 'elements_extract', 'semantic_validate'}:
                    totals['semantic_ms'] += duration
                elif name in {'schema_load', 'schema_candidates_retrieved',
                              'schema_linking_completed', 'join_path_planned'}:
                    totals['schema_linking_ms'] += duration
                elif name in {'sql_generate', 'sql_validate', 'sql_execute'} or name.startswith('sql_repair_'):
                    totals['sql_ms'] += duration
        elif result.tool == 'document_search':
            totals['retrieval_ms'] += elapsed
        elif result.tool == 'formula_calculate':
            totals['formula_ms'] += elapsed
    return totals


def _uses_material_asset_tool(question: str) -> bool:
    return any(cue in question for cue in (
        '折线图', '柱状图', '条形图', '饼图', '图表', '表格', '表中', '表内',
        '架构图', '流程图', '示意图', '插图', '截图', '图片',
        '版本对比', '新版', '旧版', '修改了什么', '变化了什么',
    ))


def query(question: str, document_id: str | None = None, formula_id: str | None = None,
          *, document_ids: list[str] | None = None, allow_router_llm: bool = True,
          force_document_route: bool = False, original_question: str | None = None) -> dict:
    ids = (list(dict.fromkeys(document_ids)) if document_ids is not None else
           ([document_id] if document_id else []))
    if len(ids) > 10:
        raise AppError('DOCUMENT_SELECTION_LIMIT', '每轮最多选择 10 份材料', 422)
    if ids and _uses_material_asset_tool(question):
        from app.agent.multimodal_service import query as query_material_assets
        return preserve_question(query_material_assets(question, ids), original_question or question, question)
    inherited = current_budget()
    if inherited:
        output = _query(question, document_id, formula_id, document_ids=ids if document_ids is not None else None,
                        allow_router_llm=allow_router_llm, force_document_route=force_document_route,
                        original_question=original_question)
        output['latency']['llm_calls'] = inherited.used
        output['latency']['prompt_tokens'] = inherited.prompt_tokens
        output['latency']['completion_tokens'] = inherited.completion_tokens
        return output
    settings = get_settings()
    with request_budget(settings.max_llm_calls, settings.llm_timeout, settings.max_context_tokens) as budget:
        output = _query(question, document_id, formula_id, document_ids=ids if document_ids is not None else None,
                        allow_router_llm=allow_router_llm, force_document_route=force_document_route,
                        original_question=original_question)
        output['latency']['llm_calls'] = budget.used
        output['latency']['prompt_tokens'] = budget.prompt_tokens
        output['latency']['completion_tokens'] = budget.completion_tokens
        return output


def _query(question: str, document_id: str | None = None, formula_id: str | None = None,
           *, document_ids: list[str] | None = None, allow_router_llm: bool = True,
           force_document_route: bool = False, original_question: str | None = None) -> dict:
    started = perf_counter()
    mark = started
    routing = ({'route': 'DOCUMENT_ONLY', 'required_tools': ['document_search'],
                'reason': ['材料问答会话使用当前所选材料'], 'confidence': 1.0,
                'normalized_question': question, 'elements': []}
               if force_document_route else route_query(
                   question, allow_llm=allow_router_llm,
                   selected_document_count=(len(document_ids) if document_ids is not None
                                            else int(bool(document_id)))))
    routing_ms = round((perf_counter() - mark) * 1000)
    mark = perf_counter()
    plan = create_plan(question, routing)
    planning_ms = round((perf_counter() - mark) * 1000)
    mark = perf_counter()
    context = {'document_id': document_id, 'formula_id': formula_id,
               'original_question': original_question or question,
               'cross_source': routing['route'] == 'CROSS_SOURCE'}
    if document_ids is not None:
        context['document_ids'] = document_ids
    execution, state = execute_plan(plan, context)
    execution_ms = round((perf_counter() - mark) * 1000)
    for item in state.trace:
        tool_result = execution.step_results.get(item.get('step_id'))
        if tool_result:
            item['children'] = [
                {**child, 'duration_ms': max(0, int(child.get('duration_ms') or 0))}
                for child in tool_result.data.get('trace', []) if isinstance(child, dict)
            ]
    mark = perf_counter()
    names = ({item['document_id']: item.get('filename') for item in list_documents()}
             if any(result.tool == 'document_search' for result in execution.step_results.values()) else {})
    selected_ids = (list(dict.fromkeys(document_ids)) if document_ids is not None else
                    ([document_id] if document_id else []))
    evidence, evidence_errors = [], []
    for step_id, result in execution.step_results.items():
        try:
            evidence.extend(from_tool_result(result, step_id, names.get(result.data.get('document_id'))))
        except AppError as error:
            evidence_errors.append(f'{step_id}: {error.message}')
    _mark_explicit_comparison(question, evidence, execution.step_results)
    cross_source_link = build_cross_source_link(plan, execution.step_results, evidence)
    required = (['database', 'document'] if routing['route'] == 'CROSS_SOURCE' else
                ['database'] if routing['route'] == 'DATABASE_ONLY' else
                ['document'] if routing['route'] == 'DOCUMENT_ONLY' else [])
    fusion = fuse_evidence(evidence, required, state.status == 'success')
    if cross_source_link['status'] == 'unverified':
        fusion['missing'].append(cross_source_link['summary'])
    fusion['missing'].extend(evidence_errors)
    if routing['route'] == 'CLARIFICATION_REQUIRED':
        fusion['missing'].append('需要用户明确数据源或问题范围')
    if 'formula_calculate' in routing['required_tools'] and any(
        result.tool == 'formula_calculate' and result.success and result.data.get('parameter_source') != 'database'
        for result in execution.step_results.values()):
        fusion['missing'].append('数据库数值尚未绑定到文档公式参数；公式结果仅基于文档自身参数')
    fusion['sufficient'] = fusion['sufficient'] and not evidence_errors
    fusion['sufficient'] = fusion['sufficient'] and not fusion['missing']
    fusion_ms = round((perf_counter() - mark) * 1000)
    mark = perf_counter()
    composed = compose_answer(evidence, fusion, execution.step_results, cross_source_link,
                              question=question)
    selection_error = next((result.error.get('message') for result in execution.step_results.values()
                            if result.tool == 'document_search' and result.error and
                            result.error.get('code') == 'DOCUMENT_SELECTION_REQUIRED'), None)
    if selection_error and not composed['claims']:
        composed['answer'] = selection_error
    clarification = next((result.data if result.tool == 'clarification'
                          else result.data.get('clarification')
                          for result in execution.step_results.values()
                          if (result.tool == 'clarification' and result.success)
                          or (result.tool == 'database_query' and result.data.get('need_clarification')
                              and result.data.get('clarification'))), None)
    if clarification:
        composed['answer'] = clarification.get('question', '请补充问题所指的数据源。')
    generation_ms = round((perf_counter() - mark) * 1000)
    output = {'success': True, 'question': question, 'route': routing, 'plan': plan.to_dict(),
            'document_ids': selected_ids,
            'document_names': [{'document_id': identifier,
                                'filename': names.get(identifier, identifier)}
                               for identifier in selected_ids],
            'execution': state.to_dict(), 'trace': state.trace,
            'tool_results': {key: value.to_dict() for key, value in execution.step_results.items()},
            'semantic': next((result.data.get('semantic') for result in execution.step_results.values()
                              if result.tool == 'database_query'
                              and result.data.get('semantic')), None),
            'schema_linking': next((result.data.get('schema_linking') for result in execution.step_results.values()
                                    if result.tool == 'database_query'
                                    and result.data.get('schema_linking')), None),
            'join_plan': next((result.data.get('join_plan') for result in execution.step_results.values()
                               if result.tool == 'database_query'
                               and result.data.get('join_plan')), None),
            'evidence': evidence, 'fusion': fusion, 'cross_source_link': cross_source_link, **composed,
            'clarification': clarification,
            'latency': {'routing_ms': routing_ms, 'planning_ms': planning_ms,
                        'execution_ms': execution_ms, 'fusion_ms': fusion_ms,
                        'generation_ms': generation_ms, 'total_ms': round((perf_counter() - started) * 1000),
                        **_tool_latency(execution.step_results)}}
    return preserve_question(output, original_question or question, question)
