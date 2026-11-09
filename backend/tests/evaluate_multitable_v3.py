"""Evaluate 50 fixed multi-table questions; --live calls DeepSeek and MySQL."""

import argparse
import json
import logging
import math
import statistics
import time
from contextlib import nullcontext
from pathlib import Path

from sqlglot import exp, parse_one

from app.agent.budget import request_budget
from app.core.config import get_settings
from app.schema.candidate_retriever import retrieve_candidates
from app.schema.schema_graph import SchemaGraph
from app.schema.schema_linker import link_schema
from app.schema.models import SchemaMetadata
from app.semantic.element_extractor import extract_rule_elements
from app.semantic.element_merger import merge_elements
from app.semantic.normalizer import normalize_question
from app.semantic.semantic_validator import validate_semantics
from app.services.multitable_service import is_multitable_intent
from app.services.multitable_service import query as query_multitable
from app.services.sql_executor import execute_sql
from app.sql.join_path_planner import plan_join_path
from app.sql.multitable_validator import validate_multitable_sql
from app.llm.usage import collect_usage
from tests.multitable_cases_v3 import CASES


SCHEMA = SchemaMetadata.model_validate_json((Path(__file__).parent / 'fixtures' / 'chinook_schema.json').read_text(encoding='utf-8'))


def _close_number(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= max(0.02, abs(b) * 0.001)
    return a == b


def _result_matches(actual, expected):
    if len(actual) != len(expected):
        return False
    if len(expected) == 1 and len(expected[0]) == 1 and isinstance(expected[0][0], (int, float)):
        return any(_close_number(value, expected[0][0]) for row in actual for value in row)
    if any(len(left) != len(right) for left, right in zip(actual, expected)):
        return False
    actual = sorted(actual, key=lambda row: json.dumps(row, ensure_ascii=False))
    expected = sorted(expected, key=lambda row: json.dumps(row, ensure_ascii=False))
    return all(all(_close_number(value, gold) for value, gold in zip(row, reference))
               for row, reference in zip(actual, expected))


def _aggregate_signature(sql, rows):
    tree = parse_one(sql, read='mysql')
    indexes = [index for index, expression in enumerate(tree.expressions)
               if expression.find(exp.AggFunc)]
    if not indexes:
        return None
    return sorted([tuple(row[index] for index in indexes) for row in rows],
                  key=lambda row: json.dumps(row, ensure_ascii=False))


def _percentile(values: list[int], proportion: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(proportion * len(ordered)) - 1)]


def evaluate(live: bool = False, *, max_api_requests: int | None = None,
             max_total_tokens: int = 2_000_000) -> dict:
    logging.getLogger('datafusion').setLevel(logging.WARNING)
    graph = SchemaGraph(SCHEMA)
    records = []
    settings = get_settings()
    api_attempt_ceiling = (max_api_requests if max_api_requests is not None else
                           len(CASES) * settings.max_llm_calls)
    budget_context = (request_budget(api_attempt_ceiling, settings.llm_timeout,
                                     settings.max_context_tokens, max_total_tokens)
                      if live else nullcontext(None))
    usage_context = collect_usage() if live else nullcontext(None)
    token_budget_state = None
    budget_exhausted = False
    with budget_context as live_budget, usage_context as live_usage:
        for index, case in enumerate(CASES, 1):
            question = case['question']
            normalized = normalize_question(question)['normalized_question']
            elements = [item.to_dict() for item in extract_rule_elements(question, normalized)]
            candidates = retrieve_candidates(normalized, elements, SCHEMA)
            linked = link_schema(normalized, elements, candidates, SCHEMA)
            record = {'category': case['category'], 'question': question,
                      'expected_tables': case['expected_tables'],
                      'selected_tables': linked['selected_tables'],
                      'intent_detected': is_multitable_intent(question),
                      'v2_would_clarify': validate_semantics(question, merge_elements(
                          extract_rule_elements(question, normalized)))['need_clarification'],
                      'table_selection_correct': False, 'join_path_correct': False,
                      'reference_valid': False, 'syntax_correct': False,
                      'execution_correct': False, 'result_correct': False,
                      'aggregate_value_correct': False}
            try:
                plan = plan_join_path(linked['selected_tables'], graph)
                record['table_selection_correct'] = set(linked['selected_tables']) <= set(case['expected_tables']) and (
                    set(case['expected_tables']) <= set(plan['join_tables']))
                record['join_path_correct'] = set(plan['join_tables']) == set(case['expected_tables']) and all(
                    edge['right_table'] in graph.neighbors(edge['left_table']) for edge in plan['join_path'])
                selected = list(linked['selected_columns']) + [
                    f"{edge[side+'_table']}.{edge[side+'_column']}"
                    for edge in plan['join_path'] for side in ('left', 'right')]
                reference_root = parse_one(case['reference_sql'], read='mysql').args['from_'].this.name
                reference_plan = plan_join_path([reference_root, *case['expected_tables']], graph)
                reference_selected = selected + [f'{table.table_name}.{column.name}'
                    for table in SCHEMA.tables if table.table_name in reference_plan['join_tables']
                    for column in table.columns]
                validate_multitable_sql(case['reference_sql'], reference_plan, SCHEMA, reference_selected)
                record['reference_valid'] = True
            except Exception as error:
                record['reference_error'] = type(error).__name__ + ': ' + str(error)
            if live:
                started = time.perf_counter()
                calls_before = live_usage.api_requests
                reported_before = live_usage.reported_requests
                prompt_before = live_usage.prompt_tokens
                completion_before = live_usage.completion_tokens
                try:
                    payload = query_multitable(question)
                    record['status_code'] = 200
                    record['latency_seconds'] = round(time.perf_counter() - started, 2)
                    record['error'] = None
                    sql = payload.get('sql')
                    record['sql'] = sql
                    record['columns'] = payload.get('columns')
                    record['actual_rows'] = payload.get('rows')
                    if sql:
                        record['syntax_correct'] = isinstance(parse_one(sql, read='mysql'), exp.Select)
                    record['execution_correct'] = sql is not None and (
                        payload.get('sql_validation', {}).get('valid') is True)
                    record['join_path_correct'] = record['join_path_correct'] and (
                        set(payload.get('join_plan', {}).get('join_tables', [])) == set(case['expected_tables']))
                    record['repair_count'] = payload.get('sql_validation', {}).get('repair_count')
                    if record['execution_correct'] and record['reference_valid']:
                        _, expected_rows = execute_sql(case['reference_sql'])
                        record['expected_rows'] = expected_rows
                        record['result_correct'] = _result_matches(payload['rows'], expected_rows)
                        actual_signature = _aggregate_signature(sql, payload['rows'])
                        expected_signature = _aggregate_signature(case['reference_sql'], expected_rows)
                        if actual_signature is not None and expected_signature is not None:
                            record['aggregate_value_correct'] = _result_matches(
                                actual_signature, expected_signature)
                except Exception as error:
                    record['error'] = getattr(error, 'code', type(error).__name__)
                    record['error_message'] = getattr(error, 'message', str(error))[:500]
                    record['diagnostic'] = getattr(error, 'diagnostic', None)
                    record['failed_step'] = getattr(error, 'failed_step', None)
                    record['generated_query'] = getattr(error, 'generated_query', None)
                    record['trace'] = getattr(error, 'trace', [])
                    record['latency_seconds'] = round(time.perf_counter() - started, 2)
                    if record['error'] in {'LLM_TOKEN_BUDGET_EXCEEDED', 'LLM_BUDGET_EXCEEDED'}:
                        budget_exhausted = True
                record['api_requests'] = live_usage.api_requests - calls_before
                record['reported_requests'] = live_usage.reported_requests - reported_before
                record['prompt_tokens'] = live_usage.prompt_tokens - prompt_before
                record['completion_tokens'] = live_usage.completion_tokens - completion_before
                record['total_tokens'] = record['prompt_tokens'] + record['completion_tokens']
                token_budget_state = live_budget.token_budget_usage()
                print(f"{index}/50 {case['category']} status={record.get('status_code')} "
                      f"result={record['result_correct']}", flush=True)
            records.append(record)
            if live and budget_exhausted:
                break
    latencies_ms = [round(row['latency_seconds'] * 1000) for row in records
                    if live and 'latency_seconds' in row]
    metrics = {name: round(sum(bool(row[name]) for row in records) / len(records), 4)
               for name in ('intent_detected', 'v2_would_clarify', 'table_selection_correct',
                            'join_path_correct', 'reference_valid', 'syntax_correct',
                            'execution_correct', 'result_correct', 'aggregate_value_correct')}
    categories = {category: sum(row['category'] == category for row in records)
                  for category in ('two_table', 'three_table', 'aggregation', 'complex')}
    return {'mode': 'live' if live else 'offline', 'cases': len(records),
            'categories': categories, 'metrics': metrics,
            'api_request_cap': max_api_requests,
            'api_attempt_ceiling': api_attempt_ceiling if live else 0,
            'token_budget': token_budget_state,
            'llm_usage': ({key: sum(row.get(key, 0) for row in records)
                           for key in ('api_requests', 'reported_requests', 'prompt_tokens',
                                       'completion_tokens', 'total_tokens')} if live else {}),
            'latency_ms': ({'p50': _percentile(latencies_ms, .50),
                            'p95': _percentile(latencies_ms, .95),
                            'mean': round(statistics.mean(latencies_ms), 2) if latencies_ms else None}
                           if live else {}),
            'budget_exhausted': budget_exhausted,
            'complete': len(records) == len(CASES) and not budget_exhausted
                        and (not live or not token_budget_state['exceeded']),
            'failures': [row for row in records if not (
                row['result_correct'] if live else row['reference_valid'] and row['join_path_correct'])]}


class _NoClient:
    def __enter__(self):
        return None

    def __exit__(self, *_):
        return None


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--max-api-requests', type=int,
                        help='optional hard upper bound on API attempts')
    parser.add_argument('--max-total-tokens', type=int, default=2_000_000,
                        help='total provider-token budget, default 2,000,000')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.max_api_requests is not None and args.max_api_requests < 1:
        parser.error('--max-api-requests must be positive when provided')
    if not 1 <= args.max_total_tokens <= 2_000_000:
        parser.error('--max-total-tokens must be between 1 and 2000000')
    result = evaluate(args.live, max_api_requests=args.max_api_requests,
                      max_total_tokens=args.max_total_tokens)
    target = args.output or Path(__file__).resolve().parents[2] / 'docs' / (
        'evaluation_multitable_v3_live.json' if args.live else 'evaluation_multitable_v3_offline.json')
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('metrics', json.dumps(result['metrics'], ensure_ascii=False), 'saved', target, flush=True)
