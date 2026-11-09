import zipfile
import pytest
from fastapi.testclient import TestClient

from app.api import evaluation
from app.main import app
from app.services import evaluation_workbench as workbench_service


def test_workbench_reports_local_readiness_without_exposing_credentials(monkeypatch):
    monkeypatch.setattr(evaluation.workbench, 'status', lambda: {
        'dataset': {'downloaded': True, 'checksum_verified': True, 'source_rows': None},
        'database': {'connected': True, 'schemas': {
            'retail_bench_1k': {'rows': 1000}, 'retail_bench_10k': {'rows': 10000}},
            'ready': True},
        'model': {'configured': True}, 'job': None,
    })

    response = TestClient(app).get('/api/evaluation/workbench')

    assert response.status_code == 200
    assert response.json()['database']['ready'] is True
    assert response.json()['dataset']['checksum_verified'] is True
    assert 'api_key' not in response.json()['model']


def test_live_workbench_evaluation_requires_a_positive_api_request_limit():
    response = TestClient(app, client=('127.0.0.1', 12345)).post('/api/evaluation/workbench/jobs', json={
        'action': 'retail_evaluation', 'repeat': 3,
    })

    assert response.status_code == 422


def test_ohr_live_evaluation_requires_a_positive_api_request_limit():
    response = TestClient(app, client=('127.0.0.1', 12345)).post('/api/evaluation/workbench/jobs', json={
        'action': 'ohr_evaluation',
    })

    assert response.status_code == 422


def test_ohr_live_evaluation_forwards_the_request_limit(monkeypatch):
    calls = []
    monkeypatch.setattr(evaluation.workbench, 'start', lambda action, **options: (
        calls.append((action, options)) or {'job_id': 'ohr-test', 'status': 'queued'}))

    response = TestClient(app, client=('127.0.0.1', 12345)).post('/api/evaluation/workbench/jobs', json={
        'action': 'ohr_evaluation', 'max_api_requests': 23,
    })

    assert response.status_code == 202
    assert calls == [('ohr_evaluation', {'repeat': 3, 'max_api_requests': 23})]


def test_conversation_memory_evaluation_requires_api_cap():
    response = TestClient(app, client=('127.0.0.1', 12345)).post('/api/evaluation/workbench/jobs', json={
        'action': 'conversation_memory_evaluation', 'context_limit_tokens': 16000,
    })

    assert response.status_code == 422


def test_conversation_memory_evaluation_forwards_api_and_context_caps(monkeypatch):
    calls = []
    monkeypatch.setattr(evaluation.workbench, 'start', lambda action, **options: (
        calls.append((action, options)) or {'job_id': 'memory-test', 'status': 'queued'}))

    response = TestClient(app, client=('127.0.0.1', 12345)).post('/api/evaluation/workbench/jobs', json={
        'action': 'conversation_memory_evaluation', 'max_api_requests': 150,
        'context_limit_tokens': 16000,
    })

    assert response.status_code == 202
    assert calls == [('conversation_memory_evaluation', {
        'repeat': 3, 'max_api_requests': 150, 'context_limit_tokens': 16000})]


def test_workbench_mutations_are_restricted_to_loopback_clients():
    response = TestClient(app, client=('192.0.2.10', 12345)).post(
        '/api/evaluation/workbench/jobs', json={'action': 'preview'})

    assert response.status_code == 403


def test_workbench_starts_allowlisted_operation_with_explicit_live_cap(monkeypatch):
    calls = []
    monkeypatch.setattr(evaluation.workbench, 'start', lambda action, **options: (
        calls.append((action, options)) or {'job_id': 'job-test', 'status': 'queued'}))

    response = TestClient(app, client=('127.0.0.1', 12345)).post('/api/evaluation/workbench/jobs', json={
        'action': 'retail_evaluation', 'repeat': 2, 'max_api_requests': 17,
    })

    assert response.status_code == 202
    assert response.json()['job_id'] == 'job-test'
    assert calls == [('retail_evaluation', {'repeat': 2, 'max_api_requests': 17})]


def test_workbench_rejects_unknown_actions():
    response = TestClient(app).post('/api/evaluation/workbench/jobs', json={'action': 'run arbitrary shell'})

    assert response.status_code == 422


def test_completed_retail_evaluation_with_wrong_answers_is_not_an_environment_failure():
    outcome = workbench_service.EvaluationWorkbench._job_outcome(
        1, 'retail_evaluation', {'complete': True, 'summaries': {
            'retail_bench_1k': {'cases': 10, 'passed': 6},
            'retail_bench_10k': {'cases': 10, 'passed': 7},
        }})

    assert outcome[0] == 'completed_with_failures'
    assert '部分题未通过' in outcome[1]
    assert workbench_service.EvaluationWorkbench._job_outcome(
        1, 'retail_evaluation', {'complete': False})[0] == 'failed'


def test_ohr_action_requires_the_local_research_archive_and_keeps_it_outside_git(tmp_path, monkeypatch):
    archive = tmp_path / 'ohr-bench-v2-pdfs.zip'
    monkeypatch.setattr(workbench_service, 'OHR_PDF_ZIP_PATH', archive)

    with pytest.raises(RuntimeError, match='缺少 OHR-Bench PDF 压缩包'):
        workbench_service.workbench.start('ohr_evaluation', max_api_requests=12)

    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('fixture.pdf', b'%PDF-test')
    status = workbench_service.workbench._ohr_dataset_status()
    assert status == {
        'available': True,
        'size_bytes': archive.stat().st_size,
        'path': 'backend/data/benchmarks/ohr-bench-v2-pdfs.zip',
    }


def test_new_metric_jobs_use_capped_arguments_and_ignored_report_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(workbench_service, 'REPORT_DIR', tmp_path / 'evaluation')
    monkeypatch.setattr(workbench_service, 'OHR_PDF_ZIP_PATH', tmp_path / 'ohr-bench-v2-pdfs.zip')

    agent_command, _ = workbench_service.workbench._command('agent_offline_evaluation', 3, None)
    multimodal_command, _ = workbench_service.workbench._command('multimodal_offline_evaluation', 3, None)
    ohr_command, _ = workbench_service.workbench._command('ohr_evaluation', 3, 23)
    memory_command, _ = workbench_service.workbench._command(
        'conversation_memory_evaluation', 3, 150, 16000)

    assert str(tmp_path / 'evaluation' / 'agent-offline.json') in agent_command
    assert str(tmp_path / 'evaluation' / 'multimodal-offline') in multimodal_command
    assert '--max-api-requests' in ohr_command and '23' in ohr_command
    assert '--max-api-requests' in memory_command and '150' in memory_command
    assert '--context-limit-tokens' in memory_command and '16000' in memory_command
    assert str(tmp_path / 'evaluation' / 'conversation-memory.json') in memory_command
    assert str(tmp_path / 'evaluation' / 'ohr-bench.json') in ohr_command


def test_agent_evaluation_switches_to_live_only_when_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(workbench_service, 'REPORT_DIR', tmp_path / 'evaluation')

    offline_command, _ = workbench_service.workbench._command('agent_offline_evaluation', 3, None)
    live_command, live_label = workbench_service.workbench._command('agent_offline_evaluation', 3, 220)

    assert '--live' not in offline_command
    assert str(tmp_path / 'evaluation' / 'agent-offline.json') in offline_command
    assert '--live' in live_command
    assert '--max-api-requests' in live_command and '220' in live_command
    assert str(tmp_path / 'evaluation' / 'agent-live.json') in live_command
    assert '220' in live_label
