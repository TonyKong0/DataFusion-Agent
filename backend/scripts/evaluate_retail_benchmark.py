"""Compare the same labeled NL2SQL workload on deterministic UCI 1k/10k MySQL samples."""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agent.budget import request_budget
from app.core.config import get_settings
from app.db.schema_loader import load_schema
from app.llm.usage import collect_usage
from app.services.nl2sql_service import query
from app.services.sql_executor import execute_sql

CASES_PATH = ROOT / 'tests/cases/retail_nl2sql_cases.json'
DATABASES = {1000: 'retail_bench_1k', 10000: 'retail_bench_10k'}
DEFAULT_TOTAL_TOKEN_BUDGET = 2_000_000


def _value_matches(actual, expected) -> bool:
    if isinstance(actual, (int, float, Decimal)) and isinstance(expected, (int, float, Decimal)):
        try:
            return abs(Decimal(str(actual)) - Decimal(str(expected))) <= Decimal('0.0001')
        except InvalidOperation:
            return False
    if hasattr(actual, 'isoformat'):
        actual = actual.isoformat(sep=' ')
    if hasattr(expected, 'isoformat'):
        expected = expected.isoformat(sep=' ')
    return str(actual) == str(expected)


def rows_match(actual: list, expected: list, *, order_matters: bool) -> bool:
    if len(actual) != len(expected):
        return False
    actual_rows, expected_rows = list(actual), list(expected)
    if not order_matters:
        key = lambda row: json.dumps(row, ensure_ascii=False, default=str, sort_keys=True)
        actual_rows.sort(key=key)
        expected_rows.sort(key=key)
    return all(len(a) == len(e) and all(_value_matches(x, y) for x, y in zip(a, e))
               for a, e in zip(actual_rows, expected_rows))


def evaluate_output(output: dict, expected_table: str, expected_rows: list, *,
                    order_matters: bool = False) -> tuple[bool, str | None]:
    """Compare a service result with its oracle without assuming a table is present."""
    if output.get('need_clarification'):
        return False, 'NEED_CLARIFICATION'
    table = output.get('table')
    if not isinstance(table, str) or not table.strip():
        return False, 'MISSING_TABLE'
    if table.casefold() != expected_table.casefold():
        return False, 'WRONG_TABLE'
    if not rows_match(output.get('rows') or [], expected_rows,
                      order_matters=order_matters):
        return False, 'RESULT_MISMATCH'
    return True, None


def _bounded_text(value, maximum: int = 1000) -> str | None:
    if value is None:
        return None
    return str(value)[:maximum]


def percentile(values: list[int], proportion: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(proportion * len(ordered)) - 1)]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='call the configured model API; otherwise only print the run plan')
    parser.add_argument('--repeat', type=int, default=3, help='repetitions per case and database size (default: 3)')
    parser.add_argument('--max-api-requests', type=int,
                        help='optional hard upper bound on model HTTP attempts')
    parser.add_argument('--max-total-tokens', type=int, default=DEFAULT_TOTAL_TOKEN_BUDGET,
                        help='total provider-token budget; accepts 1..2,000,000 (default: 2,000,000)')
    parser.add_argument('--input-usd-per-million', type=float)
    parser.add_argument('--output-usd-per-million', type=float)
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'docs/evaluation_retail_benchmark.json')
    args = parser.parse_args(argv)
    if not 1 <= args.repeat <= 20:
        parser.error('--repeat must be between 1 and 20')
    if not 1 <= args.max_total_tokens <= DEFAULT_TOTAL_TOKEN_BUDGET:
        parser.error('--max-total-tokens must be between 1 and 2000000')
    if args.max_api_requests is not None and args.max_api_requests < 1:
        parser.error('--max-api-requests must be a positive integer when provided')
    if (args.input_usd_per_million is None) != (args.output_usd_per_million is None):
        parser.error('provide both token prices or neither')
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.live:
        print(json.dumps({'mode': 'preview_only', 'dataset': 'UCI Online Retail II',
                          'sample_sizes': [1000, 10000], 'cases_per_size': 10,
                          'repetitions': args.repeat,
                          'maximum_queries': 20 * args.repeat,
                          'model': get_settings().deepseek_model,
                          'max_total_tokens': args.max_total_tokens,
                          'max_api_requests': args.max_api_requests,
                          'api_requests': 0,
                          'next_step': 'add --live; optionally set --max-api-requests N and --max-total-tokens N'},
                         ensure_ascii=False, indent=2))
        return 0
    cases = json.loads(CASES_PATH.read_text(encoding='utf-8'))
    settings = get_settings()
    original_database = settings.mysql_database
    request_ceiling = (args.max_api_requests if args.max_api_requests is not None else
                       len(cases) * len(DATABASES) * args.repeat * settings.max_llm_calls)
    remaining = request_ceiling
    token_budget_exhausted = False
    results: dict[str, list[dict]] = {}
    try:
        with request_budget(request_ceiling, settings.llm_timeout,
                            settings.max_context_tokens, args.max_total_tokens) as run_budget:
            for size, database in DATABASES.items():
                settings.mysql_database = database
                schema = load_schema()
                if not any(table['table'].lower() == 'retail_transaction' for table in schema):
                    raise RuntimeError(f'{database} has no retail_transaction table; run prepare_retail_benchmark.py first')
                rows = []
                for case in cases:
                    reference_columns, expected = execute_sql(case['reference_sql'])
                    for repetition in range(1, args.repeat + 1):
                        if remaining <= 0 or token_budget_exhausted:
                            break
                        usage = None
                        started = time.perf_counter()
                        attempts_before = run_budget.used
                        try:
                            with collect_usage() as usage, request_budget(
                                    min(remaining, settings.max_llm_calls), settings.llm_timeout,
                                    settings.max_context_tokens):
                                output = query(case['question'])
                            actual = output.get('rows') or []
                            passed, failure_code = evaluate_output(
                                output, case['expected_table'], expected,
                                order_matters=case.get('order_matters', False))
                            row = {'category': case['category'], 'question': case['question'],
                                   'database': database, 'repetition': repetition, 'passed': passed,
                                   'sql': output.get('sql'), 'actual_rows': actual,
                                   'expected_rows': expected, 'columns': output.get('columns'),
                                   'latency_ms': round((time.perf_counter() - started) * 1000),
                                   'service_latency_ms': output.get('latency_ms'),
                                   'llm_usage': usage.to_dict(),
                                   'budget_requests': run_budget.used - attempts_before}
                            if failure_code:
                                row.update({
                                    'error': failure_code,
                                    'error_type': failure_code,
                                    'error_message': _bounded_text(output.get('answer')),
                                    'failed_step': ('semantic_validate' if failure_code == 'NEED_CLARIFICATION'
                                                    else None),
                                    'trace': output.get('trace') or [],
                                    'sql': _bounded_text(output.get('sql'), 12000),
                                })
                        except Exception as error:
                            message = getattr(error, 'message', None) or str(error)
                            budget_requests = run_budget.used - attempts_before
                            error_code = getattr(error, 'code', type(error).__name__)
                            if error_code == 'LLM_TOKEN_BUDGET_EXCEEDED':
                                token_budget_exhausted = True
                            row = {'category': case['category'], 'question': case['question'],
                                   'database': database, 'repetition': repetition, 'passed': False,
                                   'error': error_code,
                                   'error_type': type(error).__name__,
                                   'error_message': _bounded_text(message),
                                   'failed_step': getattr(error, 'failed_step', None),
                                   'trace': getattr(error, 'trace', []),
                                   'generated_query': getattr(error, 'generated_query', None),
                                   'sql': _bounded_text(getattr(error, 'generated_sql', None), 12000),
                                   'latency_ms': round((time.perf_counter() - started) * 1000),
                                   'llm_usage': usage.to_dict() if usage else {},
                                   'budget_requests': budget_requests}
                        rows.append(row)
                        remaining -= row['budget_requests']
                        token_state = run_budget.token_budget_usage()
                        print(f"{database} {len(rows)} {'PASS' if row['passed'] else 'FAIL'} "
                              f"{row['latency_ms']}ms · {remaining} API attempts and "
                              f"{token_state['remaining_tokens']} tokens remain", flush=True)
                    if remaining <= 0 or token_budget_exhausted:
                        break
                results[database] = rows
                if remaining <= 0 or token_budget_exhausted:
                    break
            token_budget = run_budget.token_budget_usage()
    finally:
        settings.mysql_database = original_database

    summaries = {}
    for database, rows in results.items():
        latencies = [row['latency_ms'] for row in rows]
        summaries[database] = {
            'cases': len(rows), 'passed': sum(row['passed'] for row in rows),
            'accuracy': round(sum(row['passed'] for row in rows) / len(rows), 4) if rows else None,
            'p50_ms': percentile(latencies, .50), 'p95_ms': percentile(latencies, .95),
            'mean_ms': round(statistics.mean(latencies), 2) if latencies else None,
        }
    usage_rows = [row.get('llm_usage') or {} for rows in results.values() for row in rows]
    usage = {key: sum(row.get(key, 0) for row in usage_rows)
             for key in ('api_requests', 'reported_requests', 'prompt_tokens',
                         'completion_tokens', 'total_tokens')}
    report = {'mode': 'live', 'dataset': 'UCI Online Retail II', 'dataset_license': 'CC BY 4.0',
        'dataset_doi': '10.24432/C5CG6D', 'dataset_url': 'https://archive.ics.uci.edu/dataset/502/online+retail+ii',
        'selection': '10,000 evenly spaced valid source rows; the 1,000-row subset is every tenth selected row',
        'model': settings.deepseek_model, 'repeat': args.repeat,
        'api_request_cap': args.max_api_requests, 'api_attempt_ceiling': request_ceiling,
        'api_requests_remaining': remaining, 'llm_usage': usage,
        'token_budget': token_budget, 'token_budget_exhausted': token_budget_exhausted,
        'unreported_usage_requests': max(0, usage['api_requests'] - usage['reported_requests']),
        'summaries': summaries, 'results': results,
        'complete': not token_budget_exhausted and not token_budget['exceeded']
                   and all(item.get('cases') == len(cases) * args.repeat for item in summaries.values())
                   and len(summaries) == len(DATABASES)}
    if args.input_usd_per_million is not None:
        report['estimated_cost_usd'] = round(
            usage['prompt_tokens'] * args.input_usd_per_million / 1_000_000
            + usage['completion_tokens'] * args.output_usd_per_million / 1_000_000, 8)
        report['cost_note'] = 'Estimate uses only token rates supplied on the command line.'
    else:
        report['estimated_cost_usd'] = None
        report['cost_note'] = 'No provider price inferred; use token counts with the account/model rate.'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')
    print(json.dumps({'complete': report['complete'], 'summaries': summaries,
                      'llm_usage': usage, 'token_budget': token_budget,
                      'output': str(args.output)}, ensure_ascii=False, indent=2))
    return 0 if report['complete'] and all(row['passed'] for rows in results.values() for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
