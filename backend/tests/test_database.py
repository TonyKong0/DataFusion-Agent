from fastapi.testclient import TestClient
from app.main import app
from app.core.config import get_settings, Settings
from app.core.errors import AppError
from app.api import database


def test_unconfigured_database(monkeypatch):
    from app.db import mysql
    monkeypatch.setattr(mysql, 'get_settings', lambda: Settings(_env_file=None, mysql_user=''))
    response = TestClient(app).get('/api/database/schema')
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'MYSQL_NOT_CONFIGURED'


def test_schema_api(monkeypatch):
    schema = [{'table': 'Genre', 'columns': [{'name': 'GenreId', 'primary_key': True}], 'foreign_keys': []}]
    monkeypatch.setattr(database, 'load_schema', lambda: schema)
    response = TestClient(app).get('/api/database/schema')
    assert response.status_code == 200
    assert response.json()['tables'] == schema


def test_connection_error_is_sanitized(monkeypatch):
    def fail():
        raise AppError('MYSQL_CONNECTION_FAILED', 'MySQL 连接失败', 503)
    monkeypatch.setattr(database, 'database_status', fail)
    response = TestClient(app).get('/api/database/status')
    assert response.status_code == 503
    assert response.json()['error'] == {'code': 'MYSQL_CONNECTION_FAILED', 'message': 'MySQL 连接失败'}
