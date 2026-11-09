"""Offline, reproducible 50-case schema linking evaluation."""

import json
from pathlib import Path

from app.schema.candidate_retriever import retrieve_candidates
from app.schema.models import SchemaMetadata
from app.schema.schema_linker import link_schema


CASES_DIR = Path(__file__).parent / 'cases'
FIXTURE = Path(__file__).parent / 'fixtures' / 'chinook_schema.json'


def evaluate() -> dict:
    metadata = SchemaMetadata.model_validate_json(FIXTURE.read_text(encoding='utf-8'))
    base = json.loads((CASES_DIR / 'schema_candidate_cases.json').read_text(encoding='utf-8'))
    extras = json.loads((CASES_DIR / 'schema_linking_extra_cases.json').read_text(encoding='utf-8'))
    cases = []
    for item in base:
        tables = {'customer', 'invoice'} if '每个客户消费' in item['question'] else (
            {'genre', 'track', 'invoiceline'} if '类型卖出' in item['question'] else {item['table']})
        cases.append({'question': item['question'], 'tables': sorted(tables),
                      'columns': [f"{item['table']}.{item['column']}"]})
    cases.extend(extras)
    assert len(cases) == 50
    totals = {'table_recall_at_5': 0, 'column_recall_at_10': 0,
              'table_accuracy': 0, 'column_accuracy': 0, 'exact_match': 0}
    failures = []
    for case in cases:
        candidates = retrieve_candidates(case['question'], [], metadata)
        linked = link_schema(case['question'], [], candidates, metadata)
        gold_tables = set(case['tables'])
        gold_columns = set(case['columns'])
        recalled_tables = {item['table'] for item in candidates['candidate_tables'][:5]}
        recalled_columns = {f"{item['table']}.{item['column']}" for item in candidates['candidate_columns'][:10]}
        selected_tables = set(linked['selected_tables'])
        selected_columns = set(linked['selected_columns'])
        outcomes = {
            'table_recall_at_5': gold_tables <= recalled_tables,
            'column_recall_at_10': gold_columns <= recalled_columns,
            'table_accuracy': gold_tables <= selected_tables,
            'column_accuracy': gold_columns <= selected_columns,
            'exact_match': gold_tables == selected_tables and gold_columns <= selected_columns,
        }
        for metric, value in outcomes.items():
            totals[metric] += int(value)
        if not outcomes['exact_match']:
            failures.append({'question': case['question'], 'expected_tables': case['tables'],
                             'selected_tables': linked['selected_tables'],
                             'missing_columns': sorted(gold_columns - selected_columns)})
    return {'cases': len(cases), 'metrics': {key: round(value / len(cases), 4)
                                           for key, value in totals.items()}, 'failures': failures}


if __name__ == '__main__':
    result = evaluate()
    target = Path(__file__).resolve().parents[2] / 'docs' / 'evaluation_schema_linking_results.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
