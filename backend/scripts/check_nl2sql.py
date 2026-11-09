import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.nl2sql_service import query

if __name__ == '__main__':
    result = query('列出所有音乐类型')
    assert result['table'].lower() == 'genre' and result['row_count'] == 25
    assert len(result['trace']) == 5
    print('Phase 4 real NL2SQL passed: genre, 25 rows, 5 trace steps')
