"""Run the two real 10-case demo suites and persist inspectable outcomes."""
import json
import argparse
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.nl2sql_service import query as sql_query
from app.services.rag_service import query as rag_query
from app.services.document_service import list_documents
from app.agent.budget import request_budget
from app.core.config import get_settings
from app.llm.usage import collect_usage

ROOT = Path(__file__).resolve().parents[2]
CASES = Path(__file__).resolve().parents[1] / 'tests/cases'


def main() -> int:
    parser = argparse.ArgumentParser(description='Run the labeled 10 NL2SQL + 10 RAG live evaluation.')
    parser.add_argument('--live', action='store_true', help='call the configured model API; without this flag only print the run plan')
    parser.add_argument('--max-api-requests', type=int,
                        help='hard per-run upper bound on model HTTP attempts; required with --live')
    parser.add_argument('--input-usd-per-million', type=float,
                        help='optional account input-token price used only for a local estimate')
    parser.add_argument('--output-usd-per-million', type=float,
                        help='optional account output-token price used only for a local estimate')
    parser.add_argument('--output', type=Path, default=ROOT/'docs/test-results.json',
                        help='result path (defaults to the tracked historical location)')
    args = parser.parse_args()
    assert len(json.loads((CASES/'nl2sql_cases.json').read_text(encoding='utf-8'))) >= 10
    assert len(json.loads((CASES/'rag_cases.json').read_text(encoding='utf-8'))) >= 10
    if not args.live:
        print(json.dumps({'mode': 'preview_only', 'nl2sql_cases': 10, 'rag_cases': 10,
                          'model': get_settings().deepseek_model,
                          'api_calls': 0,
                          'next_step': 'add --live --max-api-requests N to authorize a bounded live run'},
                         ensure_ascii=False, indent=2))
        return 0
    if not args.max_api_requests or args.max_api_requests < 1:
        parser.error('--live requires --max-api-requests with a positive request cap')
    if (args.input_usd_per_million is None) != (args.output_usd_per_million is None):
        parser.error('provide both token prices or neither')
    documents = list_documents()
    if len(documents) != 1 or documents[0]['status'] != 'indexed':
        raise SystemExit('请先上传并索引唯一的 docs/demo.pdf')
    document_id = documents[0]['document_id']
    settings = get_settings()
    report = {'mode': 'live', 'model': settings.deepseek_model, 'nl2sql': [], 'rag': [],
              'document_id': document_id, 'evaluated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
              'api_request_cap': args.max_api_requests,
              'input_usd_per_million': args.input_usd_per_million,
              'output_usd_per_million': args.output_usd_per_million}
    remaining = args.max_api_requests
    for case in json.loads((CASES/'nl2sql_cases.json').read_text(encoding='utf-8')):
        if remaining <= 0:
            break
        usage = None
        budget = None
        try:
            with collect_usage() as usage, request_budget(
                    min(remaining, settings.max_llm_calls), settings.llm_timeout,
                    settings.max_context_tokens) as budget:
                result = sql_query(case['question'])
            passed = (result.get('table', '').lower() == case['expected_table'] and
                      result['row_count'] >= case['expected_min_rows'] and bool(result.get('sql')))
            item = {**case, 'passed': passed, 'table': result.get('table'), 'sql': result.get('sql'),
                    'row_count': result.get('row_count'), 'latency_ms': result.get('latency_ms'),
                    'llm_usage': usage.to_dict(), 'budget_requests': budget.used}
        except Exception as error:
            item = {**case, 'passed': False, 'error': getattr(error, 'code', type(error).__name__)}
            item['llm_usage'] = usage.to_dict() if usage else {}
            item['budget_requests'] = budget.used if budget else 0
        report['nl2sql'].append(item)
        remaining -= int(item.get('budget_requests', 0))
        print(f"NL2SQL {len(report['nl2sql'])}/10 {'PASS' if item['passed'] else 'FAIL'}", flush=True)
    for case in json.loads((CASES/'rag_cases.json').read_text(encoding='utf-8')):
        if remaining <= 0:
            break
        usage = None
        budget = None
        try:
            with collect_usage() as usage, request_budget(
                    min(remaining, settings.max_llm_calls), settings.llm_timeout,
                    settings.max_context_tokens) as budget:
                result = rag_query(document_id, case['question'], 5)
            answer = result['answer'].lower()
            passed = (any(source['page'] == case['expected_page'] for source in result['sources']) and
                      all(word.lower() in answer for word in case['expected_keywords']))
            item = {**case, 'passed': passed, 'answer': result['answer'],
                    'source_pages': [source['page'] for source in result['sources']], 'latency_ms': result['latency_ms'],
                    'llm_usage': usage.to_dict(), 'budget_requests': budget.used}
        except Exception as error:
            item = {**case, 'passed': False, 'error': getattr(error, 'code', type(error).__name__)}
            item['llm_usage'] = usage.to_dict() if usage else {}
            item['budget_requests'] = budget.used if budget else 0
        report['rag'].append(item)
        remaining -= int(item.get('budget_requests', 0))
        print(f"RAG {len(report['rag'])}/10 {'PASS' if item['passed'] else 'FAIL'}", flush=True)
    report['summary'] = {kind: {'passed': sum(item['passed'] for item in report[kind]), 'total': len(report[kind])}
                         for kind in ('nl2sql', 'rag')}
    usage_rows = [item.get('llm_usage') or {} for kind in ('nl2sql', 'rag') for item in report[kind]]
    report['llm_usage'] = {key: sum(row.get(key, 0) for row in usage_rows)
                           for key in ('api_requests', 'reported_requests', 'prompt_tokens',
                                       'completion_tokens', 'total_tokens')}
    report['unreported_usage_requests'] = max(
        0, report['llm_usage']['api_requests'] - report['llm_usage']['reported_requests'])
    if args.input_usd_per_million is not None:
        report['estimated_cost_usd'] = round(
            report['llm_usage']['prompt_tokens'] * args.input_usd_per_million / 1_000_000
            + report['llm_usage']['completion_tokens'] * args.output_usd_per_million / 1_000_000, 8)
        report['cost_note'] = 'Estimate uses only the token rates supplied on the command line.'
    else:
        report['estimated_cost_usd'] = None
        report['cost_note'] = 'Provider/model pricing was not inferred; use reported token counts with the account rate.'
    report['complete'] = len(report['nl2sql']) == 10 and len(report['rag']) == 10
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'complete': report['complete'], 'summary': report['summary'],
                      'llm_usage': report['llm_usage'],
                      'unreported_usage_requests': report['unreported_usage_requests'],
                      'output': str(args.output)}, ensure_ascii=False))
    if not report['complete'] or any(value['passed'] != value['total'] for value in report['summary'].values()):
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
