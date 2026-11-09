import json
from fastapi.testclient import TestClient
from app.main import app
from app.api import evaluation


def test_evaluation_endpoint_reads_report_and_preserves_source_scope(tmp_path, monkeypatch):
    report = {'status': 'passed', 'tests': {'total': 3, 'passed': 3, 'failed': 0, 'skipped': 0},
              'modules': [{'module': 'tests.test_agent_phase50_eval', 'total': 2, 'passed': 2}]}
    file = tmp_path / 'test_summary.json'
    file.write_text(json.dumps(report), encoding='utf-8')
    monkeypatch.setattr(evaluation, 'REPORT_PATH', file)
    payload = TestClient(app).get('/api/evaluation/summary').json()
    assert payload['report']['tests']['total'] == 3
    assert next(row for row in payload['version_comparison'] if row['version'] == 'V5')['scope'].startswith('模拟/离线')
    assert all(row['source'].startswith(('docs/', 'reports/')) for row in payload['version_comparison'])


def test_evaluation_endpoint_does_not_invent_missing_report(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation, 'REPORT_PATH', tmp_path / 'missing.json')
    payload = TestClient(app).get('/api/evaluation/summary').json()
    assert payload['report_available'] is False and payload['report'] is None
    assert not any(row['version'] == 'V5' for row in payload['version_comparison'])
