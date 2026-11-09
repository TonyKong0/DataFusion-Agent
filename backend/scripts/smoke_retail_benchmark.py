"""Run the ten fixed read-only retail SQL cases on each prepared MySQL sample."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.config import get_settings

CASES = ROOT / 'tests' / 'cases' / 'retail_nl2sql_cases.json'
DATABASES = ('retail_bench_1k', 'retail_bench_10k')


def main() -> int:
    settings = get_settings()
    if not settings.mysql_user:
        raise SystemExit('MySQL account is not configured')
    cases = json.loads(CASES.read_text(encoding='utf-8'))
    output = {'mode': 'database_smoke', 'api_requests': 0, 'cases_per_database': len(cases),
              'databases': {}}
    connection = pymysql.connect(host=settings.mysql_host, port=settings.mysql_port,
        user=settings.mysql_user, password=settings.mysql_password.get_secret_value(),
        charset='utf8mb4', connect_timeout=5, read_timeout=30)
    try:
        with connection.cursor() as cursor:
            for database in DATABASES:
                cursor.execute('SELECT COUNT(*) FROM information_schema.TABLES '
                               'WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s',
                               (database, 'retail_transaction'))
                if not cursor.fetchone()[0]:
                    raise RuntimeError(f'{database}.retail_transaction is missing')
                cursor.execute(f'SELECT COUNT(*) FROM `{database}`.retail_transaction')
                row_count = int(cursor.fetchone()[0])
                results = []
                for case in cases:
                    started = time.perf_counter()
                    cursor.execute(f"USE `{database}`")
                    cursor.execute(case['reference_sql'])
                    rows = cursor.fetchall()
                    results.append({'category': case['category'], 'success': True,
                                    'returned_rows': len(rows),
                                    'latency_ms': round((time.perf_counter() - started) * 1000)})
                    print(json.dumps({'database': database, 'category': case['category'],
                                      'success': True}, ensure_ascii=False), flush=True)
                output['databases'][database] = {'table_rows': row_count,
                    'cases': results, 'passed': sum(item['success'] for item in results)}
    finally:
        connection.close()
    output['complete'] = all(item['passed'] == len(cases) for item in output['databases'].values()) \
        and len(output['databases']) == len(DATABASES)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
