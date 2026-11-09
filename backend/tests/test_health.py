import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import health as health_api
from app.core.version import APP_VERSION
from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_health_reports_single_source_version(monkeypatch):
    monkeypatch.setattr(health_api, 'database_status', lambda: None)
    monkeypatch.setattr(health_api, 'is_reachable', lambda: True)
    monkeypatch.setattr(health_api, 'list_documents', lambda: [])

    payload = TestClient(app).get('/api/health').json()

    assert payload['status'] == 'ok'
    assert payload['version'] == APP_VERSION


def test_package_version_matches_backend_version():
    package = json.loads((REPO_ROOT / 'package.json').read_text(encoding='utf-8'))
    lock = json.loads((REPO_ROOT / 'package-lock.json').read_text(encoding='utf-8'))

    assert package['version'] == APP_VERSION
    assert lock['version'] == APP_VERSION
    assert lock['packages']['']['version'] == APP_VERSION
