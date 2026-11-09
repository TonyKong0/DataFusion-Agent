"""Bounded OHR-Bench v2 OCR/RAG pilot using a fixed 15-question subset."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agent.budget import request_budget
from app.core.config import get_settings
from app.llm.usage import collect_usage
from app.services.document_service import delete_document, import_document, index_document
from app.services.rag_service import query

CASES_PATH = ROOT / 'tests/cases/ohr_bench_subset.json'
DATASET_REVISION = '7f833e3eda9a571a9ea545a8f6d476fa1685033d'
API_RE = re.compile(r'[^\w]+', re.UNICODE)


def normalize(value: str) -> str:
    value = unicodedata.normalize('NFKC', value).casefold().replace(',', '')
    return API_RE.sub(' ', value).strip()


def answer_matches(answer: str, gold: str) -> bool:
    expected = normalize(gold)
    actual = normalize(answer)
    return bool(expected) and expected in actual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf-zip', type=Path, help='OHR-Bench pdfs.zip downloaded from the pinned dataset revision')
    parser.add_argument('--live', action='store_true', help='call the configured model API; otherwise only print the run plan')
    parser.add_argument('--max-api-requests', type=int,
                        help='hard upper bound on model HTTP attempts; required with --live')
    parser.add_argument('--input-usd-per-million', type=float)
    parser.add_argument('--output-usd-per-million', type=float)
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'docs/evaluation_ohr_bench.json')
    args = parser.parse_args()
    cases = json.loads(CASES_PATH.read_text(encoding='utf-8'))
    categories = sorted({item['evidence_source'] for item in cases})
    if len(cases) != 15 or len(categories) != 5:
        raise RuntimeError('the fixed OHR subset must contain 15 cases across five evidence categories')
    if not args.live:
        print(json.dumps({'mode': 'preview_only', 'dataset': 'OHR-Bench v2',
            'dataset_revision': DATASET_REVISION, 'cases': len(cases),
            'categories': {name: sum(row['evidence_source'] == name for row in cases) for name in categories},
            'documents': len({row['doc_name'] for row in cases}),
            'model': get_settings().deepseek_model, 'api_requests': 0,
            'next_step': 'provide --pdf-zip and add --live --max-api-requests N for a bounded paid run'},
            ensure_ascii=False, indent=2))
        return 0
    if not args.pdf_zip or not args.pdf_zip.is_file():
        parser.error('--live requires --pdf-zip pointing to the downloaded OHR-Bench pdfs.zip')
    if not args.max_api_requests or args.max_api_requests < 1:
        parser.error('--live requires --max-api-requests with a positive request cap')
    if (args.input_usd_per_million is None) != (args.output_usd_per_million is None):
        parser.error('provide both token prices or neither')

    settings = get_settings()
    remaining = args.max_api_requests
    document_ids = {}
    results = []
    try:
        with zipfile.ZipFile(args.pdf_zip) as archive:
            members = [name for name in archive.namelist() if not name.endswith('/')]
            for doc_name in sorted({row['doc_name'] for row in cases}):
                suffix = doc_name.replace('\\', '/').strip('/') + '.pdf'
                matches = [name for name in members if name.casefold().endswith(suffix.casefold())]
                if len(matches) != 1:
                    raise RuntimeError(f'expected one PDF for {doc_name}, found {len(matches)}')
                filename = Path(doc_name).name + '.pdf'
                content = archive.read(matches[0])
                imported = import_document(content, filename)
                document_id = imported['document_id']
                document_ids[doc_name] = document_id
                index_document(document_id)

            for case in cases:
                if remaining <= 0:
                    break
                usage = None
                budget = None
                started = time.perf_counter()
                try:
                    with collect_usage() as usage, request_budget(
                            min(remaining, settings.max_llm_calls), settings.llm_timeout,
                            settings.max_context_tokens) as budget:
                        result = query(document_ids[case['doc_name']], case['question'],
                                       settings.rag_top_k)
                    pages = [source['page'] for source in result.get('sources', [])]
                    page_hit = bool(set(pages) & set(case['pages']))
                    answer_hit = answer_matches(result.get('answer', ''), case['answer'])
                    row = {'id': case['id'], 'evidence_source': case['evidence_source'],
                           'doc_type': case['doc_type'], 'question': case['question'],
                           'gold_answer': case['answer'], 'answer': result.get('answer'),
                           'gold_pages': case['pages'], 'source_pages': pages,
                           'answer_match': answer_hit, 'evidence_page_hit': page_hit,
                           'passed': answer_hit and page_hit,
                           'latency_ms': round((time.perf_counter() - started) * 1000),
                           'llm_usage': usage.to_dict(), 'budget_requests': budget.used}
                except Exception as error:
                    row = {'id': case['id'], 'evidence_source': case['evidence_source'],
                           'doc_type': case['doc_type'], 'question': case['question'],
                           'gold_answer': case['answer'], 'passed': False,
                           'error': getattr(error, 'code', type(error).__name__),
                           'latency_ms': round((time.perf_counter() - started) * 1000),
                           'llm_usage': usage.to_dict() if usage else {},
                           'budget_requests': budget.used if budget else 0}
                results.append(row)
                remaining -= row['budget_requests']
                print(f"{case['id']} {case['evidence_source']} "
                      f"{'PASS' if row['passed'] else 'FAIL'} · {remaining} API requests remain", flush=True)
    finally:
        for document_id in document_ids.values():
            try:
                delete_document(document_id)
            except Exception:
                pass

    summaries = {category: {
        'cases': sum(row['evidence_source'] == category for row in results),
        'passed': sum(row['passed'] for row in results if row['evidence_source'] == category),
    } for category in categories}
    for summary in summaries.values():
        summary['accuracy'] = round(summary['passed'] / summary['cases'], 4) if summary['cases'] else None
    usage_rows = [row.get('llm_usage') or {} for row in results]
    usage = {key: sum(row.get(key, 0) for row in usage_rows)
             for key in ('api_requests', 'reported_requests', 'prompt_tokens',
                         'completion_tokens', 'total_tokens')}
    report = {'mode': 'live', 'dataset': 'OHR-Bench v2', 'dataset_revision': DATASET_REVISION,
        'dataset_license': 'CC BY 4.0', 'subset_size': len(cases), 'evaluated_cases': len(results),
        'categories': summaries, 'documents': len(document_ids), 'model': settings.deepseek_model,
        'api_request_cap': args.max_api_requests, 'api_requests_remaining': remaining,
        'llm_usage': usage, 'unreported_usage_requests': max(0, usage['api_requests'] - usage['reported_requests']),
        'results': results, 'complete': len(results) == len(cases)}
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
    print(json.dumps({'complete': report['complete'], 'categories': summaries,
        'llm_usage': usage, 'output': str(args.output)}, ensure_ascii=False, indent=2))
    return 0 if report['complete'] and all(row['passed'] for row in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
