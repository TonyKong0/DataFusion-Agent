"""Live, paired V1-direct / V2-semantic comparison on the local Chinook DB."""

import json
import time
from pathlib import Path

from app.core.errors import AppError
from app.db.schema_loader import load_schema
from app.llm.deepseek_client import chat, chat_json
from app.llm.prompts import ANSWER_SYSTEM, NL2SQL_SYSTEM
from app.services.nl2sql_service import query
from app.services.sql_executor import execute_sql
from app.services.sql_validator import validate_sql


CASES = [
    {'question': '一共有多少个艺术家', 'table': 'artist', 'kind': 'artist_count'},
    {'question': '列出所有音乐类型', 'table': 'genre', 'kind': 'genre_list'},
    {'question': '给我瞅瞅美国的客户', 'table': 'customer', 'kind': 'usa_customers'},
    {'question': '显示价格最高的10首歌曲', 'table': 'track', 'kind': 'price_top10'},
    {'question': '客户和员工', 'table': None, 'kind': 'clarify'},
    {'question': '客户增长率是多少', 'table': None, 'kind': 'clarify'},
]


def run_direct(question):
    start = time.perf_counter()
    try:
        schema = load_schema()
        generated = chat_json(NL2SQL_SYSTEM, json.dumps({'schema': schema, 'question': question}, ensure_ascii=False))
        if generated.get('need_clarification') is True:
            return {'sql': None, 'table': None, 'rows': [], 'columns': [],
                    'clarified': True, 'executed': False, 'latency_ms': round((time.perf_counter()-start)*1000)}
        sql, table = validate_sql(generated['sql'], generated['table'], schema)
        columns, rows = execute_sql(sql)
        chat(ANSWER_SYSTEM, json.dumps({'question': question, 'sql': sql,
                                        'columns': columns, 'rows': rows}, ensure_ascii=False))
        return {'sql': sql, 'table': table, 'rows': rows, 'columns': columns,
                'clarified': False, 'executed': True, 'latency_ms': round((time.perf_counter()-start)*1000)}
    except (AppError, KeyError, TypeError, ValueError) as error:
        return {'sql': None, 'table': None, 'rows': [], 'columns': [],
                'clarified': False, 'executed': False, 'error': type(error).__name__,
                'latency_ms': round((time.perf_counter()-start)*1000)}


def run_semantic(question):
    start = time.perf_counter()
    try:
        result = query(question)
        return {'sql': result['sql'], 'table': result['table'], 'rows': result['rows'],
                'columns': result['columns'], 'clarified': result['need_clarification'],
                'executed': any(item['name'] == 'sql_execute' for item in result['trace']),
                'latency_ms': round((time.perf_counter()-start)*1000)}
    except AppError as error:
        return {'sql': None, 'table': None, 'rows': [], 'columns': [],
                'clarified': False, 'executed': False, 'error': error.code,
                'latency_ms': round((time.perf_counter()-start)*1000)}


def grade(case, result):
    if case['table'] is None:
        return bool(result['clarified'] and not result['executed'])
    if not result['executed'] or str(result['table']).lower() != case['table']:
        return False
    rows = [row if isinstance(row, dict) else dict(zip(result['columns'], row))
            for row in result['rows']]
    kind = case['kind']
    if kind == 'artist_count':
        return len(rows) == 1 and 275 in rows[0].values()
    if kind == 'genre_list':
        return len(rows) == 25
    if kind == 'usa_customers':
        return bool(rows) and all(str(row.get('Country', row.get('country', ''))).upper() == 'USA' for row in rows)
    if kind == 'price_top10':
        prices = [row.get('UnitPrice', row.get('unitprice')) for row in rows]
        return len(rows) == 10 and all(price is not None for price in prices) and prices == sorted(prices, reverse=True)
    return False


def evaluate():
    details = []
    for case in CASES:
        item = {'question': case['question'], 'expected_table': case['table']}
        for name, runner in (('v1', run_direct), ('v2', run_semantic)):
            result = runner(case['question'])
            item[name] = {'correct': grade(case, result), 'table': result['table'],
                          'sql': result['sql'], 'executed': result['executed'],
                          'clarified': result['clarified'], 'latency_ms': result['latency_ms'],
                          'error': result.get('error')}
        details.append(item)
    summary = {}
    for name in ('v1', 'v2'):
        results = [item[name] for item in details]
        summary[name] = {
            'cases': len(results), 'accuracy': sum(item['correct'] for item in results) / len(results),
            'wrong_sql': sum(bool(item['sql']) and not item['correct'] for item in results),
            'wrong_entity': sum(item['table'] is not None and
                                item['table'].lower() != (case['expected_table'] or '')
                                for item, case in zip(results, details)),
            'wrong_execution': sum(item['executed'] and not item['correct'] for item in results),
            'avg_latency_ms': round(sum(item['latency_ms'] for item in results) / len(results)),
        }
    return {'summary': summary, 'details': details}


if __name__ == '__main__':
    report = evaluate()
    output = Path(__file__).resolve().parents[2] / 'docs' / 'evaluation_v2_results.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')
    print(json.dumps(report['summary'], ensure_ascii=False, indent=2))
