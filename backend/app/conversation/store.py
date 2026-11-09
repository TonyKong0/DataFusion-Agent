"""Conversation records in a separate MySQL schema, never in Chinook."""
import json
import re
from contextlib import contextmanager
from threading import Lock
from uuid import uuid4

import pymysql

from app.core.config import get_settings
from app.core.errors import AppError

_schema_lock = Lock()
_schema_ready = False


def _credentials() -> tuple[str, str]:
    settings = get_settings()
    return (settings.conversation_mysql_user or settings.mysql_user,
            settings.conversation_mysql_password.get_secret_value()
            if settings.conversation_mysql_user else settings.mysql_password.get_secret_value())


def _database_name() -> str:
    name = get_settings().conversation_database
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', name):
        raise AppError('CONVERSATION_DB_INVALID', '会话数据库名称不合法', 503)
    if name.lower() == get_settings().mysql_database.lower():
        raise AppError('CONVERSATION_DB_INVALID', '会话数据库必须与 Chinook 分开', 503)
    return name


def ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        settings = get_settings()
        user, password = _credentials()
        if not user:
            raise AppError('MYSQL_NOT_CONFIGURED', '请配置本地 MySQL 连接信息', 503)
        name = _database_name()
        try:
            conn = pymysql.connect(host=settings.mysql_host, port=settings.mysql_port,
                user=user, password=password,
                charset='utf8mb4', connect_timeout=5, read_timeout=10, write_timeout=10,
                autocommit=True)
            try:
                with conn.cursor() as cursor:
                    cursor.execute(f'CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
                    cursor.execute(f'''CREATE TABLE IF NOT EXISTS `{name}`.conversations (
                        id CHAR(32) PRIMARY KEY,
                        owner_id VARCHAR(64) NOT NULL,
                        mode VARCHAR(16) NOT NULL,
                        document_id VARCHAR(64) NULL,
                        document_name VARCHAR(255) NULL,
                        title VARCHAR(200) NOT NULL DEFAULT '新对话',
                        summary TEXT NOT NULL,
                        state_json JSON NOT NULL,
                        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                        updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                        INDEX owner_updated (owner_id, updated_at)
                    ) ENGINE=InnoDB''')
                    cursor.execute('SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=%s AND table_name=%s AND column_name=%s',
                                   (name, 'conversations', 'document_name'))
                    if not cursor.fetchone()[0]:
                        cursor.execute(f'ALTER TABLE `{name}`.conversations ADD COLUMN document_name VARCHAR(255) NULL')
                    cursor.execute(f'''CREATE TABLE IF NOT EXISTS `{name}`.turns (
                        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                        conversation_id CHAR(32) NOT NULL,
                        question TEXT NOT NULL,
                        resolved_question TEXT NOT NULL,
                        answer LONGTEXT NOT NULL,
                        result_json LONGTEXT NOT NULL,
                        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                        INDEX conversation_turns (conversation_id, id),
                        CONSTRAINT fk_conversation_turns FOREIGN KEY (conversation_id)
                            REFERENCES `{name}`.conversations(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB''')
            finally:
                conn.close()
        except pymysql.MySQLError:
            raise AppError('CONVERSATION_DB_UNAVAILABLE', '会话数据库不可用，请检查 MySQL 权限与配置', 503) from None
        _schema_ready = True


@contextmanager
def connection():
    ensure_schema()
    settings = get_settings()
    user, password = _credentials()
    try:
        conn = pymysql.connect(host=settings.mysql_host, port=settings.mysql_port,
            user=user, password=password,
            database=_database_name(), charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5, read_timeout=10, write_timeout=10, autocommit=False)
    except pymysql.MySQLError:
        raise AppError('CONVERSATION_DB_UNAVAILABLE', '会话数据库连接失败', 503) from None
    try:
        yield conn
    finally:
        conn.close()


def _decoded(row: dict | None) -> dict | None:
    if row is None:
        return None
    row['state'] = json.loads(row.pop('state_json') or '{}')
    for key in ('created_at', 'updated_at'):
        if key in row and row[key] is not None:
            row[key] = row[key].isoformat()
    return row


def create(owner_id: str, mode: str, document_id: str | None = None,
           document_name: str | None = None, *, conversation_id: str | None = None) -> dict:
    conversation_id = conversation_id or uuid4().hex
    if not re.fullmatch(r'[0-9a-f]{32}', conversation_id):
        raise AppError('INVALID_CONVERSATION_ID', '对话 ID 不合法', 422)
    with connection() as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute('INSERT INTO conversations (id, owner_id, mode, document_id, document_name, summary, state_json) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                    (conversation_id, owner_id, mode, document_id, document_name, '', '{}'))
            conn.commit()
        except pymysql.MySQLError:
            conn.rollback()
            raise AppError('CONVERSATION_CREATE_FAILED', '创建对话失败', 500) from None
    return get(owner_id, conversation_id)


def get(owner_id: str, conversation_id: str, *, include_turns: bool = False) -> dict:
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT * FROM conversations WHERE id=%s AND owner_id=%s', (conversation_id, owner_id))
        row = _decoded(cursor.fetchone())
        if not row:
            raise AppError('CONVERSATION_NOT_FOUND', '对话不存在', 404)
        if include_turns:
            cursor.execute('SELECT id, question, resolved_question, answer, result_json, created_at FROM turns WHERE conversation_id=%s ORDER BY id', (conversation_id,))
            row['turns'] = [_turn(item) for item in cursor.fetchall()]
        return row


def list_for_owner(owner_id: str) -> list[dict]:
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT * FROM conversations WHERE owner_id=%s ORDER BY updated_at DESC', (owner_id,))
        return [_decoded(row) for row in cursor.fetchall()]


def recent_turns(conversation_id: str, limit: int) -> list[dict]:
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT id, question, resolved_question, answer, result_json, created_at FROM turns WHERE conversation_id=%s ORDER BY id DESC LIMIT %s', (conversation_id, limit))
        return list(reversed([_turn(item) for item in cursor.fetchall()]))


def memory_turns(conversation_id: str, limit: int = 200) -> list[dict]:
    """Load a bounded window of durable turns for session-scoped recall."""
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT id, question, resolved_question, answer, result_json, created_at '
                       'FROM turns WHERE conversation_id=%s ORDER BY id DESC LIMIT %s',
                       (conversation_id, max(1, min(int(limit), 500))))
        return list(reversed([_turn(item) for item in cursor.fetchall()]))


def recent_document_turns(conversation_id: str, document_ids: list[str], limit: int,
                          legacy_document_id: str | None = None) -> list[dict]:
    """Find the latest turns for this exact document selection across the full chat."""
    selected = set(document_ids)
    matches = []
    before_id = None
    with connection() as conn, conn.cursor() as cursor:
        while len(matches) < limit:
            if before_id is None:
                cursor.execute('SELECT id, question, resolved_question, answer, result_json, created_at '
                               'FROM turns WHERE conversation_id=%s ORDER BY id DESC LIMIT 50',
                               (conversation_id,))
            else:
                cursor.execute('SELECT id, question, resolved_question, answer, result_json, created_at '
                               'FROM turns WHERE conversation_id=%s AND id<%s ORDER BY id DESC LIMIT 50',
                               (conversation_id, before_id))
            rows = cursor.fetchall()
            if not rows:
                break
            for row in rows:
                before_id = row['id']
                result = json.loads(row['result_json'] or '{}')
                scope = result.get('document_ids')
                if scope is None and result.get('document_id'):
                    scope = [result['document_id']]
                if scope is None and legacy_document_id:
                    scope = [legacy_document_id]
                if scope is not None and set(scope) == selected:
                    matches.append(_turn(row))
                    if len(matches) == limit:
                        break
            if len(rows) < 50:
                break
    return list(reversed(matches))


def history_turns(conversation_id: str) -> list[dict]:
    """Read only the dialogue text needed to answer questions about this conversation."""
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT id, question, answer, result_json FROM turns WHERE conversation_id=%s ORDER BY id',
                       (conversation_id,))
        history = []
        for item in cursor.fetchall():
            item['conversation_history'] = bool(json.loads(item.pop('result_json') or '{}').get('conversation_history'))
            history.append(item)
        return history


def _turn(row: dict) -> dict:
    row['result'] = json.loads(row.pop('result_json') or '{}')
    row['created_at'] = row['created_at'].isoformat()
    return row


def append_turn(owner_id: str, conversation_id: str, question: str, resolved_question: str,
                result: dict, state: dict) -> None:
    from app.conversation.cancellation import check
    check()
    settings = get_settings()
    with connection() as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute('SELECT summary, title FROM conversations WHERE id=%s AND owner_id=%s FOR UPDATE', (conversation_id, owner_id))
                conversation = cursor.fetchone()
                if not conversation:
                    raise AppError('CONVERSATION_NOT_FOUND', '对话不存在', 404)
                cursor.execute('INSERT INTO turns (conversation_id, question, resolved_question, answer, result_json) VALUES (%s,%s,%s,%s,%s)',
                    (conversation_id, question, resolved_question, result.get('answer') or '', json.dumps(result, ensure_ascii=False, default=str)))
                cursor.execute('SELECT question, answer FROM turns WHERE conversation_id=%s ORDER BY id DESC LIMIT %s',
                    (conversation_id, settings.conversation_recent_turns + 1))
                recent = cursor.fetchall()
                memory_summary = state.get('memory_summary')
                summary = (memory_summary[-settings.conversation_summary_chars:]
                           if isinstance(memory_summary, str) and memory_summary.strip()
                           else conversation['summary'] or '')
                if not memory_summary and len(recent) > settings.conversation_recent_turns:
                    older = recent[-1]
                    summary = (summary + f"\n问：{older['question'][:100]} 答：{older['answer'][:180]}")[-settings.conversation_summary_chars:]
                title = question[:36] if conversation['title'] == '新对话' else conversation['title']
                cursor.execute('UPDATE conversations SET title=%s, summary=%s, state_json=%s, updated_at=CURRENT_TIMESTAMP(6) WHERE id=%s',
                    (title, summary, json.dumps(state, ensure_ascii=False, default=str), conversation_id))
            check()
            conn.commit()
        except AppError:
            conn.rollback()
            raise
        except pymysql.MySQLError:
            conn.rollback()
            raise AppError('CONVERSATION_SAVE_FAILED', '保存对话失败', 500) from None


def delete(owner_id: str, conversation_id: str) -> None:
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute('DELETE FROM conversations WHERE id=%s AND owner_id=%s', (conversation_id, owner_id))
        if not cursor.rowcount:
            raise AppError('CONVERSATION_NOT_FOUND', '对话不存在', 404)
        conn.commit()


def import_legacy(owner_id: str, legacy_id: str, mode: str, document_id: str | None,
                  document_name: str | None, messages: list[dict], last_result: dict | None) -> dict:
    conversation_id = legacy_id.replace('-', '')
    try:
        return get(owner_id, conversation_id)
    except AppError as error:
        if error.code != 'CONVERSATION_NOT_FOUND':
            raise
    create(owner_id, mode, document_id, document_name, conversation_id=conversation_id)
    pending = None
    pairs = []
    for message in messages[:100]:
        if message.get('role') == 'user':
            pending = str(message.get('content') or '')[:2000]
        elif message.get('role') == 'assistant' and pending:
            pairs.append((pending, str(message.get('content') or '')[:20000]))
            pending = None
    for index, (question, answer) in enumerate(pairs):
        result = last_result if index == len(pairs) - 1 and last_result else {'success': True, 'answer': answer}
        state = {}
        if index == len(pairs) - 1 and result.get('clarification', {}).get('session_id'):
            state['pending_clarification_id'] = result['clarification']['session_id']
        append_turn(owner_id, conversation_id, question, question, result, state)
    return get(owner_id, conversation_id)
